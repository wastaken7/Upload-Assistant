"""Regression tests for Zenith-specific names."""

import asyncio

from src.meta import Meta
from src.trackers.UNIT3D.znth import Zenith


def test_zenith_supports_music_and_uses_its_music_naming_guide():
    meta = Meta(
        category="MUSIC",
        tag="-FiVE0",
        music_release={
            "fields": {
                "artist": {"value": "Salem"},
                "album": {"value": "King Night"},
                "release_year": {"value": "2010"},
                "media": {"value": "WEB"},
                "format": {"value": "FLAC"},
                "release_type": {"value": "Single"},
            },
            "tracks": [{"codec": "FLAC", "bit_depth": 24, "sample_rate": 44100}],
        },
    )

    tracker = Zenith({"DEFAULT": {}, "TRACKERS": {"ZENITH": {}}})

    assert "MUSIC" in tracker.supported_categories
    assert asyncio.run(tracker.get_name(meta))["name"] == "Salem - King Night (2010) - [WEB FLAC 24bit-44.1kHz Single]-FiVE0"


def test_zenith_music_name_omits_calculated_lossless_bitrate():
    meta = Meta(
        category="MUSIC",
        music_release={
            "fields": {
                "artist": {"value": "Kanye West"},
                "album": {"value": "808s & Heartbreak"},
                "release_year": {"value": "2008"},
                "media": {"value": "CD"},
                "format": {"value": "FLAC"},
            },
            "tracks": [{"codec": "FLAC", "bit_depth": 16, "sample_rate": 44100, "bitrate": 737000}],
        },
    )

    name = asyncio.run(Zenith({"DEFAULT": {}, "TRACKERS": {"ZENITH": {}}}).get_name(meta))["name"]

    assert name == "Kanye West - 808s & Heartbreak (2008) - [CD FLAC 16bit-44.1kHz]"


def test_zenith_music_additional_data_sends_valid_external_ids():
    meta = Meta(
        category="MUSIC",
        music_release={
            "external_ids": {
                "musicbrainz_release": "c0d17e85-3a36-4dc8-9a88-c188a5e78b0d",
                "musicbrainz_release_group": "3bdb2b21-f6f5-3f8b-a1e0-067f8bb71940",
                "discogs_release": "1791341",
                "discogs_master": "28700",
            }
        },
    )

    data = asyncio.run(Zenith({"DEFAULT": {}, "TRACKERS": {"ZENITH": {}}}).get_additional_data(meta))

    assert data == {
        "exists_on_musicbrainz": "1",
        "musicbrainz_release_id": "c0d17e85-3a36-4dc8-9a88-c188a5e78b0d",
        "musicbrainz_release_group_id": "3bdb2b21-f6f5-3f8b-a1e0-067f8bb71940",
        "exists_on_discogs": "1",
        "discogs_release_id": "1791341",
        "discogs_master_id": "28700",
    }


def test_zenith_music_additional_data_omits_invalid_or_disabled_external_ids():
    meta = Meta(
        category="MUSIC",
        music_discogs_enabled=False,
        music_release={"external_ids": {"musicbrainz_release": "invalid", "discogs_release": "not-a-number"}},
    )

    assert asyncio.run(Zenith({"DEFAULT": {}, "TRACKERS": {"ZENITH": {}}}).get_additional_data(meta)) == {}


def test_zenith_music_type_id_comes_from_the_analyzed_codec():
    meta = Meta(category="MUSIC", music_release={"fields": {"format": {"value": "FLAC"}}})

    type_data = asyncio.run(Zenith({"DEFAULT": {}, "TRACKERS": {"ZENITH": {}}}).get_type_id(meta))

    assert type_data == {"type_id": "7"}
