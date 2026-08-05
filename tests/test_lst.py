"""Regression tests for LST-specific upload payloads."""

import asyncio

from src.meta import Meta
from src.trackers.UNIT3D.lst import LST


def test_lst_music_payload_includes_discogs_release_and_master_ids():
    meta = Meta(
        category="MUSIC",
        music_release={"external_ids": {"discogs_release": "https://www.discogs.com/release/12345-example", "discogs_master": "master/67890"}},
    )

    data = asyncio.run(LST({"DEFAULT": {}, "TRACKERS": {"LST": {}}}).get_additional_data(meta))

    assert data["release_exists_on_discogs"] == "1"
    assert data["discogs"] == "12345"
    assert data["discogs_master_id"] == "67890"
    assert data["extra_discogs_ids"] == ""
    assert data["extra_discogs_master_ids"] == ""


def test_lst_music_payload_omits_discogs_existence_flag_for_invalid_ids():
    meta = Meta(category="MUSIC", music_release={"external_ids": {"discogs_release": "not-an-id"}})

    data = asyncio.run(LST({"DEFAULT": {}, "TRACKERS": {"LST": {}}}).get_additional_data(meta))

    assert "release_exists_on_discogs" not in data


def test_lst_music_name_uses_technical_fields_for_lossless_releases():
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

    name = asyncio.run(LST({"DEFAULT": {}, "TRACKERS": {"LST": {}}}).get_name(meta))["name"]

    assert name == "Taylor Swift - Red 2012 WEB FLAC 16-bit 44.1 kHz-FiVE0"


def test_lst_music_name_ignores_invalid_sample_rate():
    meta = Meta(
        category="MUSIC",
        music_release={
            "fields": {
                "artist": {"value": "Artist"},
                "album": {"value": "Album"},
                "release_year": {"value": "2000"},
                "media": {"value": "CD"},
                "nfo_sample_rate": {"value": "unknown"},
            },
            "tracks": [{"codec": "FLAC", "bit_depth": 16}],
        },
    )

    name = asyncio.run(LST({"DEFAULT": {}, "TRACKERS": {"LST": {}}}).get_name(meta))["name"]

    assert name == "Artist - Album 2000 CD FLAC 16-bit"


def test_lst_audiobook_name_omits_lossy_technical_fields():
    meta = Meta(category="BOOK", audiobook=True, author="Ernest Cline", title="Ready Player One", year=2011, source="WEB", type="M4B", tag="zeno")

    name = asyncio.run(LST({"DEFAULT": {}, "TRACKERS": {"LST": {}}}).get_name(meta))["name"]

    assert name == "Ernest Cline - Ready Player One 2011 WEB M4B-zeno"


def test_lst_ebook_name_includes_edition_type_and_isbn():
    meta = Meta(
        category="BOOK",
        author="Liu Cixin",
        title="The Three-Body Problem",
        edition="Revised Edition",
        year=2008,
        type="PDF",
        ocr=True,
        isbn="978-0765377067",
        tag="-GROUP",
    )

    name = asyncio.run(LST({"DEFAULT": {}, "TRACKERS": {"LST": {}}}).get_name(meta))["name"]

    assert name == "Liu Cixin - The Three-Body Problem Revised Edition 2008 PDF OCR 9780765377067-GROUP"
