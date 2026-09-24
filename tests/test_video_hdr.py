# ruff: noqa: S101

import asyncio

import pytest

from src.video import VideoManager


def test_empty_bdinfo_uses_mediainfo_hdr_metadata() -> None:
    mediainfo = {
        "media": {
            "track": [
                {"@type": "General"},
                {
                    "@type": "Video",
                    "colour_primaries": "BT.2020",
                    "transfer_characteristics": "PQ",
                    "HDR_Format_String": "SMPTE ST 2094 App 4, Version 1, HDR10+ Profile B compatible",
                },
            ]
        }
    }

    assert asyncio.run(VideoManager().get_hdr(mediainfo, {})) == "HDR10+"


@pytest.mark.parametrize("mediainfo", [None, {}, {"media": {}}, {"media": {"track": []}}, {"media": {"track": [{"@type": "General"}]}}])
def test_missing_video_track_has_no_hdr(mediainfo) -> None:
    assert asyncio.run(VideoManager().get_hdr(mediainfo, {})) == ""


def test_hdr_selects_video_track_by_type() -> None:
    mediainfo = {
        "media": {
            "track": [
                {"@type": "General"},
                {"@type": "Audio"},
                {"@type": "Video", "colour_primaries": "BT.2020", "HDR_Format": "HDR10", "HDR_Format_String": "Dolby Vision, HDR10 compatible"},
            ]
        }
    }

    assert asyncio.run(VideoManager().get_hdr(mediainfo, None)) == "DV HDR"


def test_sdr_avi_has_no_hdr() -> None:
    mediainfo = {"media": {"track": [{"@type": "General", "Format": "AVI"}, {"@type": "Video", "Format": "MPEG-4 Visual"}]}}

    assert asyncio.run(VideoManager().get_hdr(mediainfo, None)) == ""
