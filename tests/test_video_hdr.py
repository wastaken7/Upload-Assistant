# ruff: noqa: S101

import asyncio

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
