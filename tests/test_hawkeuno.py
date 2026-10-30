# Assertions are the idiomatic pytest checks for this focused payload test.
# ruff: noqa: S101

from unittest.mock import AsyncMock

import pytest

from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.rehostimages import check_tracker_image_hosts
from src.trackers.UNIT3D.hawkeuno import HawkeUno


@pytest.mark.asyncio
async def test_hawkeuno_uses_api_release_tag_for_repack(monkeypatch):
    tracker = HawkeUno({"TRACKERS": {"HAWKEUNO": {}}})
    monkeypatch.setattr(tracker, "get_description", lambda _meta: _noop())
    meta = Meta(category="TV", type="WEBDL", tmdb=123, repack="REPACK")

    data = await tracker.get_data(meta)

    assert data["release_tag"] == "REPACK"
    assert "repack" not in data


@pytest.mark.asyncio
async def test_hawkeuno_image_host_policy_does_not_require_legacy_method():
    tracker = HawkeUno({"TRACKERS": {"HAWKEUNO": {}}})
    tracker.rehost_images_manager.check_policy = AsyncMock()
    meta = Meta(category="TV", type="WEBDL", tmdb=123)

    await check_tracker_image_hosts(meta, tracker)

    tracker.rehost_images_manager.check_policy.assert_awaited_once_with(meta, "HAWKEUNO", tracker.image_host_policy)


@pytest.mark.asyncio
async def test_hawkeuno_respects_configured_screenshot_rows():
    config = {
        "DEFAULT": {"screens_per_row": "1000", "thumbnail_size": "350"},
        "TRACKERS": {"HAWKEUNO": {}},
    }
    builder = DescriptionBuilder("HAWKEUNO", config)

    screens_per_row = await builder.get_screens_per_row()

    assert screens_per_row == 1000
    parts = []
    for index in range(9):
        parts.append(builder.format_screenshot(f"https://example.com/{index}", f"https://example.com/{index}.png"))
        builder._append_screenshot_row_separator(parts, index, screens_per_row)

    assert "\n" not in "".join(parts)


@pytest.mark.asyncio
async def test_hawkeuno_supplies_missing_web_service_and_release_group():
    tracker = HawkeUno({"TRACKERS": {"HAWKEUNO": {}}})
    meta = Meta(
        type="WEBDL",
        service=None,
        tag=None,
        name="Movie 2026 1080p WEB-DL DDP5.1 x265",
        clean_name="Movie.2026.1080p.WEB-DL.DDP5.1.x265",
    )

    assert await tracker.get_name(meta) == {"name": "Movie 2026 1080p NADA WEB-DL DDP5.1 x265-NOGROUP"}
    assert tracker._normalize_upload_name(meta.clean_name, meta) == "Movie.2026.1080p.NADA.WEB-DL.DDP5.1.x265-NOGROUP"


@pytest.mark.asyncio
async def test_hawkeuno_keeps_detected_service_and_group():
    tracker = HawkeUno({"TRACKERS": {"HAWKEUNO": {}}})
    meta = Meta(
        type="WEBDL",
        service="AMZN",
        tag="-GROUP",
        name="Movie 2026 1080p AMZN WEB-DL DDP5.1 x265-GROUP",
    )

    assert await tracker.get_name(meta) == {"name": meta.name}


@pytest.mark.asyncio
async def test_hawkeuno_accepts_webrip_as_encode_and_uses_webdl_name():
    tracker = HawkeUno({"TRACKERS": {"HAWKEUNO": {}}})
    meta = Meta(
        type="WEBRIP",
        service="AMZN",
        tag="-GROUP",
        name="Movie 2026 1080p AMZN WEBRip x265-GROUP",
        clean_name="Movie.2026.1080p.AMZN.WEBRip.x265-GROUP",
        language_checked=True,
        audio_languages=["English"],
        valid_mi_settings=True,
    )

    assert await tracker.get_additional_checks(meta)
    assert await tracker.get_type_id(meta) == {"type_id": "15"}
    assert await tracker.get_name(meta) == {"name": "Movie 2026 1080p AMZN WEB-DL x265-GROUP"}
    assert tracker._normalize_upload_name(meta.clean_name, meta) == "Movie.2026.1080p.AMZN.WEB-DL.x265-GROUP"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "category, tv_pack, incomplete",
    [
        ("MOVIE", False, False),
        ("TV", False, False),
        ("TV", True, False),
        ("TV", True, True),
    ],
)
@pytest.mark.parametrize("manual_name", [None, "  Custom  Release S03 WEBRip  "])
async def test_hawkeuno_upload_names(tmp_path, category, tv_pack, incomplete, manual_name):
    tracker = HawkeUno({"TRACKERS": {"HAWKEUNO": {}}})
    tracker.get_description = AsyncMock()
    tracker.common.create_torrent_for_upload = AsyncMock()
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="release",
        category=category,
        type="WEBRIP",
        tv_pack=tv_pack,
        season_pack_incomplete=incomplete,
        season="S03",
        season_int=3,
        name="Generated Release S03 WEBRip",
        clean_name="Generated.Release.S03.WEBRip",
        manual_name=manual_name,
    )
    folder = tmp_path / "tmp" / "release"
    folder.mkdir(parents=True)
    for filename in ("[HAWKEUNO].torrent", "[HAWKEUNO]DESCRIPTION.txt", "MEDIAINFO_CLEANPATH.txt"):
        (folder / filename).write_bytes(b"fixture")

    data = await tracker.get_data(meta)
    files = await tracker.get_files(meta)

    if manual_name is not None:
        assert data["name"] == "Custom  Release S03 WEBRip"
        assert files["torrent"][0] == "Custom  Release S03 WEBRip.torrent"
    elif incomplete:
        assert data["name"] == "Generated Release S03 INCOMPLETE NADA WEB-DL-NOGROUP"
        assert files["torrent"][0] == "Generated.Release.S03.INCOMPLETE.NADA.WEB-DL-NOGROUP.torrent"
    else:
        assert "name" not in data
        assert files["torrent"][0] == "Generated.Release.S03.NADA.WEB-DL-NOGROUP.torrent"
    assert files["torrent"][1] == b"fixture"


@pytest.mark.asyncio
async def test_hawkeuno_sends_explicit_attributes_for_web_episode(monkeypatch):
    tracker = HawkeUno({"TRACKERS": {"HAWKEUNO": {}}})
    monkeypatch.setattr(tracker, "get_description", lambda _meta: _noop())
    meta = Meta(
        category="TV",
        type="WEBDL",
        tmdb=123,
        imdb_id=456,
        resolution="2160p",
        source="Web",
        video_encode="H.265",
        video_codec="HEVC",
        hdr="DV HDR",
        audio="DD+ 5.1 Atmos",
        channels="5.1.2",
        service="AMZN",
        tag="-GROUP",
        audio_languages=["English"],
        season_int=2,
        episode_int=5,
    )

    data = await tracker.get_data(meta)

    assert data["resolution"] == "2"
    assert data["video_codec"] == 3
    assert data["video_format"] == 2
    assert data["audio_format"] == 8
    assert data["audio_channels"] == 8
    assert data["source_type"] == 9
    assert data["streaming_service"] == "AMZN"
    assert data["media_language"] == "English"
    assert data["release_group"] == "GROUP"
    assert data["season_number"] == 2
    assert data["episode_number"] == 5
    assert data["season_pack"] == 0
    assert data["imdb"] == 456
    assert "edition" not in data
    assert "release_tag" not in data


@pytest.mark.asyncio
async def test_hawkeuno_sends_explicit_attributes_for_uhd_disc(monkeypatch):
    tracker = HawkeUno({"TRACKERS": {"HAWKEUNO": {}}})
    monkeypatch.setattr(tracker, "get_description", lambda _meta: _noop())
    meta = Meta(
        category="MOVIE",
        type="DISC",
        is_disc="BDMV",
        tmdb=123,
        resolution="2160p",
        source="Blu-ray",
        uhd="UHD",
        webdv=True,
        video_codec="HEVC",
        hdr="HDR10+",
        audio="Dual-Audio TrueHD 7.1 Atmos",
        channels="7.1.4",
        audio_languages=["English", "French"],
        edition="Director's Cut Hybrid",
        region="GBR",
        distributor="ARROW VIDEO",
        tag=None,
    )

    data = await tracker.get_data(meta)

    assert data["video_codec"] == 5
    assert data["video_format"] == 4
    assert data["audio_format"] == 1
    assert data["audio_channels"] == 6
    assert data["source_type"] == 2
    assert data["media_language"] == "DUAL"
    assert data["edition"] == 5
    assert data["region"] == "GBR"
    assert data["distributor"] == "3"
    assert data["release_group"] == "NoGRP"
    assert "streaming_service" not in data
    assert "imdb" not in data


@pytest.mark.parametrize(
    "fields, expected",
    [
        ({"type": "WEBRIP", "source": "Web", "webdv": True}, "WEB-DL Hybrid"),
        ({"type": "ENCODE", "source": "HDTV", "resolution": "1080p"}, "HDTV"),
        ({"type": "ENCODE", "source": "HDTV", "resolution": "576i"}, "SDTV"),
        ({"type": "DISC", "is_disc": "DVD", "source": "PAL", "dvd_size": "DVD9"}, "DVD9"),
        ({"type": "REMUX", "source": "NTSC DVD"}, "DVD"),
        ({"type": "REMUX", "source": "HDDVD"}, "HD-DVD"),
        ({"type": "ENCODE", "source": "BluRay"}, "BluRay"),
    ],
)
def test_hawkeuno_source_type(fields, expected):
    tracker = HawkeUno({"TRACKERS": {"HAWKEUNO": {}}})

    assert tracker.get_source_type(Meta(**fields)) == expected


@pytest.mark.parametrize(
    "audio, expected",
    [
        ("DTS-HD MA 7.1 Auro3D", "DTS-HD MA Auro3D"),
        ("DTS-HD MA 5.1", "DTS-HD MA"),
        ("DTS:X 7.1", "DTS:X"),
        ("DTS-ES 6.1", "DTS"),
        ("Dubbed DD 5.1", "DD"),
        ("Opus 2.0", "OPUS"),
        ("LPCM 2.0", "LPCM"),
        ("", ""),
    ],
)
def test_hawkeuno_audio_format(audio, expected):
    tracker = HawkeUno({"TRACKERS": {"HAWKEUNO": {}}})

    assert tracker.get_audio_format(Meta(audio=audio)) == expected


@pytest.mark.asyncio
async def test_hawkeuno_release_tag_and_language_fallbacks(monkeypatch):
    tracker = HawkeUno({"TRACKERS": {"HAWKEUNO": {}}})
    monkeypatch.setattr(tracker, "get_description", lambda _meta: _noop())
    meta = Meta(
        category="TV",
        type="WEBDL",
        tmdb=123,
        service=None,
        tv_pack=True,
        season_pack_incomplete=True,
        season="S01",
        season_int=1,
        episode_int=3,
        audio_languages=["English", "Spanish", "German"],
        name="Show S01 WEB-DL",
        clean_name="Show.S01.WEB-DL",
        repack="RERIP",
    )

    data = await tracker.get_data(meta)

    assert data["release_tag"] == "INCOMPLETE"
    assert data["streaming_service"] == "NADA"
    assert data["media_language"] == "MULTI"
    assert data["season_pack"] == 1
    assert "episode_number" not in data
    assert tracker.get_release_tag(Meta(audio="Dubbed DD+ 5.1")) == "DUBBED"


async def _noop():
    return None
