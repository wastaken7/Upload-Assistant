# ruff: noqa: S101
import asyncio
import runpy
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image
from torf import Torrent

from src.meta import Meta
from src.trackers import fileiplay as fileiplay_module
from src.trackers.fileiplay import FileIPlay
from src.trackersetup import STATIC_AUTH_TYPES, TrackerSetup, tracker_class_map

CONFIG = {"DEFAULT": {}, "TRACKERS": {"FILEIPLAY": {"api_key": "test-token", "torznab_api_key": "test-integration-key", "anon": False}}}


def _image(size: tuple[int, int], image_format: str = "PNG") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size).save(buffer, format=image_format)
    return buffer.getvalue()


def _torrent_bytes(tmp_path: Path) -> tuple[bytes, str]:
    content = tmp_path / "Fictional.Film.2001.mkv"
    content.write_bytes(b"x" * 1024)
    torrent = Torrent(path=content, trackers=["https://tracker.example/announce/passkey"], private=True)
    torrent.generate()
    return torrent.dump(), str(torrent.infohash)


def _torznab(items: list[dict[str, str]]) -> str:
    body = "".join(
        f"<item><title>{item['title']}</title><guid>{item['guid']}</guid><comments>{item['guid']}</comments>"
        f"<link>{item.get('link', '')}</link>"
        f'<torznab:attr name="size" value="{item.get("size", "1000")}"/>'
        f'<torznab:attr name="files" value="{item.get("files", "1")}"/>'
        f'<torznab:attr name="infohash" value="{item.get("infohash", "")}"/></item>'
        for item in items
    )
    return f'<?xml version="1.0"?><rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed"><channel>{body}</channel></rss>'


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

    monkeypatch.setattr(fileiplay_module.httpx, "AsyncClient", factory)
    return requests


def test_registration_and_config() -> None:
    example_config = runpy.run_path(str(Path(__file__).resolve().parents[1] / "data" / "example_config.py"))["config"]
    assert tracker_class_map["FILEIPLAY"] is FileIPlay
    assert STATIC_AUTH_TYPES["FILEIPLAY"] == "other_api"
    assert example_config["TRACKERS"]["FILEIPLAY"]["cli_alias"] == "FIP"
    assert {"api_key", "torznab_api_key"} <= example_config["TRACKERS"]["FILEIPLAY"].keys()


@pytest.mark.parametrize(("category", "kept"), [("MOVIE", True), ("TV", True), ("GAME", True), ("MUSIC", True), ("XXX", True), ("BOOK", False)])
def test_supported_categories(category: str, kept: bool) -> None:
    meta = Meta(category=category, trackers=["FILEIPLAY"])
    TrackerSetup(CONFIG).filter_unsupported_trackers(meta)
    assert (meta.trackers == ["FILEIPLAY"]) is kept


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"category": "MOVIE", "resolution": "1080p", "type": "WEBDL"}, 11),
        ({"category": "MOVIE", "resolution": "1080p", "type": "REMUX", "source": "BluRay"}, 11),
        ({"category": "MOVIE", "resolution": "2160p", "type": "ENCODE"}, 31),
        ({"category": "MOVIE", "resolution": "1080p", "type": "DISC", "is_disc": "BDMV"}, 5),
        ({"category": "MOVIE", "resolution": "480p", "type": "DISC", "is_disc": "DVD", "sd": 1}, 9),
        ({"category": "MOVIE", "resolution": "480p", "type": "DVDRIP", "sd": 1}, 9),
        ({"category": "MOVIE", "resolution": "480p", "type": "WEBRIP", "sd": 1}, 24),
        ({"category": "MOVIE", "resolution": "1080p", "anime": True}, 1),
        ({"category": "TV", "resolution": "1080p"}, 13),
        ({"category": "TV", "resolution": "576p", "sd": 1}, 20),
        ({"category": "TV", "is_sports": True}, 42),
        ({"category": "XXX"}, 27),
        ({"category": "MUSIC"}, 28),
        ({"category": "GAME"}, 30),
    ],
)
def test_category_id(values: dict[str, Any], expected: int) -> None:
    assert FileIPlay(CONFIG).get_category_id(Meta(**values)) == expected


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (
            {
                "category": "MOVIE",
                "name": "Fictional Film 2001 2160p BluRay DD+ 5.1 DV HDR x265-FAKEGRP",
                "audio": "DD+ 5.1",
                "hdr": "DV HDR",
                "resolution": "2160p",
                "tag": "-FAKEGRP",
            },
            "Fictional.Film.2001.2160p.DV.HDR.BluRay.x265.DDP5.1-FAKEGRP",
        ),
        (
            {
                "category": "TV",
                "name": "Fictional Show S01E02 1080p AMZN WEB-DL Dual-Audio AAC 2.0 H.264-NOGROUP",
                "audio": "Dual-Audio AAC 2.0",
                "resolution": "1080p",
                "tag": "-NOGROUP",
            },
            "Fictional.Show.S01E02.1080p.AMZN.WEB-DL.H.264.AAC2.0",
        ),
        (
            {
                "category": "MOVIE",
                "name": "Café & Friends: Part II 1999 1080p BluRay REMUX AVC DTS-HD MA 5.1-FAKEGRP",
                "audio": "DTS-HD MA 5.1",
                "resolution": "1080p",
                "tag": "-FAKEGRP",
            },
            "Cafe.and.Friends.Part.II.1999.1080p.BluRay.REMUX.AVC.DTS-HD.MA.5.1-FAKEGRP",
        ),
        ({"category": "MOVIE", "name": "ignored", "scene": True, "scene_name": "Fictional.Film.2001.1080p.WEB.h264-FAKEGRP"}, "Fictional.Film.2001.1080p.WEB.h264-FAKEGRP"),
        ({"category": "MOVIE", "name": "ignored", "manual_name": "Fictional Film's Cut 2001"}, "Fictional.Films.Cut.2001"),
        ({"category": "MUSIC", "name": "Fictional Artist - Fictional Album (2020) [FLAC]"}, "Fictional.Artist.Fictional.Album.2020.FLAC"),
    ],
)
def test_name_follows_naming_guide(values: dict[str, Any], expected: str) -> None:
    assert asyncio.run(FileIPlay(CONFIG).get_name(Meta(**values))) == expected


def test_data_sends_ids_matching_the_category(tmp_path: Path) -> None:
    meta = Meta(
        category="TV",
        base_dir=str(tmp_path),
        uuid="abc",
        name="Fictional Show S02E03 1080p WEB-DL",
        resolution="1080p",
        tmdb_id=101,
        tvdb_id=202,
        imdb_id=1234567,
        season="S02",
        season_int=2,
        episode_int=3,
        genres=["Drama", "Comedy"],
        artwork_url="https://img.example/poster.jpg",
        anon=True,
    )

    data = asyncio.run(FileIPlay(CONFIG).get_data(meta, attach_screenshots=False, preview=True))

    assert data == {
        "category_id": "13",
        "name": "Fictional.Show.S02E03.1080p.WEB-DL",
        "anon": "1",
        "tmdbid": "101",
        "tmdb_type": "tv",
        "tvdbid": "202",
        "imdb_url": "https://www.imdb.com/title/tt1234567/",
        "genre": "Drama, Comedy",
        "season": "2",
        "episode": "3",
    }


def test_data_without_tmdb_category_sends_poster_and_no_ids(tmp_path: Path) -> None:
    meta = Meta(category="GAME", base_dir=str(tmp_path), uuid="abc", name="Fictional Game", tmdb_id=5, artwork_url="https://img.example/cover.jpg", steam_url="https://store.steampowered.com/app/4242/Fictional_Game/")

    data = asyncio.run(FileIPlay(CONFIG).get_data(meta, attach_screenshots=False, preview=True))

    assert data["category_id"] == "30"
    assert data["poster"] == "https://img.example/cover.jpg"
    assert data["steamid"] == "4242"
    assert "tmdbid" not in data
    assert "tmdb_type" not in data


def test_data_sends_poster_for_movie_without_tmdb(tmp_path: Path) -> None:
    meta = Meta(category="MOVIE", base_dir=str(tmp_path), uuid="abc", name="Fictional Film 2001", resolution="1080p", artwork_url="https://img.example/poster.jpg")

    data = asyncio.run(FileIPlay(CONFIG).get_data(meta, attach_screenshots=False, preview=True))

    assert data["poster"] == "https://img.example/poster.jpg"
    assert "tmdb_type" not in data


def test_bdmv_sends_bdinfo_as_mediainfo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work_dir = tmp_path / "tmp" / "abc"
    work_dir.mkdir(parents=True)
    meta = Meta(category="MOVIE", base_dir=str(tmp_path), uuid="abc", is_disc="BDMV")
    tracker = FileIPlay(CONFIG)

    async def playlist_mediainfo(_meta: Meta) -> str:
        return "General\\nFormat : BDAV\\n"

    monkeypatch.setattr(tracker.common, "get_bdmv_mediainfo", playlist_mediainfo)
    # Without a BDInfo summary, the main playlist's MediaInfo is sent instead.
    assert asyncio.run(tracker.get_mediainfo(meta)) == "General\\nFormat : BDAV\\n"

    (work_dir / "BD_SUMMARY_00.txt").write_text("Disc Title: Fictional Film\n", encoding="utf-8")
    assert asyncio.run(tracker.get_mediainfo(meta)) == "Disc Title: Fictional Film\n"


def test_images_keep_only_supported_screenshots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = []
    for name, size, image_format in (("small", (64, 36), "PNG"), ("photo", (64, 36), "JPEG"), ("huge", (4097, 10), "PNG"), ("gif", (8, 8), "GIF")):
        path = tmp_path / f"{name}.img"
        path.write_bytes(_image(size, image_format))
        paths.append(path)
    monkeypatch.setattr(fileiplay_module, "manifest_files", lambda *_args: paths)

    images = asyncio.run(FileIPlay(CONFIG).get_images(Meta(base_dir=str(tmp_path), uuid="abc")))

    assert [(name, content_type) for name, _content, content_type in images] == [("small.png", "image/png"), ("photo.jpg", "image/jpeg")]


def test_search_existing_parses_torznab(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/torznab/api"
        assert request.url.params["t"] == "search"
        assert request.url.params["q"] == "Fictional Film 2001"
        assert request.url.params["apikey"] == "test-integration-key"
        assert "Authorization" not in request.headers
        items = [{"title": "Fictional.Film.2001.1080p.WEB.h264-FAKEGRP", "guid": "https://fileiplay.org/torrents/77/fictional", "link": "https://fileiplay.org/dl?apikey=secret", "size": "2048", "files": "3"}]
        return httpx.Response(200, text=_torznab(items))

    _mock_client(monkeypatch, handler)
    dupes = asyncio.run(FileIPlay(CONFIG).search_existing(Meta(category="MOVIE", title="Fictional Film", year=2001)))

    assert dupes == [
        {
            "name": "Fictional.Film.2001.1080p.WEB.h264-FAKEGRP",
            "size": 2048,
            "files": [],
            "file_count": 3,
            "link": "https://fileiplay.org/torrents/77/fictional",
            "id": "77",
        }
    ]


def test_search_existing_reports_torznab_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_client(monkeypatch, lambda _request: httpx.Response(200, text='<error code="100" description="Invalid API key"/>'))
    with pytest.raises(RuntimeError, match="Invalid API key"):
        asyncio.run(FileIPlay(CONFIG).search_existing(Meta(category="MOVIE", title="Fictional Film")))


def test_search_existing_requires_integration_key() -> None:
    config = {"DEFAULT": {}, "TRACKERS": {"FILEIPLAY": {"api_key": "test-token"}}}
    with pytest.raises(RuntimeError, match="torznab_api_key"):
        asyncio.run(FileIPlay(config).search_existing(Meta(category="MOVIE", title="Fictional Film")))


def _upload_meta(tmp_path: Path) -> Meta:
    work_dir = tmp_path / "tmp" / "abc"
    work_dir.mkdir(parents=True)
    (work_dir / "MEDIAINFO_CLEANPATH.txt").write_text("General\n", encoding="utf-8")
    return Meta(
        category="MOVIE",
        base_dir=str(tmp_path),
        uuid="abc",
        name="Fictional Film 2001 1080p WEB-DL H.264-FAKEGRP",
        resolution="1080p",
        type="WEBDL",
        tag="-FAKEGRP",
        tmdb=1,
    )


def _prepare_upload(tracker: FileIPlay, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    torrent_path = tmp_path / "tmp" / "abc" / "[FILEIPLAY].torrent"

    async def fake_create(_meta: Meta, tracker_name: str, source_flag: str, **_kwargs: Any) -> None:
        assert (tracker_name, source_flag) == ("FILEIPLAY", "FileIPlay")
        torrent_path.write_bytes(b"d4:infod4:name4:testee")

    async def fake_description(_meta: Meta, attach: bool) -> str:
        assert attach is True
        return "[b]Fictional description[/b]"

    async def no_sleep(_seconds: float) -> None:
        return None

    screenshot = tmp_path / "shot.png"
    screenshot.write_bytes(_image((64, 36)))
    monkeypatch.setattr(tracker.common, "create_torrent_for_upload", fake_create)
    monkeypatch.setattr(tracker, "generate_description", fake_description)
    monkeypatch.setattr(fileiplay_module, "manifest_files", lambda *_args: [screenshot])
    monkeypatch.setattr(fileiplay_module.asyncio, "sleep", no_sleep)
    return torrent_path


def test_upload_posts_documented_fields_and_downloads_published_torrent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    meta = _upload_meta(tmp_path)
    published, info_hash = _torrent_bytes(tmp_path)
    searches: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/torrents":
            assert request.method == "POST"
            assert request.headers["Authorization"] == "Bearer test-token"
            body = request.content
            for expected in (
                b'name="category_id"\r\n\r\n11',
                b'name="name"\r\n\r\nFictional.Film.2001.1080p.WEB-DL.H.264-FAKEGRP',
                b'name="anon"\r\n\r\n0',
                b'name="tmdbid"\r\n\r\n1',
                b'name="tmdb_type"\r\n\r\nmovie',
                b'name="description"\r\n\r\n[b]Fictional description[/b]',
                b'name="mediainfo"\r\n\r\nGeneral',
                b'name="torrent"; filename="Fictional.Film.2001.1080p.WEB-DL.H.264-FAKEGRP.torrent"',
                b'name="images[]"; filename="shot.png"',
            ):
                assert expected in body
            data = {"id": 123, "name": "Fictional.Film.2001.1080p.WEB-DL.H.264-FAKEGRP", "info_hash": info_hash.upper(), "url": "https://fileiplay.org/torrents/123/fictional"}
            return httpx.Response(201, json={"data": data, "meta": {"warnings": []}})
        if request.url.path == "/torznab/api":
            searches.append(request.url.params["q"])
            # The first search runs before the new torrent is listed.
            if len(searches) == 1:
                return httpx.Response(200, text=_torznab([]))
            items = [
                {"title": "Other", "guid": "https://fileiplay.org/torrents/5/other", "link": "https://fileiplay.org/dl/5"},
                {"title": "Fictional", "guid": "https://fileiplay.org/torrents/123/fictional", "link": "https://fileiplay.org/dl/123", "infohash": info_hash},
            ]
            return httpx.Response(200, text=_torznab(items))
        assert request.url.path == "/dl/123"
        return httpx.Response(200, content=published)

    _mock_client(monkeypatch, handler)
    tracker = FileIPlay(CONFIG)
    torrent_path = _prepare_upload(tracker, monkeypatch, tmp_path)

    assert asyncio.run(tracker.upload(meta)) is True
    assert meta.tracker_status["FILEIPLAY"]["torrent_id"] == "123"
    assert meta.tracker_status["FILEIPLAY"]["status_message"] == "Uploaded."
    assert searches == ["Fictional.Film.2001.1080p.WEB-DL.H.264-FAKEGRP"] * 2
    assert torrent_path.read_bytes() == published


def test_upload_fails_when_published_torrent_is_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    meta = _upload_meta(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/torrents":
            return httpx.Response(201, json={"data": {"id": 123, "info_hash": "abc", "url": "https://fileiplay.org/torrents/123/fictional"}, "meta": {"warnings": ["TMDB lookup failed"]}})
        return httpx.Response(200, text=_torznab([]))

    requests = _mock_client(monkeypatch, handler)
    tracker = FileIPlay(CONFIG)
    torrent_path = _prepare_upload(tracker, monkeypatch, tmp_path)

    assert asyncio.run(tracker.upload(meta)) is False
    assert len(requests) == 4
    status = meta.tracker_status["FILEIPLAY"]["status_message"]
    assert status.startswith("data error: Uploaded")
    assert "https://fileiplay.org/torrents/123/fictional" in status
    assert status.endswith("Warnings: TMDB lookup failed")
    # The placeholder-announce torrent must not be left behind to seed.
    assert not torrent_path.exists()


def test_upload_reports_validation_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    meta = _upload_meta(tmp_path)
    error = {"error": {"code": "validation_failed", "message": "The supplied fields are invalid.", "fields": {"category_id": ["The selected category id is invalid."]}}}
    _mock_client(monkeypatch, lambda _request: httpx.Response(422, json=error))
    tracker = FileIPlay(CONFIG)
    _prepare_upload(tracker, monkeypatch, tmp_path)

    assert asyncio.run(tracker.upload(meta)) is False
    assert meta.tracker_status["FILEIPLAY"]["status_message"] == (
        "data error: HTTP 422: The supplied fields are invalid. (validation_failed) - category_id: The selected category id is invalid."
    )


def test_additional_checks_require_both_keys() -> None:
    meta = Meta(category="MOVIE", name="Fictional Film")
    assert asyncio.run(FileIPlay({"TRACKERS": {"FILEIPLAY": {}}}).get_additional_checks(meta)) is False
    assert asyncio.run(FileIPlay({"TRACKERS": {"FILEIPLAY": {"api_key": "test-token"}}}).get_additional_checks(meta)) is False
    assert asyncio.run(FileIPlay(CONFIG).get_additional_checks(meta)) is True


@pytest.mark.parametrize(("tracker_config", "expected"), [({}, False), ({"add_logo": False}, False), ({"add_logo": True}, True), ({"add_logo": "true"}, True)])
def test_description_leaves_out_logo_unless_enabled(monkeypatch: pytest.MonkeyPatch, tracker_config: dict[str, Any], expected: bool) -> None:
    captured: dict[str, Any] = {}

    async def fake_generator(_self: Any, _meta: Meta, **kwargs: Any) -> str:
        captured.update(kwargs)
        return ""

    monkeypatch.setattr(fileiplay_module.DescriptionBuilder, "general_description_generator", fake_generator)
    config = {"DEFAULT": {"add_logo": True}, "TRACKERS": {"FILEIPLAY": {**CONFIG["TRACKERS"]["FILEIPLAY"], **tracker_config}}}

    asyncio.run(FileIPlay(config).generate_description(Meta(category="MOVIE", name="Fictional Film"), attach_screenshots=False))

    assert captured["logo"] is expected


def test_description_drops_image_resizes() -> None:
    builder = fileiplay_module.DescriptionBuilder("FILEIPLAY", CONFIG)
    description = "[url=https://img.example/view/1][img=350]https://img.example/1.png[/img][/url]"

    assert builder.tracker_specific_formats("FILEIPLAY", description) == "[url=https://img.example/view/1][img]https://img.example/1.png[/img][/url]"
