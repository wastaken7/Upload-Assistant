"""Regression tests for DarkPeers-specific BOOK and MUSIC title rules."""

import asyncio
from unittest.mock import AsyncMock

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


def test_darkpeers_book_name_never_uses_publisher_as_author():
    meta = Meta(category="BOOK", publisher="Publisher Name", title="Book Title", year=2026, type="EPUB", isbn="978-0-123456-47-2")

    assert _name(meta) == "Book Title 2026 EPUB 9780123456472"


def test_darkpeers_book_name_preserves_alphanumeric_asin():
    meta = Meta(category="BOOK", author="Author", title="Book Title", year=2026, type="EPUB", asin="B01N5AX3TQ")

    assert _name(meta) == "Author - Book Title 2026 EPUB B01N5AX3TQ"


def test_darkpeers_replaces_generic_dual_audio_with_rule_matrix_label():
    meta = Meta(category="MOVIE", name="Anime 2026 1080p WEB-DL Dual-Audio-TEAM", language_checked=True, original_language="Japanese", audio_languages=["Japanese", "French"])

    assert _name(meta) == "Anime 2026 1080p WEB-DL French MULTi-TEAM"


def test_darkpeers_preserves_detected_original_scene_name():
    meta = Meta(category="MOVIE", name="Generated Name", scene=True, scene_name="Original.Release.2026-GRP", language_checked=True)

    assert _name(meta) == "Original.Release.2026-GRP"


def _additional_checks(meta: Meta) -> bool:
    config = {"DEFAULT": {"tmdb_api": "test-key", "thumbnail_size": "350"}, "TRACKERS": {"DARKPEERS": {}}}
    return asyncio.run(DarkPeers(config).get_additional_checks(meta))


def test_darkpeers_evo_webdl_allowed_and_non_webdl_blocked():
    evo_webdl = Meta(category="MOVIE", type="WEBDL", tag="-EVO", audio_languages=["English"], resolution="1080p", screens=3)
    evo_encode = Meta(category="MOVIE", type="ENCODE", tag="-EVO", audio_languages=["English"], resolution="1080p", screens=3)
    evo_remux = Meta(category="MOVIE", type="REMUX", tag="EVO", audio_languages=["English"], resolution="1080p", screens=3)

    assert _additional_checks(evo_webdl) is True
    assert _additional_checks(evo_encode) is False
    assert _additional_checks(evo_remux) is False


def test_darkpeers_hdt_remux_allowed_and_non_remux_blocked():
    hdt_remux = Meta(category="MOVIE", type="REMUX", tag="-HDT", audio_languages=["English"], resolution="1080p", screens=3)
    hdt_webdl = Meta(category="MOVIE", type="WEBDL", tag="-HDT", audio_languages=["English"], resolution="1080p", screens=3)
    hdt_encode = Meta(category="MOVIE", type="ENCODE", tag="HDT", audio_languages=["English"], resolution="1080p", screens=3)

    assert _additional_checks(hdt_remux) is True
    assert _additional_checks(hdt_webdl) is False
    assert _additional_checks(hdt_encode) is False


def test_darkpeers_hardcoded_subs_blocked_in_interactive_and_unattended():
    subs_interactive = Meta(category="MOVIE", type="WEBDL", tag="-GRP", hardcoded_subs=True, unattended=False, audio_languages=["English"], resolution="1080p", screens=3)
    subs_unattended = Meta(category="MOVIE", type="WEBDL", tag="-GRP", hardcoded_subs=True, unattended=True, audio_languages=["English"], resolution="1080p", screens=3)
    no_subs_unattended = Meta(category="MOVIE", type="WEBDL", tag="-GRP", hardcoded_subs=False, unattended=True, audio_languages=["English"], resolution="1080p", screens=3)

    assert _additional_checks(subs_interactive) is False
    assert _additional_checks(subs_unattended) is False
    assert _additional_checks(no_subs_unattended) is True


def test_darkpeers_video_language_rule_requires_original_audio_with_accepted_subtitles():
    original_with_subtitles = Meta(
        category="MOVIE", unattended=True, audio_languages=["jpn"], subtitle_languages=["Swedish"], original_language="Japanese", resolution="1080p", screens=3
    )
    foreign_dub_with_subtitles = Meta(
        category="MOVIE", unattended=True, audio_languages=["Spanish"], subtitle_languages=["English"], original_language="Japanese", resolution="1080p", screens=3
    )

    assert _additional_checks(original_with_subtitles) is True
    assert _additional_checks(foreign_dub_with_subtitles) is False


def test_darkpeers_rejects_unsupported_resolution():
    unsupported = Meta(category="MOVIE", unattended=True, audio_languages=["English"], resolution="1440p", screens=3)

    assert _additional_checks(unsupported) is False


def test_darkpeers_rejects_multi_season_and_video_archives():
    seasons = Meta(category="TV", unattended=True, audio_languages=["English"], resolution="1080p", screens=3, filelist=["Show.S01E01.mkv", "Show.S02E01.mkv"])
    archive = Meta(category="MOVIE", unattended=True, audio_languages=["English"], resolution="1080p", screens=3, filelist=["Movie.part01.rar"])

    assert _additional_checks(seasons) is False
    assert _additional_checks(archive) is False


def test_darkpeers_tv_scope_ignores_parent_directory_and_detects_episode_season():
    meta = Meta(category="TV", name="Show S01", path="C:/media/Complete Series/Show S01", filelist=["Show.S01E01.mkv"])
    adapter = DarkPeers({"DEFAULT": {"tmdb_api": "test-key"}, "TRACKERS": {"DARKPEERS": {}}})

    assert adapter.validate_tv_scope(meta) is True
    assert adapter._is_single_tv_season(meta) is True


def test_darkpeers_confirmed_folder_check_continues_to_evo_validation():
    meta = Meta(category="MOVIE", type="ENCODE", tag="-EVO", keep_folder=True, audio_languages=["English"], resolution="1080p", screens=3)
    adapter = DarkPeers({"DEFAULT": {"tmdb_api": "test-key"}, "TRACKERS": {"DARKPEERS": {}}})
    adapter._confirm_or_skip = AsyncMock(return_value=True)

    assert asyncio.run(adapter.get_additional_checks(meta)) is False


def test_darkpeers_book_language_is_unrestricted_but_author_is_required_unattended():
    portuguese = Meta(category="BOOK", unattended=True, author="Autor", publisher="Editora", type="EPUB", isbn="978-0-123456-47-2", book_language="Portuguese")
    no_author = Meta(category="BOOK", unattended=True, publisher="Editora", type="EPUB", isbn="978-0-123456-47-2")

    assert _additional_checks(portuguese) is True
    assert _additional_checks(no_author) is False


def test_darkpeers_game_requires_scene_rars_nfo_and_instructions():
    valid_game = Meta(
        category="GAME",
        unattended=True,
        scene=True,
        scene_nfo_file="release.nfo",
        filelist=["release.r00", "release.rar"],
        description="Installation instructions: mount and install.",
    )
    iso = Meta(category="GAME", unattended=True, scene=True, scene_nfo_file="release.nfo", filelist=["release.iso"], description="Installation instructions")

    assert _additional_checks(valid_game) is True
    assert _additional_checks(iso) is False
