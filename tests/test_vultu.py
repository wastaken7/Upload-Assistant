# ruff: noqa: S101
import asyncio
import runpy
from pathlib import Path
from typing import Any

import httpx
import pytest

from src.meta import Meta
from src.trackers import vultu as vultu_module
from src.trackers.UNIT3D.capybarabr import CapybaraBR
from src.trackers.vultu import Vultu
from src.trackersetup import STATIC_AUTH_TYPES, TrackerSetup, tracker_class_map

CONFIG = {"DEFAULT": {}, "TRACKERS": {"VULTU": {"api_key": "test-token", "anon": False}}}


def _mock_client(monkeypatch: pytest.MonkeyPatch, handler: Any) -> list[httpx.Request]:
    """Route every client the tracker creates through a mock transport."""
    requests: list[httpx.Request] = []
    real_client = httpx.AsyncClient

    def recording_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    def factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(recording_handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(vultu_module.httpx, "AsyncClient", factory)
    return requests


def test_registration_and_config() -> None:
    example_config = runpy.run_path(str(Path(__file__).resolve().parents[1] / "data" / "example_config.py"))["config"]
    assert tracker_class_map["VULTU"] is Vultu
    assert STATIC_AUTH_TYPES["VULTU"] == "other_api"
    assert example_config["TRACKERS"]["VULTU"]["cli_alias"] == "VLT"
    assert "announce_url" not in example_config["TRACKERS"]["VULTU"]


@pytest.mark.parametrize(("category", "kept"), [("MOVIE", True), ("TV", True), ("GAME", True), ("MUSIC", False), ("BOOK", False)])
def test_supported_categories(category: str, kept: bool) -> None:
    meta = Meta(category=category, trackers=["VULTU"])
    TrackerSetup(CONFIG).filter_unsupported_trackers(meta)
    assert (meta.trackers == ["VULTU"]) is kept


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"category": "MOVIE", "tmdb": 101}, "tmdb:movie:101"),
        ({"category": "TV", "tmdb_id": 202}, "tmdb:tv:202"),
        ({"category": "GAME", "igdb_id": 303}, "igdb:303"),
        ({"category": "GAME"}, ""),
        ({"category": "MOVIE"}, ""),
    ],
)
def test_work_from_ids(values: dict[str, Any], expected: str) -> None:
    assert asyncio.run(Vultu(CONFIG).get_work(Meta(**values))) == expected


def test_work_translates_imdb_through_works_search(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/works"
        assert request.url.params["imdb"] == "tt0000001"
        assert request.url.params["kind"] == "tv"
        assert request.headers["Authorization"] == "Bearer test-token"
        return httpx.Response(200, json={"results": [{"work": "tmdb:movie:9", "kind": "movie"}, {"work": "tmdb:tv:42", "kind": "tv"}]})

    _mock_client(monkeypatch, handler)
    assert asyncio.run(Vultu(CONFIG).get_work(Meta(category="TV", imdb_tt="tt0000001"))) == "tmdb:tv:42"


def test_search_existing_paginates_and_maps_releases(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = {
        None: {
            "releases": [
                {
                    "id": None,
                    "name": "Fictional.Show.S02.1080p.WEB-DL.DDP5.1.H.264-NOGRP",
                    "size": 1000,
                    "files": [{"path": "Fictional.Show.S02E01.mkv", "size": 500}, {"path": "Fictional.Show.S02E02.mkv", "size": 500}],
                    "url": None,
                    "pending": True,
                }
            ],
            "next": 77,
        },
        "77": {"releases": [{"id": 5, "name": "Fictional.Show.S02.2160p.BluRay.x265-OTHER", "size": 2000, "files": [], "url": "https://vultu.org/torrents/5"}], "next": None},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/duplicates"
        assert request.url.params["work"] == "tmdb:tv:12"
        assert request.url.params["season"] == "2"
        return httpx.Response(200, json=pages[request.url.params.get("before")])

    requests = _mock_client(monkeypatch, handler)
    dupes = asyncio.run(Vultu(CONFIG).search_existing(Meta(category="TV", tmdb=12, season="S02")))

    assert len(requests) == 2
    assert dupes[0]["files"] == ["Fictional.Show.S02E01.mkv", "Fictional.Show.S02E02.mkv"]
    assert dupes[0]["link"] is None
    assert dupes[1] == {"name": "Fictional.Show.S02.2160p.BluRay.x265-OTHER", "size": 2000, "files": [], "file_count": 0, "link": "https://vultu.org/torrents/5", "id": 5}


def test_search_existing_omits_season_for_multi_season_packs(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "season" not in request.url.params
        return httpx.Response(200, json={"releases": [], "next": None})

    _mock_client(monkeypatch, handler)
    assert asyncio.run(Vultu(CONFIG).search_existing(Meta(category="TV", tmdb=12, season="S01-S03"))) == []


def test_search_existing_raises_problem_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"status": 401, "detail": "Token inválido.", "code": "api.invalid_token"})

    _mock_client(monkeypatch, handler)
    with pytest.raises(RuntimeError, match=r"api\.invalid_token"):
        asyncio.run(Vultu(CONFIG).search_existing(Meta(category="MOVIE", tmdb=1)))


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"category": "MOVIE", "tmdb": 1, "screens": 3}, True),
        ({"category": "MOVIE", "tmdb": 1, "screens": 2}, False),
        ({"category": "TV", "screens": 4}, False),
        ({"category": "GAME", "screens": 0}, False),
        ({"category": "GAME", "igdb_id": 7, "screens": 0}, True),
    ],
)
def test_additional_checks(values: dict[str, Any], expected: bool) -> None:
    assert asyncio.run(Vultu(CONFIG).get_additional_checks(Meta(name="Fictional Film 2001 1080p WEB-DL-NOGRP", **values))) is expected


def test_name_matches_capybarabr() -> None:
    meta = Meta(
        category="TV",
        name="Fictional Show 2026 S01 1080p WEB-DL DD+ 5.1 H.264-FAKEGRP",
        title="Fictional Show",
        year=2026,
        tag="-FAKEGRP",
        audio_languages=["Portuguese", "English"],
        dual_audio=True,
    )

    expected = asyncio.run(CapybaraBR({"TRACKERS": {}}).get_name(meta))["name"]

    assert asyncio.run(Vultu(CONFIG).get_name(meta)) == expected.strip()
    assert "2026" not in expected


def test_upload_data_limits_screenshots_and_flags_anime(tmp_path: Path) -> None:
    (tmp_path / "tmp" / "abc").mkdir(parents=True)
    (tmp_path / "tmp" / "abc" / "MEDIAINFO_CLEANPATH.txt").write_text("General\nFormat : Matroska\n", encoding="utf-8")
    images = [{"raw_url": f"https://img.example/{index}.png"} for index in range(8)] + [{"raw_url": "http://img.example/insecure.png"}]
    meta = Meta(category="MOVIE", base_dir=str(tmp_path), uuid="abc", name="Fictional Film 2001", anime=True, anon=True, image_list=images)

    data = asyncio.run(Vultu(CONFIG).get_data(meta, "tmdb:movie:1"))

    assert data["screenshots"] == [f"https://img.example/{index}.png" for index in range(6)]
    assert data["anime"] == "true"
    assert data["anonymous"] == "true"
    assert data["mediainfo"].startswith("General")
    assert asyncio.run(Vultu(CONFIG).get_data(Meta(category="GAME", base_dir=str(tmp_path), uuid="abc", anime=True), "igdb:1"))["anime"] == "false"


def test_bdmv_sends_bdinfo_as_mediainfo(tmp_path: Path) -> None:
    (tmp_path / "tmp" / "abc").mkdir(parents=True)
    (tmp_path / "tmp" / "abc" / "BD_SUMMARY_00.txt").write_text("Disc Title: Fictional Film\n", encoding="utf-8")
    meta = Meta(category="MOVIE", base_dir=str(tmp_path), uuid="abc", is_disc="BDMV")

    assert asyncio.run(Vultu(CONFIG).get_mediainfo(meta)) == "Disc Title: Fictional Film\n"


def test_upload_posts_form_and_downloads_registered_torrent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "tmp" / "abc").mkdir(parents=True)
    (tmp_path / "tmp" / "abc" / "MEDIAINFO_CLEANPATH.txt").write_text("General\n", encoding="utf-8")
    meta = Meta(
        category="MOVIE",
        base_dir=str(tmp_path),
        uuid="abc",
        name="Fictional Film 2001 1080p WEB-DL-FAKEGRP",
        tag="-FAKEGRP",
        tmdb=1,
        image_list=[{"raw_url": f"https://img.example/{index}.png"} for index in range(3)],
    )
    torrent_path = tmp_path / "tmp" / "abc" / "[VULTU].torrent"

    async def fake_create(_meta: Meta, tracker: str, _source_flag: str, **_kwargs: Any) -> None:
        assert tracker == "VULTU"
        torrent_path.write_bytes(b"d4:infod4:name4:testee")

    downloads: list[str] = []

    async def fake_download(_meta: Meta, tracker: str, headers: dict[str, str] | None = None, downurl: str = "", **_kwargs: Any) -> str:
        assert tracker == "VULTU"
        assert headers is not None
        assert headers["Authorization"] == "Bearer test-token"
        downloads.append(downurl)
        return str(torrent_path)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v1/torrents"
        body = request.content
        assert b'name="work"\r\n\r\ntmdb:movie:1' in body
        assert body.count(b'name="screenshots"') == 3
        assert b'name="torrent"; filename="Fictional Film 2001 1080p WEB-DL-FAKEGRP.torrent"' in body
        return httpx.Response(201, json={"id": 412, "url": "https://vultu.org/torrents/412", "downloadUrl": "https://vultu.org/api/v1/torrents/412/download", "pending": True})

    _mock_client(monkeypatch, handler)
    tracker = Vultu(CONFIG)
    monkeypatch.setattr(tracker.common, "create_torrent_for_upload", fake_create)
    monkeypatch.setattr(tracker.common, "download_tracker_torrent", fake_download)

    assert asyncio.run(tracker.upload(meta)) is True
    assert meta.tracker_status["VULTU"]["torrent_id"] == "412"
    assert meta.tracker_status["VULTU"]["status_message"] == "Uploaded; pending moderation."
    assert downloads == ["https://vultu.org/api/v1/torrents/412/download"]


def test_upload_reports_problem_detail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "tmp" / "abc").mkdir(parents=True)
    meta = Meta(category="GAME", base_dir=str(tmp_path), uuid="abc", name="Fictional Game", igdb_id=3)

    async def fake_create(*_args: Any, **_kwargs: Any) -> None:
        (tmp_path / "tmp" / "abc" / "[VULTU].torrent").write_bytes(b"de")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"status": 409, "detail": "Já publicado.", "code": "torrent.duplicate_info_hash"})

    _mock_client(monkeypatch, handler)
    tracker = Vultu(CONFIG)
    monkeypatch.setattr(tracker.common, "create_torrent_for_upload", fake_create)

    assert asyncio.run(tracker.upload(meta)) is False
    assert "torrent.duplicate_info_hash" in meta.tracker_status["VULTU"]["status_message"]


def test_upload_without_work_fails_before_posting(monkeypatch: pytest.MonkeyPatch) -> None:
    requests = _mock_client(monkeypatch, lambda _request: httpx.Response(500))
    meta = Meta(category="MOVIE", name="Fictional Film")

    assert asyncio.run(Vultu(CONFIG).upload(meta)) is False
    assert requests == []
    assert "TMDB/IGDB" in meta.tracker_status["VULTU"]["status_message"]
