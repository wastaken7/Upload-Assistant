# ruff: noqa: S101
import asyncio
import json
import runpy
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from PIL import Image

from src.meta import Meta
from src.trackers import amigosshare as asc_module
from src.trackers.amigosshare import AmigosShare, find_options, format_description, parse_page, site_choices
from src.trackersetup import STATIC_AUTH_TYPES, TrackerSetup, tracker_class_map

CONFIG: dict[str, Any] = {"DEFAULT": {}, "TRACKERS": {"AMIGOSSHARE": {"announce_url": "https://tracker.example/announce/passkey", "anon": False}}}


def _attribute(kind: str, names: list[str], *, required: bool = True, multiple: bool = False, start: int = 100) -> dict[str, Any]:
    return {"type": kind, "label": kind, "required": required, "multiple": multiple, "options": [{"id": start + i, "name": name} for i, name in enumerate(names)]}


VIDEO_PROFILE: dict[str, Any] = {
    "key": "filmes",
    "imdb": True,
    "dimensions": True,
    "trailer": True,
    "subtitle": True,
    "subtitleWhen": [301, 302],
    "coverRequired": True,
    "screenshotsMin": 2,
    "screenshotsMax": 6,
    "mediainfo": True,
    "attributes": [
        _attribute("genre", ["Ação", "Drama", "Ficção Científica"], multiple=True, start=100),
        _attribute("language", ["Inglês", "Japonês", "Português", "Outros"], start=200),
        _attribute("audio_channels", ["Dual-Audio", "Legendado", "Dublado", "Original", "Nacional", "Multi-Audio"], start=301),
        _attribute("resolution", ["WEB-DL", "BD25", "BD50", "Remux", "BD-REMUX"], start=400),
        _attribute("container", ["MKV", "M2TS", "MP4"], start=500),
        _attribute("video_codec", ["H265 - HDR", "H265", "HEVC", "H264", "AVC"], start=600),
        _attribute("audio_codec", ["E-AC-3", "AC3", "DTS-HD-MA"], start=700),
    ],
}
FORM_PROPS: dict[str, Any] = {
    "categories": [{"id": 4, "name": "Filmes", "slug": "filmes", "type": "filmes", "children": []}],
    "profiles": {"filmes": VIDEO_PROFILE, "series": {**VIDEO_PROFILE, "key": "series"}},
    "limits": {"torrentKb": 102400, "imageKb": 51200},
}


def _page_html(component: str, props: dict[str, Any]) -> str:
    data = json.dumps({"component": component, "props": props, "url": "/", "version": "v1"})
    return f'<html><body><script data-page="app" type="application/json">{data}</script><div id="app"></div></body></html>'


def _png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (64, 36)).save(buffer, format="PNG")
    return buffer.getvalue()


def _movie_meta(tmp_path: Path, **values: Any) -> Meta:
    defaults: dict[str, Any] = {
        "category": "MOVIE",
        "base_dir": str(tmp_path),
        "uuid": "release",
        "name": "Fictional Film 2001 1080p WEB-DL DD+ 5.1 H.265-FAKEGRP",
        "title": "Fictional Film",
        "year": 2001,
        "imdb_id": 1234567,
        "imdb_tt": "tt1234567",
        "type": "WEBDL",
        "audio": "DD+ 5.1",
        "video_codec": "HEVC",
        "audio_languages": ["English", "Portuguese"],
        "subtitle_languages": ["Portuguese"],
        "original_language": "en",
        "filelist": [str(tmp_path / "Fictional.Film.2001.mkv")],
        "ua_name": "Upload Assistant",
        "current_version": "v1.0",
    }
    defaults.update(values)
    return Meta(**defaults)


def _tracker(handler: Any) -> tuple[AmigosShare, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    tracker = AmigosShare(CONFIG)
    tracker.session = httpx.AsyncClient(transport=httpx.MockTransport(recording))
    tracker.session.cookies.set("XSRF-TOKEN", "token%3D", domain="amigos-share.club")
    tracker.cookies_loaded = True
    return tracker, requests


def test_registration_and_config() -> None:
    example_config = runpy.run_path(str(Path(__file__).resolve().parents[1] / "data" / "example_config.py"))["config"]
    assert tracker_class_map["AMIGOSSHARE"] is AmigosShare
    assert STATIC_AUTH_TYPES["AMIGOSSHARE"] == "cookies"
    assert example_config["TRACKERS"]["AMIGOSSHARE"]["cli_alias"] == "ASC"


@pytest.mark.parametrize(("category", "kept"), [("MOVIE", True), ("TV", True), ("BOOK", True), ("GAME", True), ("XXX", True), ("MUSIC", False)])
def test_supported_categories(category: str, kept: bool) -> None:
    meta = Meta(category=category, trackers=["AMIGOSSHARE"])
    TrackerSetup(CONFIG).filter_unsupported_trackers(meta)
    assert (meta.trackers == ["AMIGOSSHARE"]) is kept


def test_parse_page_reads_the_inertia_data() -> None:
    page = parse_page(_page_html("torrents/create", {"a": 1}))
    assert page is not None
    assert page["component"] == "torrents/create"
    assert parse_page("<html>login</html>") is None


def test_options_match_without_accents_or_case() -> None:
    attribute = _attribute("genre", ["Ficção Científica", "Ação"])
    assert find_options(attribute, ["acao", "FICCAO CIENTIFICA", "unknown"]) == [101, 100]


def test_site_choices_prefer_imdb_for_language_and_take_the_first_mediainfo_match() -> None:
    lookup = {"genres": ["Drama", "Ficção Científica", "Western"], "language": "Inglês"}
    mediainfo = {"attributes": {"video_codec": ["H265 - HDR 10", "H265", "HEVC"], "language": ["Japonês"], "container": ["MKV"], "unknown": ["X"]}}
    chosen = site_choices(VIDEO_PROFILE, lookup, mediainfo)
    assert chosen == {"genre": [101, 102], "language": [200], "video_codec": [601], "container": [500]}


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({}, "Fictional Film (Original Film)"),
        ({"manual_name": " Custom Title "}, "Custom Title"),
        ({"category": "TV", "season": "S01", "episode": "E02"}, "Fictional Film (Original Film) - S01E02"),
        ({"category": "TV", "season": "S01", "episode": "E02", "tv_pack": True}, "Fictional Film (Original Film) - S01"),
    ],
)
def test_video_names_follow_the_site_title(tmp_path: Path, values: dict[str, Any], expected: str) -> None:
    meta = _movie_meta(tmp_path, **values)
    assert asyncio.run(AmigosShare(CONFIG).get_name(meta, {"title": "Fictional Film (Original Film)"})) == expected


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"category": "BOOK", "author": "Jane Writer", "title": "A Fictional Book"}, "Jane Writer - A Fictional Book"),
        ({"category": "GAME", "title": "Fictional Quest", "platform": "PC", "tag": "-FAKEREL"}, "Fictional Quest [FAKEREL]"),
        ({"category": "GAME", "title": "Fictional Quest", "platform": "PS4", "year": 2019}, "Fictional Quest [2019]"),
        ({"category": "XXX", "title": "Fictional Scene", "publisher": "FakeStudio"}, "FakeStudio - Fictional Scene"),
    ],
)
def test_other_names_follow_rule_6_4(values: dict[str, Any], expected: str) -> None:
    assert asyncio.run(AmigosShare(CONFIG).get_name(Meta(**values))) == expected


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"audio_languages": ["English", "Portuguese"]}, "Dual-Audio"),
        ({"audio_languages": ["English", "Spanish", "Portuguese"]}, "Multi-Audio"),
        ({"audio_languages": ["Portuguese"]}, "Dublado"),
        ({"audio_languages": ["Portuguese"], "original_language": "pt"}, "Nacional"),
        ({"audio_languages": ["English"], "subtitle_languages": ["Portuguese"]}, "Legendado"),
        ({"audio_languages": ["English"], "subtitle_languages": []}, "Original"),
        ({"audio_languages": ["por", "eng"]}, "Dual-Audio"),
        ({"audio_languages": ["eng"], "subtitle_languages": ["pt-BR"]}, "Legendado"),
    ],
)
def test_audio_type(tmp_path: Path, values: dict[str, Any], expected: str) -> None:
    assert AmigosShare(CONFIG).get_audio_channels(_movie_meta(tmp_path, **values)) == expected


def test_release_fills_what_the_site_left_out_and_discs_override_quality(tmp_path: Path) -> None:
    tracker = AmigosShare(CONFIG)
    meta = _movie_meta(tmp_path, is_disc="BDMV", disctype="BD50", genres=["Drama"], type="DISC", filelist=[])
    chosen = {"resolution": [403], "container": [500]}
    attribute_ids = asyncio.run(tracker.choose_attributes(meta, VIDEO_PROFILE, chosen))
    assert attribute_ids is not None
    assert {402, 501, 101, 200, 301, 601, 700} == set(attribute_ids)


def test_unattended_missing_required_field_skips_the_tracker(tmp_path: Path) -> None:
    tracker = AmigosShare(CONFIG)
    meta = _movie_meta(tmp_path, unattended=True, audio="", video_codec="", original_language="", type="")
    assert asyncio.run(tracker.choose_attributes(meta, VIDEO_PROFILE, {})) is None
    assert meta.skipping == "AMIGOSSHARE"


def test_description_keeps_only_site_images_and_supported_tags() -> None:
    description = (
        "[h1]Title[/h1]\n[align=center]Centered[/align]\n[url=https://img.example][img=350]https://img.example/a.png[/img][/url]\n"
        "[img]https://amigos-share.club/storage/torrent-images/a.webp[/img]\n[font=Courier New]text[/font]\n\n\n\n[pre]code[/pre]"
    )
    assert format_description(description, "https://amigos-share.club") == (
        "[size=22][b]Title[/b][/size]\n[center]Centered[/center]\n\n[img]https://amigos-share.club/storage/torrent-images/a.webp[/img]\ntext\n\n[code]code[/code]"
    )


def test_description_sizes_stay_within_site_limits() -> None:
    description = "[size=2]small[/size] [size=14]body[/size] [SIZE=50]huge[/SIZE]"
    assert format_description(description, "https://amigos-share.club") == "[size=8]small[/size] [size=14]body[/size] [size=36]huge[/SIZE]"


def test_search_existing_turns_badges_into_release_terms(tmp_path: Path) -> None:
    props = {
        "torrents": {
            "data": [
                {"id": 7, "name": "Fictional Film (Original Film)", "year": 2001, "size": 1000, "badges": [{"kind": "resolution", "label": "4K"}, {"kind": "source", "label": "WEB-DL"}]}
            ],
            "next_page_url": None,
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["q"] == "tt1234567"
        assert request.url.params["category"] == "4"
        return httpx.Response(200, text=_page_html("torrents/index", props))

    tracker, requests = _tracker(handler)
    dupes = asyncio.run(tracker.search_existing(_movie_meta(tmp_path)))
    assert len(requests) == 1
    assert dupes == [{"name": "Fictional Film (Original Film) 2001 2160p WEB-DL", "size": 1000, "link": "https://amigos-share.club/torrents/7", "id": 7}]


def test_results_without_resolution_read_the_files_of_the_torrent(tmp_path: Path) -> None:
    listing = {"torrents": {"data": [{"id": 8, "name": "Fictional Show - S01", "year": 2020, "size": 5000, "badges": [{"kind": "source", "label": "WEB-DL"}]}]}}
    details = {"files": {"data": [{"path": "Fictional.Show.S01E01.1080p.WEB-DL.mkv"}, {"path": "Fictional.Show.S01E02.1080p.WEB-DL.mkv"}]}, "filesTotal": 8}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/torrents/8":
            return httpx.Response(200, text=_page_html("torrents/show", details))
        return httpx.Response(200, text=_page_html("torrents/index", listing))

    tracker, requests = _tracker(handler)
    dupes = asyncio.run(tracker.search_existing(_movie_meta(tmp_path, category="TV", season="S01", episode="E01")))
    assert [request.url.path for request in requests] == ["/torrents", "/torrents/8"]
    assert dupes[0]["name"] == "Fictional Show - S01 2020 WEB-DL 1080p"
    assert dupes[0]["files"] == ["Fictional.Show.S01E01.1080p.WEB-DL.mkv", "Fictional.Show.S01E02.1080p.WEB-DL.mkv"]
    assert dupes[0]["file_count"] == 8


def test_every_result_without_resolution_is_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    items = [{"id": index, "name": f"Fictional Film {index}", "size": 1000, "badges": []} for index in range(8)]
    monkeypatch.setattr(asc_module.asyncio, "sleep", AsyncMock())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/torrents":
            return httpx.Response(200, text=_page_html("torrents/index", {"torrents": {"data": items}}))
        return httpx.Response(200, text=_page_html("torrents/show", {"files": {"data": [{"path": "Fictional.Film.1080p.mkv"}]}}))

    tracker, requests = _tracker(handler)
    dupes = asyncio.run(tracker.search_existing(_movie_meta(tmp_path)))
    assert len(requests) == 9
    assert all(dupe["name"].endswith("1080p") for dupe in dupes)


def test_remote_screenshots_use_the_checked_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    downloads: list[str] = []

    async def fake_download(url: str) -> bytes | None:
        downloads.append(url)
        return _png() if url.endswith("good.png") else None

    monkeypatch.setattr(asc_module, "manifest_files", lambda *_args: [])
    monkeypatch.setattr(asc_module, "download_public_image", fake_download)
    meta = Meta(category="GAME", image_list=[{"raw_url": "https://img.example/bad.png"}, {"raw_url": "https://img.example/good.png"}])
    images = asyncio.run(AmigosShare(CONFIG).get_screenshots(meta, 6))
    assert downloads == ["https://img.example/bad.png", "https://img.example/good.png"]
    assert [(name, content_type) for name, _content, content_type in images] == [("screenshot_2.png", "image/png")]


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, 5.0), ("12", 12.0), ("600", 60.0), ("-3", 0.0), ("not a date", 5.0), ("Wed, 21 Oct 2015 07:28:00 GMT", 0.0)],
)
def test_retry_after_accepts_seconds_and_http_dates(value: str | None, expected: float) -> None:
    assert asc_module.retry_after_seconds(value) == expected


@pytest.mark.parametrize(("dimensions", "expected"), [("3840 × 1600", "2160p"), ("1920 × 800", "1080p"), ("1280 × 536", "720p"), ("720 × 576", "576p"), ("", "")])
def test_resolution_from_dimensions(dimensions: str, expected: str) -> None:
    assert asc_module.resolution_from_dimensions(dimensions) == expected


def test_expired_cookies_skip_the_tracker(tmp_path: Path) -> None:
    tracker, _requests = _tracker(lambda _request: httpx.Response(302, headers={"Location": "https://amigos-share.club/login"}))
    meta = _movie_meta(tmp_path)
    assert asyncio.run(tracker.search_existing(meta)) == []
    assert meta.skipping == "AMIGOSSHARE"


def _upload_handler(final: httpx.Response) -> Any:
    lookup = {
        "type": "movie",
        "imdbId": "tt1234567",
        "title": "Fictional Film (Original Film)",
        "year": 2001,
        "genres": ["Drama"],
        "language": "Inglês",
        "cover": {"path": "torrent-images/aa/cover.webp", "url": "/storage/torrent-images/aa/cover.webp"},
        "description": "[center][img]https://amigos-share.club/storage/torrent-images/aa/cover.webp[/img]\n[b]Sinopse[/b][/center]",
    }
    mediainfo = {
        "width": 1920,
        "height": 800,
        "subtitle": "embedded",
        "attributes": {"resolution": ["WEB-DL"], "container": ["MKV"], "video_codec": ["H265"], "audio_codec": ["E-AC-3"], "audio_channels": ["Dual-Audio"]},
        "report": "General\nComplete name : Fictional.Film.2001.mkv",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path == "/torrents/upload":
            return httpx.Response(200, text=_page_html("torrents/create", FORM_PROPS))
        if path == "/torrents/lookup":
            assert request.headers["X-XSRF-TOKEN"] == "token="
            return httpx.Response(200, json=lookup)
        if path == "/torrents/mediainfo":
            return httpx.Response(200, json=mediainfo)
        if path == "/torrents/screenshots":
            return httpx.Response(200, json={"path": f"torrent-screens/{len(request.content)}.webp", "url": "/storage/x.webp"})
        if path == "/torrents" and request.method == "POST":
            return final
        raise AssertionError(f"Unexpected request {request.method} {request.url}")

    return handler


def _prepare_upload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tracker: AmigosShare) -> Meta:
    meta = _movie_meta(tmp_path)
    release_dir = tmp_path / "tmp" / "release"
    release_dir.mkdir(parents=True)
    (release_dir / "MEDIAINFO_CLEANPATH.txt").write_text("General\nComplete name : Fictional.Film.2001.mkv", encoding="utf-8")
    screenshots = []
    for index in range(3):
        screenshot = tmp_path / f"shot{index}.png"
        screenshot.write_bytes(_png())
        screenshots.append(screenshot)
    monkeypatch.setattr(asc_module, "manifest_files", lambda *_args: screenshots)

    async def fake_create(meta: Meta, tracker_name: str, *_args: Any, **_kwargs: Any) -> None:
        (Path(meta.base_dir) / "tmp" / meta.uuid / f"[{tracker_name}].torrent").write_bytes(b"d4:infod4:name4:testee")

    async def fake_download(*_args: Any, **kwargs: Any) -> str:
        assert kwargs["downurl"] == "https://amigos-share.club/torrents/123/download"
        return "downloaded"

    async def no_external_subtitle(_meta: Meta) -> bool:
        return False

    monkeypatch.setattr(tracker.common, "create_torrent_for_upload", fake_create)
    monkeypatch.setattr(tracker.common, "download_tracker_torrent", fake_download)
    monkeypatch.setattr(tracker.common, "has_portuguese_external_subtitle", no_external_subtitle)
    return meta


def test_upload_sends_the_form_the_site_expects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tracker, requests = _tracker(_upload_handler(httpx.Response(302, headers={"Location": "https://amigos-share.club/torrents/123"})))
    meta = _prepare_upload(tmp_path, monkeypatch, tracker)

    assert asyncio.run(tracker.upload(meta)) is True
    assert meta.tracker_status["AMIGOSSHARE"]["torrent_id"] == "123"
    assert [request.url.path for request in requests].count("/torrents/screenshots") == 3

    form = requests[-1]
    assert form.headers["Accept"] == "application/json"
    body = form.content.decode("utf-8", errors="replace")
    for field, value in (
        ("category_id", "4"),
        ("name", "Fictional Film (Original Film)"),
        ("year", "2001"),
        ("imdb_id", "tt1234567"),
        ("cover_path", "torrent-images/aa/cover.webp"),
        ("width", "1920"),
        ("subtitle", "embedded"),
        ("mediainfo", "General\nComplete name : Fictional.Film.2001.mkv"),
    ):
        assert f'name="{field}"\r\n\r\n{value}\r\n' in body
    attribute_ids = {line for line in body.split("\r\n") if line.isdigit()}
    assert {"101", "200", "301", "400", "500", "601", "700"} <= attribute_ids
    assert body.count('name="screenshot_paths[]"') == 3
    assert 'name="torrent"; filename="Fictional Film (Original Film).torrent"' in body
    assert "Compartilhado com Upload Assistant v1.0 (fork)" in body
    # The IMDb description the site generates is not sent.
    assert "Sinopse" not in body


def test_validation_errors_are_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    final = httpx.Response(422, json={"message": "invalid", "errors": {"torrent": ["Este torrent já foi enviado."]}})
    tracker, _requests = _tracker(_upload_handler(final))
    meta = _prepare_upload(tmp_path, monkeypatch, tracker)

    assert asyncio.run(tracker.upload(meta)) is False
    assert meta.tracker_status["AMIGOSSHARE"]["status_message"] == "data error - torrent: Este torrent já foi enviado."


def test_debug_mode_does_not_upload_images_or_the_form(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tracker, requests = _tracker(_upload_handler(httpx.Response(500)))
    meta = _prepare_upload(tmp_path, monkeypatch, tracker)
    meta.debug = True

    assert asyncio.run(tracker.upload(meta)) is True
    assert [request.url.path for request in requests] == ["/torrents/upload", "/torrents/lookup", "/torrents/mediainfo"]


def test_lookup_of_a_series_is_refused_for_a_movie(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/torrents/upload":
            return httpx.Response(200, text=_page_html("torrents/create", FORM_PROPS))
        return httpx.Response(200, json={"type": "series", "title": "Fictional Show"})

    tracker, _requests = _tracker(handler)
    meta = _movie_meta(tmp_path)
    assert asyncio.run(tracker.get_data(meta)) is None
    assert "IMDb lookup failed" in meta.tracker_status["AMIGOSSHARE"]["status_message"]


def test_rules_flag_extra_files_and_undubbed_remux(tmp_path: Path) -> None:
    meta = _movie_meta(
        tmp_path,
        type="REMUX",
        audio_languages=["English"],
        filelist=[str(tmp_path / "Fictional.Film.2001.mkv"), str(tmp_path / "Fictional.Film.2001.nfo")],
        source_size=30 * 1024 * 1024,
    )
    warnings = AmigosShare(CONFIG).rules(meta)
    assert any("15.2.16" in warning and ".nfo" in warning for warning in warnings)
    assert any("15.2.6" in warning for warning in warnings)


def test_requests_are_read_from_the_requests_page(tmp_path: Path) -> None:
    props = {"requests": {"data": [{"id": 9, "title": "Fictional Film", "bountyTotal": 500}]}}
    tracker, _requests = _tracker(lambda _request: httpx.Response(200, text=_page_html("requests/index", props)))
    meta = _movie_meta(tmp_path, search_requests=True)
    assert asyncio.run(tracker.get_requests(meta)) == [{"Name": "Fictional Film", "Reward": "500", "Link": "https://amigos-share.club/pedidos/9"}]
