"""Category-only CLI arguments imply the release category."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.args import Args
from src.meta import Meta
from src.prep_helpers import CATEGORY_ONLY_ARGS, detect_disc_and_category

# One valid command-line value for each category-only flag; flags without a value are switches.
FLAG_VALUES: dict[str, list[str]] = {
    "--igdb": ["000000"],
    "--steam": ["000000"],
    "--platform": ["pc"],
    "--game-title": ["Example Quest"],
    "--developer": ["Example Studio"],
    "--game-version": ["v1.0"],
    "--game-subcategory": ["dlc"],
    "--author": ["Example Author"],
    "--book-title": ["Example Book"],
    "--book-narrator": ["Example Narrator"],
    "--book-translator": ["Example Translator"],
    "--book-language": ["English"],
    "--isbn": ["0000000000"],
    "--asin": ["B000000000"],
    "--audible-url": ["https://www.audible.com/pd/Example-Book-Audiobook/B000000000"],
    "--openlibrary": ["OL0000000W"],
    "--comic": [],
    "--manga": [],
    "--magazine": [],
    "--newspaper": [],
    "--music-artist": ["Example Artist"],
    "--music-album": ["Example Album"],
    "--music-media": ["CD"],
    "--music-release-type": ["album"],
    "--music-release-year": ["2026"],
    "--music-edition-year": ["2026"],
    "--music-unknown-release": [],
    "--music-artist-role": ["Example Artist=guest"],
    "--music-request-id": ["000000"],
    "--music-group-id": ["000000"],
    "--music-watermark": ["Example watermark"],
    "--music-lineage": ["lineage.txt"],
    "--music-showcase": [],
    "--music-label": ["Example Label"],
    "--music-catalogue-number": ["EX-000"],
    "--music-genre": ["rock"],
    "--music-discogs-id": ["000000"],
    "--music-discogs-release-id": ["000000"],
    "--music-discogs-master-id": ["000000"],
    "--season": ["1"],
    "--episode": ["1"],
    "--manual-episode-title": ["Example Episode"],
    "--daily": ["2026-01-01"],
    "--tvmaze": ["000000"],
    "--tpdb": ["scenes/00000000-0000-0000-0000-000000000000"],
    "--blvckout": ["000000"],
}

FLAG_CATEGORIES = [(flag, category) for category, fields in CATEGORY_ONLY_ARGS.items() for flag in fields.values()]


def _run_detection(meta: Meta) -> None:
    prep = SimpleNamespace(disc_info_manager=SimpleNamespace(get_disc=AsyncMock(return_value=("", str(meta.path), {}, []))))
    asyncio.run(detect_disc_and_category(prep, meta))


def _detect(tmp_path, argv: list[str], filename: str = "Example.Release.2026.1080p.WEB-DL.mkv") -> Meta:
    release = tmp_path / filename
    release.write_bytes(b"not a real release")
    meta, _, _ = Args({"DEFAULT": {"screens": 1}}).parse([str(release), *argv], Meta())
    _run_detection(meta)
    return meta


def test_every_category_only_flag_has_a_test_value():
    assert {flag for flag, _ in FLAG_CATEGORIES} == set(FLAG_VALUES)


@pytest.mark.parametrize(("flag", "category"), FLAG_CATEGORIES)
def test_category_only_flag_sets_category(flag, category, tmp_path):
    meta = _detect(tmp_path, [flag, *FLAG_VALUES[flag]])

    assert meta.category == category


def test_without_category_flags_the_category_is_left_to_detection(tmp_path):
    meta = _detect(tmp_path, [])

    assert meta.category == ""


@pytest.mark.parametrize("flag", ["--multi", "--music-check-log", "--no-music-discogs", "--music-enrich", "--no-music-enrich"])
def test_behaviour_switches_do_not_set_category(flag, tmp_path):
    meta = _detect(tmp_path, [flag])

    assert meta.category == ""


def test_manual_category_wins_over_category_only_flags(tmp_path):
    meta = _detect(tmp_path, ["--category", "movie", "--igdb", "000000"])

    assert meta.category == "MOVIE"


def test_sports_category_is_not_replaced_by_tv_flags(tmp_path):
    meta = _detect(tmp_path, ["--category", "sports", "--season", "1"])

    # SPORTS is a tracker classification; TV or MOVIE is still decided later.
    assert meta.category == ""


@pytest.mark.parametrize(("filename", "category"), [("Example Book.epub", "BOOK"), ("Example Quest.nsp", "GAME")])
def test_tv_flags_do_not_replace_the_category_of_the_files(filename, category, tmp_path):
    meta = _detect(tmp_path, ["--season", "1"], filename)

    assert meta.category == category


@pytest.mark.parametrize(("argv", "category"), [(["--igdb", "000000"], "GAME"), (["--season", "1"], "TV")])
def test_edited_arguments_replace_an_automatic_movie_category(argv, category, tmp_path):
    release = tmp_path / "Example.Release.2026.1080p.WEB-DL.mkv"
    release.write_bytes(b"not a real release")
    parser = Args({"DEFAULT": {"screens": 1}})
    meta, _, _ = parser.parse([str(release)], Meta())
    _run_detection(meta)
    meta.category = "MOVIE"  # chosen by the later name-based detection

    meta, _, _ = parser.parse([str(release), *argv], meta)
    _run_detection(meta)

    assert meta.category == category


def test_tmdb_category_agreeing_with_flags_is_kept(tmp_path):
    meta = _detect(tmp_path, ["--tmdb", "tv/000000", "--season", "1"])

    assert meta.category == "TV"


def test_conflicting_flags_leave_the_category_to_detection(tmp_path):
    meta = _detect(tmp_path, ["--igdb", "000000", "--isbn", "0000000000"])

    assert meta.category == ""


def test_flags_conflicting_with_tmdb_keep_the_tmdb_category(tmp_path):
    meta = _detect(tmp_path, ["--tmdb", "movie/000000", "--igdb", "000000"])

    assert meta.category == "MOVIE"
