# ruff: noqa: S101
import asyncio
import runpy
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from src.cookie_auth import get_tracker_domain
from src.meta import Meta
from src.trackers.NEXUSPHP.ptzone import PTZone
from src.trackers.NEXUSPHP.qingwa import QingWa
from src.trackersetup import STATIC_AUTH_TYPES, get_tracker_framework, tracker_class_map


@pytest.fixture
def tracker():
    instance = QingWa({"DEFAULT": {"tmdb_api": "dummy_key"}, "TRACKERS": {"QINGWA": {"announce_url": "https://tracker.example/announce"}}})
    yield instance
    asyncio.run(instance.session.aclose())


def test_registration_and_config(tracker):
    example_config = runpy.run_path(str(Path(__file__).resolve().parents[1] / "data" / "example_config.py"))["config"]
    assert tracker_class_map["QINGWA"] is QingWa
    assert get_tracker_framework("QINGWA") == "NEXUSPHP"
    assert STATIC_AUTH_TYPES["QINGWA"] == "cookies"
    assert get_tracker_domain("QINGWA") == "qingwapt.com"
    assert example_config["TRACKERS"]["QINGWA"]["cli_alias"] == "QW"
    assert tracker.source_flag == "[www.qingwapt.com] 青蛙"


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"category": "MOVIE"}, 401),
        ({"category": "TV"}, 402),
        ({"category": "TV", "genres": ["Reality"]}, 403),
        ({"category": "TV", "keywords": ["talk show"]}, 403),
        ({"category": "MOVIE", "genres": ["Documentary"]}, 404),
        ({"category": "TV", "keywords": ["documentary"]}, 404),
        ({"category": "MOVIE", "anime": True}, 405),
        ({"category": "TV", "genres": ["Animation"]}, 405),
    ],
)
def test_categories(tracker, values, expected):
    assert tracker.get_category(Meta(**values)) == expected


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"is_disc": "BDMV", "resolution": "2160p"}, 1),
        ({"is_disc": "BDMV", "resolution": "1080p"}, 8),
        ({"is_disc": "DVD"}, 2),
        ({"type": "REMUX"}, 9),
        ({"type": "ENCODE"}, 10),
        ({"type": "WEB-DL"}, 7),
        ({"type": "WEBRIP"}, 7),
        ({"type": "HDTV"}, 4),
        ({}, 6),
    ],
)
def test_sources(tracker, values, expected):
    meta = Meta(**values)
    assert tracker.get_type(meta) == expected
    assert asyncio.run(tracker.get_type_data(meta)) == {"source_sel[4]": expected}
    assert asyncio.run(tracker.get_region_data(meta)) == {}


@pytest.mark.parametrize(
    ("codec", "expected"),
    [("H.264", 1), ("HEVC", 6), ("x265", 6), ("VC-1", 2), ("MPEG-2", 4), ("MPEG-4", 3), ("AV1", 7), ("VP9", 8), ("unknown", 5)],
)
def test_video_codecs(tracker, codec, expected):
    assert tracker.get_codec(Meta(video_codec=codec)) == expected


@pytest.mark.parametrize(
    ("audio", "expected"),
    [
        ("DTS:X", 9),
        ("DTS-HD MA 5.1", 10),
        ("DTS-HD HRA", 21),
        ("DTS 5.1", 14),
        ("TrueHD Atmos 7.1", 11),
        ("TrueHD 7.1", 12),
        ("LPCM", 13),
        ("DD+ Atmos 5.1", 16),
        ("E-AC-3", 16),
        ("DDP 5.1", 16),
        ("DD 5.1", 15),
        ("AC-3", 15),
        ("FLAC", 1),
        ("AAC", 17),
        ("APE", 18),
        ("WAV", 19),
        ("MP3", 4),
        ("M4A", 8),
        ("Opus", 20),
        ("AV3A", 22),
        ("unknown", 7),
    ],
)
def test_audio_codecs(tracker, audio, expected):
    assert tracker.get_audio_codec(Meta(audio=audio)) == expected


@pytest.mark.parametrize(
    ("resolution", "sd", "expected"),
    [("4320p", False, 6), ("2160p", False, 7), ("1440p", False, 8), ("1080p", False, 1), ("1080i", False, 2), ("720p", False, 3), ("576p", True, 4), ("OTHER", False, 5)],
)
def test_resolutions(tracker, resolution, sd, expected):
    assert tracker.get_resolution(Meta(resolution=resolution, sd=sd)) == expected


def test_tags_and_optional_metadata(tracker):
    assert tracker.get_group_tag(Meta()) == 5
    assert tracker.get_checkboxes(Meta(audio_languages=None, subtitle_languages=None)) == []
    meta = Meta(is_disc="BDMV", hdr="DV HDR10+", exclusive=True, audio_languages=["Mandarin", "Cantonese"], subtitle_languages=["Chinese"])
    assert set(tracker.get_checkboxes(meta)) == {"1", "5", "8", "6", "11", "12", "13", "7"}
    assert tracker.get_checkboxes(Meta(is_disc="BDMV", diy_disc=True)) == ["4"]
    assert tracker.get_checkboxes(Meta(type="REMUX")) == ["15"]
    # A season pack alone does not imply a completed series or a series collection.
    assert tracker.get_checkboxes(Meta(category="TV", tv_pack=True)) == []


def test_localized_description(tracker, tmp_path):
    (tmp_path / "tmp" / "fictional").mkdir(parents=True)
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="fictional",
        category="MOVIE",
        title="Imaginary Journey",
        year=2026,
        description="Fictional user description",
        tmdb_localized_data={"zh-cn": {"main": {"name": "Imaginary Journey", "overview": "Fictional localized synopsis"}}},
    )

    async def exercise():
        await tracker.load_localized_data(meta)
        data = await tracker.get_description(meta)
        assert "Fictional localized synopsis" in data["descr"]
        assert "Fictional user description" in data["descr"]

    asyncio.run(exercise())


def test_complete_upload_payload(tracker, monkeypatch):
    async def exercise():
        monkeypatch.setattr(tracker, "load_localized_data", AsyncMock())
        monkeypatch.setattr(tracker, "get_description", AsyncMock(return_value={"descr": "Fictional description"}))
        monkeypatch.setattr(tracker, "get_technical_info", AsyncMock(return_value={"technical_info": "Fictional technical information"}))
        meta = Meta(
            title="Imaginary Journey",
            year=2026,
            tag="-ExampleGroup",
            category="MOVIE",
            type="WEB-DL",
            resolution="2160p",
            video_codec="HEVC",
            audio="DD+ 5.1",
            anon=1,
            aka="AKA Fictional Alternative",
            original_title="Fictional Original",
        )
        data = await tracker.get_data(meta)
        assert data["source_sel[4]"] == 7
        assert "medium_sel[4]" not in data
        assert data["type"] == 401
        assert data["codec_sel[4]"] == 6
        assert data["audiocodec_sel[4]"] == 16
        assert data["standard_sel[4]"] == 7
        assert data["team_sel[4]"] == 5
        assert data["uplver"] == "yes"
        assert data["technical_info"] == "Fictional technical information"
        assert data["name"] == "Imaginary Journey 2026 2160p WEB-DL H.265 DDP 5.1-ExampleGroup"
        assert data["small_descr"] == "Fictional Alternative / Fictional Original"
        assert "uplver" not in await tracker.get_anonymous_data(Meta(anon=0))
        monkeypatch.setattr(tracker.cookie_validator, "load_session_cookies", AsyncMock(return_value={"session": "fictional-cookie"}))
        uploader = AsyncMock(return_value=True)
        monkeypatch.setattr(tracker.cookie_auth_uploader, "handle_upload", uploader)
        assert await tracker.upload(meta) is True
        args = uploader.call_args.kwargs
        assert args["tracker"] == "QINGWA"
        assert args["upload_url"] == "https://www.qingwapt.com/takeupload.php"
        assert args["source_flag"] == tracker.source_flag
        assert args["data"]["source_sel[4]"] == 7
        assert args["upload_cookies"]["session"] == "fictional-cookie"
        await tracker.session.aclose()

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (
            {"type": "WEBDL", "service": "NF", "video_encode": "H.265", "hdr": "DV HDR10", "audio": "DD+ Atmos 5.1"},
            "Imaginary Journey S02E03 2026 1080p NF WEB-DL DV HDR H.265 DDP 5.1 Atmos-ExampleGroup",
        ),
        (
            {"type": "ENCODE", "source": "BluRay", "video_encode": "x265 10bit", "audio": "Dual-Audio FLAC 2.0"},
            "Imaginary Journey S02E03 2026 1080p BluRay x265 FLAC 2.0-ExampleGroup",
        ),
        (
            {"type": "ENCODE", "source": "BluRay", "video_encode": "x264", "bit_depth": "10", "audio": "AC3 5.1"},
            "Imaginary Journey S02E03 2026 1080p BluRay Hi10P x264 DD 5.1-ExampleGroup",
        ),
        (
            {"type": "DISC", "is_disc": "BDMV", "video_codec": "AVC", "source": "BluRay", "region": "USA", "audio": "DTS-HD MA 7.1"},
            "Imaginary Journey S02E03 2026 1080p USA Blu-ray AVC DTS-HD MA 7.1-ExampleGroup",
        ),
        (
            {"type": "REMUX", "source": "BluRay", "video_codec": "HEVC", "audio": "TrueHD Atmos 7.1"},
            "Imaginary Journey S02E03 2026 1080p BluRay Remux HEVC TrueHD 7.1 Atmos-ExampleGroup",
        ),
        (
            {"type": "HDTV", "source": "HDTV", "service": "FictionTV", "video_codec": "AVC", "audio": "E-AC-3", "channels": "2.0"},
            "Imaginary Journey S02E03 2026 1080p FictionTV HDTV H264 DDP 2.0-ExampleGroup",
        ),
        ({"type": "WEBDL", "video_codec": "AVC", "manual_date": "2026-10-09", "audio": "AAC 2.0"}, "Imaginary Journey 20261009 1080p WEB-DL H.264 AAC 2.0-ExampleGroup"),
    ],
)
def test_qingwa_title_order(tracker, values, expected):
    meta = Meta(title="Imaginary Journey", category="TV", year=2026, season="S02", episode="E03", resolution="1080p", tag="-ExampleGroup", **values)
    original_name = meta.name
    assert asyncio.run(tracker.get_name(meta)) == {"name": expected}
    assert meta.name == original_name


@pytest.mark.parametrize(
    "excluded",
    [
        {"Title": "Director commentary"},
        {"title": "Audio Commentary"},
        {"TrackTitle": "Commentary"},
        {"ServiceKind": "C"},
        {"ServiceKind": "Main / Commentary"},
        {"Title": "Compatibility track"},
    ],
)
def test_encode_counts_tracks_not_languages(tracker, excluded):
    meta = Meta(
        title="Imaginary Journey",
        category="MOVIE",
        type="ENCODE",
        source="BluRay",
        video_encode="x265",
        audio="FLAC 2.0",
        tag="-ExampleGroup",
        audio_languages=["English"],
        mediainfo={"media": {"track": [{"@type": "Video"}, {"@type": "Audio", "Language": "en"}, {"@type": "Audio", "Language": "en"}, {"@type": "Audio", **excluded}]}},
    )
    assert asyncio.run(tracker.get_name(meta))["name"].endswith("x265 FLAC 2.0 2Audio-ExampleGroup")
    meta.mediainfo["media"]["track"].pop(2)
    assert "Audio" not in asyncio.run(tracker.get_name(meta))["name"]


def test_title_manual_override_and_season_number(tracker):
    assert asyncio.run(tracker.get_name(Meta(title="Imaginary Journey", manual_name="  Custom reviewed title  "))) == {"name": "Custom reviewed title"}
    meta = Meta(title="Imaginary Journey", category="TV", season=1, year=2026, type="WEBDL", video_codec="AVC", edition="Complete", aka="AKA Alternate")
    assert asyncio.run(tracker.get_name(meta))["name"] == "Imaginary Journey S01 2026 WEB-DL H.264"


def test_subtitle_uses_localized_name_and_deduplicates(tracker, monkeypatch):
    async def exercise():
        monkeypatch.setattr(tracker, "get_description", AsyncMock(return_value={"descr": "Fictional description"}))
        monkeypatch.setattr(tracker, "get_technical_info", AsyncMock(return_value={"technical_info": "Fictional technical information"}))
        meta = Meta(title="Imaginary Journey", aka="AKA 幻想之旅", original_title="Imaginary Journey", tmdb_localized_data={"zh-cn": {"main": {"title": "幻想之旅"}}})
        data = await tracker.get_data(meta)
        assert data["small_descr"] == "幻想之旅"
        assert meta.aka == "AKA 幻想之旅"

    asyncio.run(exercise())


@pytest.mark.parametrize("tracker_class, expected_filter", [(QingWa, "source7"), (PTZone, "medium4")])
def test_dupe_search_uses_matching_source_filter(monkeypatch, tracker_class, expected_filter):
    async def exercise():
        instance = tracker_class(
            {
                "DEFAULT": {"tmdb_api": "dummy_key"},
                "TRACKERS": {"QINGWA": {"announce_url": "https://tracker.example/announce"}, "PTZONE": {"announce_url": "https://tracker.example/announce"}},
            }
        )
        monkeypatch.setattr(instance.cookie_validator, "load_session_cookies", AsyncMock(return_value={"session": "fictional-cookie"}))

        def respond(request):
            assert request.url.params[expected_filter] == "1"
            assert request.url.params["cat401"] == "1"
            assert request.url.params["search"] == "Imaginary Journey 2026"
            return httpx.Response(
                200,
                text='<table class="torrents"><tr><th>Name</th></tr><tr><td><table class="torrentname"><tr><td><a href="details.php?id=42&amp;hit=1" title="Imaginary Journey 2026">Example</a></td></tr></table></td></tr></table>',
            )

        await instance.session.aclose()
        instance.session = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        async with instance.session:
            results = await instance.search_existing(Meta(category="MOVIE", type="WEB-DL", title="Imaginary Journey", year=2026, resolution="1080p"))
        assert results == [{"name": "Imaginary Journey 2026", "link": f"{instance.base_url}/details.php?id=42"}]

    asyncio.run(exercise())
