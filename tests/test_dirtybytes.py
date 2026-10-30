# ruff: noqa: S101
import asyncio
import runpy
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image

from src.meta import Meta
from src.trackers import dirtybytes as dirtybytes_module
from src.trackers.dirtybytes import DirtyBytes
from src.trackersetup import STATIC_AUTH_TYPES, TrackerSetup, tracker_class_map

CONFIG = {"DEFAULT": {}, "TRACKERS": {"DIRTYBYTES": {"api_key": "test-key", "anon": False}}}


def _png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (4, 4)).save(buffer, format="PNG")
    return buffer.getvalue()


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

    monkeypatch.setattr(dirtybytes_module.httpx, "AsyncClient", factory)
    return requests


def test_registration_and_config() -> None:
    example_config = runpy.run_path(str(Path(__file__).resolve().parents[1] / "data" / "example_config.py"))["config"]
    assert tracker_class_map["DIRTYBYTES"] is DirtyBytes
    assert STATIC_AUTH_TYPES["DIRTYBYTES"] == "other_api"
    assert example_config["TRACKERS"]["DIRTYBYTES"]["cli_alias"] == "DB"


@pytest.mark.parametrize(("category", "kept"), [("XXX", True), ("MOVIE", False), ("TV", False)])
def test_supported_categories(category: str, kept: bool) -> None:
    meta = Meta(category=category, trackers=["DIRTYBYTES"])
    TrackerSetup(CONFIG).filter_unsupported_trackers(meta)
    assert (meta.trackers == ["DIRTYBYTES"]) is kept


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"basename_no_ext": "Fakestudio.26.01.02.Some.Scene.XXX.1080p", "resolution": "1080p"}, 9),
        ({"basename_no_ext": "Fakestudio.26.01.02.Some.Scene.XXX.720p", "resolution": "720p"}, 8),
        ({"basename_no_ext": "Fakestudio.Some.Scene.XXX.480p", "resolution": "480p", "sd": 1}, 7),
        ({"basename_no_ext": "Fakestudio.Some.Scene.XXX.2160p", "resolution": "2160p"}, 11),
        ({"basename_no_ext": "Fakestudio.Some.Scene.XXX", "resolution": "OTHER", "video_height": 1600}, 10),
        ({"basename_no_ext": "Fakestudio.Some.Movie.XXX.1080p", "resolution": "1080p"}, 3),
        ({"basename_no_ext": "Fakestudio.Some.Title.XXX", "resolution": "OTHER", "is_disc": "DVD", "sd": 1}, 1),
        ({"basename_no_ext": "Fakestudio.Some.Scene.XXX.VR180", "resolution": "OTHER", "video_height": 2880}, 22),
        ({"basename_no_ext": "Fakestudio.Some.Scene.XXX", "keywords": ["VR"], "resolution": "OTHER", "video_height": 4096}, 24),
        ({"basename_no_ext": "Fakestudio.Some.Movie.XXX.VR", "resolution": "2160p"}, 15),
        ({"basename_no_ext": "Fakestudio.SiteRip.XXX.1080p", "resolution": "1080p"}, 26),
    ],
)
def test_category_id(values: dict[str, Any], expected: int) -> None:
    assert DirtyBytes(CONFIG).get_category_id(Meta(category="XXX", **values)) == expected


def test_search_existing_uses_dupe_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/torrents/dupe-search"
        assert request.url.params["name"] == "Fakestudio.26.01.02.Some.Scene.XXX.1080p"
        assert request.headers["X-API-KEY"] == "test-key"
        return httpx.Response(200, json={"data": [{"id": 4, "name": "Fakestudio.26.01.02.Some.Scene.XXX.1080p", "size": 10, "numfiles": 1}, {"id": 5}]})

    _mock_client(monkeypatch, handler)
    dupes = asyncio.run(DirtyBytes(CONFIG).search_existing(Meta(category="XXX", basename_no_ext="Fakestudio.26.01.02.Some.Scene.XXX.1080p")))

    assert dupes == [
        {
            "id": 4,
            "name": "Fakestudio.26.01.02.Some.Scene.XXX.1080p",
            "size": 10,
            "files": [],
            "file_count": 1,
            "link": "https://dirtybytes.net/torrent/4",
            "download": "https://dirtybytes.net/api/v1/torrents/download/4",
        }
    ]


def test_search_existing_raises_on_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_client(monkeypatch, lambda _request: httpx.Response(401, json={"message": "Invalid API key"}))
    with pytest.raises(RuntimeError, match="Invalid API key"):
        asyncio.run(DirtyBytes(CONFIG).search_existing(Meta(category="XXX", basename_no_ext="Fakestudio.Scene.XXX")))


def _upload_meta(tmp_path: Path) -> Meta:
    work_dir = tmp_path / "tmp" / "abc"
    (work_dir / "screenshots").mkdir(parents=True)
    (work_dir / "MEDIAINFO_CLEANPATH.txt").write_text("General\n", encoding="utf-8")
    cover = tmp_path / "cover.png"
    cover.write_bytes(_png())
    return Meta(
        category="XXX",
        base_dir=str(tmp_path),
        uuid="abc",
        basename_no_ext="Fakestudio.26.01.02.Some.Scene.XXX.1080p",
        resolution="1080p",
        publisher="Fakestudio",
        manual_cast=["Performer One", "Performer Two"],
        keywords=["fansite", "pov"],
        audio_languages=["English"],
        year=2026,
        artwork_path=str(cover),
    )


def _prepare_upload(tracker: DirtyBytes, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, downloads: list[str]) -> None:
    async def fake_create(_meta: Meta, tracker_name: str, source_flag: str, **_kwargs: Any) -> None:
        assert (tracker_name, source_flag) == ("DIRTYBYTES", "DirtyBytes")
        (tmp_path / "tmp" / "abc" / "[DIRTYBYTES].torrent").write_bytes(b"d4:infod4:name4:testee")

    async def fake_description(_meta: Meta, _attach: bool) -> str:
        return "[b]Fictional description[/b]"

    async def fake_download(_meta: Meta, _tracker: str, **kwargs: Any) -> str:
        downloads.append(kwargs["downurl"])
        return "downloaded"

    monkeypatch.setattr(tracker.common, "create_torrent_for_upload", fake_create)
    monkeypatch.setattr(tracker.common, "download_tracker_torrent", fake_download)
    monkeypatch.setattr(tracker, "generate_description", fake_description)
    monkeypatch.setattr(dirtybytes_module, "manifest_files", lambda *_args: [])


def test_upload_posts_documented_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    meta = _upload_meta(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v1/torrents/upload"
        assert request.headers["X-API-KEY"] == "test-key"
        body = request.content
        for expected in (
            b'name="category"\r\n\r\n9',
            b'name="anonymousUpload"\r\n\r\n0',
            b'name="nfo"\r\n\r\n[b]Fictional description[/b]',
            b'name="studio"\r\n\r\nFakestudio',
            b'name="performers"\r\n\r\nPerformer One, Performer Two',
            b'name="content_tags"\r\n\r\nfansite, pov',
            b'name="language"\r\n\r\nenglish',
            b'name="release_year"\r\n\r\n2026',
            b'name="mediainfo"\r\n\r\nGeneral',
            b'name="unrar"\r\n\r\n0',
            b'name="file"; filename="Fakestudio.26.01.02.Some.Scene.XXX.1080p.torrent"',
            b'name="images[]"; filename="cover.png"',
        ):
            assert expected in body
        return httpx.Response(200, json={"id": 12, "name": "x", "message": "Upload successful", "images": []})

    _mock_client(monkeypatch, handler)
    tracker = DirtyBytes(CONFIG)
    downloads: list[str] = []
    _prepare_upload(tracker, monkeypatch, tmp_path, downloads)

    assert asyncio.run(tracker.upload(meta)) is True
    assert meta.tracker_status["DIRTYBYTES"]["torrent_id"] == "12/"
    assert downloads == ["https://dirtybytes.net/api/v1/torrents/download/12"]


def test_upload_warns_when_torrent_download_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    meta = _upload_meta(tmp_path)
    _mock_client(monkeypatch, lambda _request: httpx.Response(200, json={"id": 12, "message": "Upload successful"}))
    tracker = DirtyBytes(CONFIG)
    downloads: list[str] = []
    _prepare_upload(tracker, monkeypatch, tmp_path, downloads)

    async def failed_download(_meta: Meta, _tracker: str, **kwargs: Any) -> None:
        downloads.append(kwargs["downurl"])

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(tracker.common, "download_tracker_torrent", failed_download)
    monkeypatch.setattr(dirtybytes_module.asyncio, "sleep", no_sleep)

    assert asyncio.run(tracker.upload(meta)) is True
    assert len(downloads) == 4
    assert "https://dirtybytes.net/torrent/12/" in meta.tracker_status["DIRTYBYTES"]["status_message"]


def test_upload_reports_duplicate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    meta = _upload_meta(tmp_path)
    _mock_client(monkeypatch, lambda _request: httpx.Response(409, json={"error": "Duplicate", "torrent_id": 7}))
    tracker = DirtyBytes(CONFIG)
    downloads: list[str] = []
    _prepare_upload(tracker, monkeypatch, tmp_path, downloads)

    assert asyncio.run(tracker.upload(meta)) is False
    assert "torrent/7/" in meta.tracker_status["DIRTYBYTES"]["status_message"]
    assert downloads == []
