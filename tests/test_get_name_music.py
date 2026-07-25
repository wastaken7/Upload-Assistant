"""Regression tests for the default MUSIC naming convention."""

import asyncio

from src.get_name import NameManager
from src.meta import Meta


def test_default_music_name_uses_lst_naming_convention():
    meta = Meta(
        category="MUSIC",
        tag="-FiVE0",
        music_release={
            "fields": {
                "artist": {"value": "Taylor Swift"},
                "album": {"value": "Red"},
                "release_year": {"value": "2012"},
                "media": {"value": "WEB"},
            },
            "tracks": [{"codec": "FLAC", "bit_depth": 16, "sample_rate": 44100}],
        },
    )

    name_notag, name, clean_name, potential_missing = asyncio.run(NameManager({}).get_name(meta))

    assert name_notag == "Taylor Swift - Red 2012 WEB FLAC 16-bit 44.1 kHz"
    assert name == "Taylor Swift - Red 2012 WEB FLAC 16-bit 44.1 kHz-FiVE0"
    assert clean_name == name
    assert potential_missing == []


def test_default_music_name_omits_pcm_fields_for_lossy_codec():
    meta = Meta(
        category="MUSIC",
        artist="Artist",
        title="Album",
        year=2026,
        source="web",
        type="AAC",
        music_release={"tracks": [{"codec": "AAC", "bit_depth": 24, "sample_rate": 96000}]},
    )

    name_notag, *_ = asyncio.run(NameManager({}).get_name(meta))

    assert name_notag == "Artist - Album 2026 WEB AAC"
