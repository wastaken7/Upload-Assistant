import asyncio

import pytest

from src.audio import AudioManager
from src.meta import Meta


@pytest.mark.parametrize(
    ("channels", "commercial", "format_settings", "expected"),
    [
        ("8", "Dolby Digital Plus", "Dolby Surround EX", "DD+ EX 7.1"),
        ("8", "", "Dolby Surround EX", "DD+ EX 7.1"),
        ("6", "Dolby Digital Plus", "Dolby Surround EX", "DD+ EX 5.1"),
        ("8", "Dolby Digital Plus", "", "DD+ 7.1"),
    ],
)
def test_dolby_digital_plus_ex_audio_name(channels: str, commercial: str, format_settings: str, expected: str) -> None:
    mediainfo = {
        "media": {
            "track": [
                {
                    "@type": "Audio",
                    "Format": "AC-3",
                    "Format_Commercial": commercial,
                    "Format_Settings": format_settings,
                    "Channels": channels,
                    "Language": "en",
                }
            ]
        }
    }
    meta = Meta(mediainfo=mediainfo, original_language="en")

    audio, _, _ = asyncio.run(AudioManager({}).get_audio_v2(mediainfo, meta, None))

    assert audio == expected  # noqa: S101
