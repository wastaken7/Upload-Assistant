"""Regression tests for DarkPeers-specific BOOK and MUSIC title rules."""

import asyncio

from src.meta import Meta
from src.trackers.UNIT3D.darkpeers import DarkPeers


def _name(meta: Meta) -> str:
    config = {"DEFAULT": {"tmdb_api": "test-key"}, "TRACKERS": {"DARKPEERS": {}}}
    return asyncio.run(DarkPeers(config).get_name(meta))["name"]


def test_darkpeers_music_name_uses_required_folder_style():
    meta = Meta(
        category="MUSIC",
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

    assert _name(meta) == "Taylor Swift - Red (2012) - WEB FLAC 16-44.1"


def test_darkpeers_ebook_name_includes_book_elements():
    meta = Meta(
        category="BOOK",
        author="Liu Cixin",
        title="The Three-Body Problem",
        edition="Revised Edition",
        year=2008,
        type="EPUB",
        isbn="978-0765377067",
        source="RETAIL",
        ocr=True,
    )

    assert _name(meta) == "Liu Cixin - The Three-Body Problem 2008 Revised Edition EPUB 9780765377067 Retail OCR"


def test_darkpeers_audiobook_name_includes_format_bitrate_isbn_and_tag():
    meta = Meta(
        category="BOOK",
        audiobook=True,
        author="Ernest Cline",
        title="Ready Player One",
        year=2011,
        type="MP3",
        audiobook_bitrate=64,
        isbn="978-0-307-88743-6",
        tag="GROUP",
    )

    assert _name(meta) == "Ernest Cline - Ready Player One 2011 MP3 64 9780307887436-GROUP"


def _additional_checks(meta: Meta) -> bool:
    config = {"DEFAULT": {"tmdb_api": "test-key"}, "TRACKERS": {"DARKPEERS": {}}}
    return asyncio.run(DarkPeers(config).get_additional_checks(meta))


def test_darkpeers_evo_webdl_allowed_and_non_webdl_blocked():
    evo_webdl = Meta(category="MOVIE", type="WEBDL", tag="-EVO", audio_languages=["English"])
    evo_encode = Meta(category="MOVIE", type="ENCODE", tag="-EVO", audio_languages=["English"])
    evo_remux = Meta(category="MOVIE", type="REMUX", tag="EVO", audio_languages=["English"])

    assert _additional_checks(evo_webdl) is True
    assert _additional_checks(evo_encode) is False
    assert _additional_checks(evo_remux) is False


def test_darkpeers_hdt_remux_allowed_and_non_remux_blocked():
    hdt_remux = Meta(category="MOVIE", type="REMUX", tag="-HDT", audio_languages=["English"])
    hdt_webdl = Meta(category="MOVIE", type="WEBDL", tag="-HDT", audio_languages=["English"])
    hdt_encode = Meta(category="MOVIE", type="ENCODE", tag="HDT", audio_languages=["English"])

    assert _additional_checks(hdt_remux) is True
    assert _additional_checks(hdt_webdl) is False
    assert _additional_checks(hdt_encode) is False


def test_darkpeers_hardcoded_subs_blocked_in_interactive_and_unattended():
    subs_interactive = Meta(category="MOVIE", type="WEBDL", tag="-GRP", hardcoded_subs=True, unattended=False, audio_languages=["English"])
    subs_unattended = Meta(category="MOVIE", type="WEBDL", tag="-GRP", hardcoded_subs=True, unattended=True, audio_languages=["English"])
    no_subs_unattended = Meta(category="MOVIE", type="WEBDL", tag="-GRP", hardcoded_subs=False, unattended=True, audio_languages=["English"])

    assert _additional_checks(subs_interactive) is False
    assert _additional_checks(subs_unattended) is False
    assert _additional_checks(no_subs_unattended) is True

