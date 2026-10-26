# ruff: noqa: S101
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from src.meta import Meta
from src.trackers.NEXUSPHP.zmpt import ZmPT
from src.trackersetup import get_tracker_framework, http_trackers, tracker_class_map


pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def tracker():
    instance = ZmPT({"DEFAULT": {"tmdb_api": "dummy_key"}, "TRACKERS": {"ZMPT": {"announce_url": "https://zmpt.cc/announce.php?passkey=test"}}})
    yield instance
    await instance.session.aclose()


async def test_zmpt_registration():
    assert tracker_class_map["ZMPT"] is ZmPT
    assert get_tracker_framework("ZMPT") == "NEXUSPHP"
    assert "ZMPT" in http_trackers
    assert set(ZmPT.supported_categories) == {"MOVIE", "TV"}
    assert ZmPT.source_flag == "[zmpt.cc] 织梦"


@pytest.mark.parametrize(
    ("metadata", "category"),
    [
        ({"category": "MOVIE"}, 401),
        ({"category": "TV"}, 402),
        ({"category": "TV", "genres": ["Reality"]}, 403),
        ({"category": "TV", "genres": ["Talk Show"]}, 403),
        ({"category": "TV", "genres": ["Drama"], "keywords": ["reality tv"]}, 403),
        ({"category": "TV", "keywords": ["Talk Show"]}, 403),
        ({"category": "TV", "keywords": ["reality-based drama"]}, 402),
        ({"category": "TV", "keywords": ["unreality tv"]}, 402),
        ({"category": "MOVIE", "genres": ["Animation"]}, 417),
        ({"category": "TV", "anime": True}, 417),
        ({"category": "MOVIE", "genres": ["Documentary"]}, 422),
        ({"category": "TV", "keywords": ["documentary"]}, 422),
    ],
)
async def test_categories(tracker, metadata, category):
    assert tracker.get_category(Meta(**metadata)) == category


@pytest.mark.parametrize(
    ("metadata", "medium"),
    [
        ({"is_disc": "BDMV", "resolution": "2160p"}, 1),
        ({"is_disc": "BDMV", "resolution": "1080p"}, 1),
        ({"is_disc": "DVD"}, 6),
        ({"type": "REMUX"}, 3),
        ({"type": "HDTV"}, 5),
        ({"type": "WEBDL"}, 10),
        ({"type": "WEBRIP"}, 7),
        ({"type": "ENCODE"}, 7),
        ({"type": "DVDRIP"}, 7),
        ({"type": "OTHER"}, 12),
    ],
)
async def test_media(tracker, metadata, medium):
    assert tracker.get_type(Meta(**metadata)) == medium


@pytest.mark.parametrize(("resolution", "standard"), [("1080p", 1), ("1080i", 1), ("2160p", 5), ("1440p", 6), ("576p", 7), ("480p", 7), ("720p", 8), ("4320p", 9)])
async def test_resolutions(tracker, resolution, standard):
    assert tracker.get_resolution(Meta(resolution=resolution)) == standard


@pytest.mark.parametrize(("codec", "value"), [("H.264", 1), ("x264", 1), ("HEVC", 6), ("x265", 6), ("VC-1", 2), ("XviD", 3), ("MPEG-2", 4), ("AV1", 5)])
async def test_video_codecs(tracker, codec, value):
    assert tracker.get_codec(Meta(video_codec=codec)) == value


@pytest.mark.parametrize(
    ("audio", "value"), [("FLAC", 1), ("DTS-HD MA 5.1", 3), ("AAC 2.0", 6), ("DD+ 5.1", 8), ("TrueHD Atmos 7.1", 7), ("LPCM 2.0", 7), ("ALAC", 9), ("WAV", 10)]
)
async def test_audio_codecs(tracker, audio, value):
    assert tracker.get_audio_codec(Meta(audio=audio)) == value


async def test_groups_and_tags(tracker):
    assert tracker.get_group_tag(Meta(tag="-ZmWeb")) == 7
    assert tracker.get_group_tag(Meta(tag="-ZmPT")) == 6
    assert tracker.get_group_tag(Meta(tag="-Other")) == 5
    assert tracker.get_checkboxes(Meta(audio_languages=None, subtitle_languages=None)) == []
    meta = Meta(exclusive=True, diy_disc=True, is_disc="BDMV", audio_languages=["Cantonese"], subtitle_languages=["Chinese"], hdr="HDR10")
    assert tracker.get_checkboxes(meta) == ["1", "4", "5", "6", "7"]
    assert tracker.get_checkboxes(Meta(is_disc="BDMV")) == ["10"]


async def test_upload_form_uses_nexusphp_fields(tracker, tmp_path, monkeypatch):
    media_dir = tmp_path / "tmp" / "release"
    media_dir.mkdir(parents=True)
    (media_dir / "MEDIAINFO_CLEANPATH.txt").write_text("Video\nFormat: HEVC", encoding="utf-8")
    monkeypatch.setattr(tracker, "get_description", AsyncMock(return_value={"descr": "Description with screenshots"}))
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="release",
        name="Example.2026.2160p.WEB-DL.H.265-ZmWeb",
        category="MOVIE",
        type="WEBDL",
        resolution="2160p",
        video_codec="HEVC",
        audio="DD+ 5.1",
        tag="-ZmWeb",
        anon=True,
        douban_id=1234567,
        imdb_id="tt1234567",
        imdb_info={"imdb_url": "https://www.imdb.com/title/tt1234567/"},
        tmdb_localized_data={"zh-cn": {"main": {"title": "Example"}}},
    )
    data = await tracker.get_data(meta)

    assert data["type"] == 401
    assert data["medium_sel[4]"] == 10
    assert data["codec_sel[4]"] == 6
    assert data["audiocodec_sel[4]"] == 8
    assert data["standard_sel[4]"] == 5
    assert data["team_sel[4]"] == 7
    assert data["uplver"] == "yes"
    assert data["url"] == "https://www.imdb.com/title/tt1234567/"
    assert data["pt_gen"] == "https://movie.douban.com/subject/1234567/"
    assert data["technical_info"] == "Video\nFormat: HEVC"
    assert data["descr"] == "Description with screenshots"
    assert "medium_sel" not in data
    assert "processing_sel[4]" not in data
    assert "source_sel[4]" not in data


async def test_search_uses_native_filters_and_parses_details(tracker, monkeypatch):
    html = """<table class="torrents"><tr><th>Name</th></tr><tr><td>
    <table class="torrentname"><tr><td><a href="details.php?id=42&amp;hit=1" title="Example.2026.1080p.WEB-DL">Example</a></td></tr></table>
    </td></tr></table>"""
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, text=html)

    await tracker.session.aclose()
    tracker.session = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(tracker.cookie_validator, "load_session_cookies", AsyncMock(return_value={"session": "test"}))

    results = await tracker.search_existing(Meta(category="MOVIE", title="Example", year=2026, type="WEBDL", resolution="1080p"))

    assert results == [{"name": "Example.2026.1080p.WEB-DL", "link": "https://zmpt.cc/details.php?id=42"}]
    assert dict(requests[0].url.params) == {"cat401": "1", "medium10": "1", "standard1": "1", "incldead": "0", "search": "Example 2026"}
    assert "session=test" in requests[0].headers["cookie"]


async def test_upload_delegates_to_cookie_uploader(tracker, monkeypatch):
    monkeypatch.setattr(tracker, "get_data", AsyncMock(return_value={"type": 401}))
    monkeypatch.setattr(tracker.cookie_validator, "load_session_cookies", AsyncMock(return_value={"session": "test"}))
    upload = AsyncMock(return_value=False)
    monkeypatch.setattr(tracker.cookie_auth_uploader, "handle_upload", upload)

    assert await tracker.upload(Meta()) is False
    args = upload.call_args.kwargs
    assert args["tracker"] == "ZMPT"
    assert args["upload_url"] == "https://zmpt.cc/takeupload.php"
    assert args["torrent_field_name"] == "file"
    assert args["success_text"] == "download.php?id="
    assert args["upload_cookies"].get("session") == "test"
