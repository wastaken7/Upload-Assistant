"""Quick corrections offered with the "Input args that need correction" prompt."""

from __future__ import annotations

import pytest

import upload
from src.args import cli_option_choices
from src.meta import Meta


@pytest.fixture(autouse=True)
def setup_globals() -> None:
    upload.load_heavy_globals()


def test_choices_come_from_the_real_parser() -> None:
    choices = cli_option_choices()

    assert "movie" in choices["--category"]
    assert "WEB" in choices["--source"]
    assert "2160p" in choices["--resolution"]


def test_suggestions_use_the_parser_spelling_of_current_values() -> None:
    meta = Meta(category="MOVIE", type="WEBDL", source="Web", resolution="2160P", tmdb_id=12345, imdb_id=1234567, tag="-NOGRP", year=2016)

    values = upload._editarg_suggestions(meta)

    assert values["--category"] == "movie"
    assert values["--type"] == "webdl"
    assert values["--source"] == "WEB"
    assert values["--resolution"] == "2160p"
    assert values["--tmdb"] == "movie/12345"
    assert values["--imdb"] == "tt1234567"
    assert values["--tag"] == "NOGRP"
    assert values["--year"] == "2016"
    assert "--season" not in values


def test_values_the_parser_would_reject_are_left_empty() -> None:
    meta = Meta(category="TV", type="HDTV", source="Unlisted Source", resolution="1080p", season="S02", episode="E05")

    values = upload._editarg_suggestions(meta)

    assert values["--source"] == ""
    assert values["--tmdb"] == ""
    assert values["--season"] == "2"
    assert values["--episode"] == "5"


@pytest.mark.parametrize(
    ("meta", "expected", "absent"),
    [
        (
            Meta(category="GAME", igdb_id=1234, platform="PC", game_title="Fictional Quest", game_version="1.0.2", game_subcategory="full_game"),
            {"--igdb": "1234", "--platform": "pc", "--game-title": "Fictional Quest", "--game-version": "1.0.2", "--game-subcategory": "full_game"},
            ("--resolution", "--tmdb", "--asin"),
        ),
        (
            Meta(category="BOOK", title="Fictional Novel", author="Jane Doe", asin="B000000000", isbn="9780000000000", audiobook=False),
            {"--book-title": "Fictional Novel", "--author": "Jane Doe", "--asin": "B000000000", "--isbn": "9780000000000"},
            ("--resolution", "--igdb", "--book-narrator"),
        ),
        (
            Meta(category="MUSIC", artist="Fictional Band", title="Paper Moons", music_release={"fields": {"media": {"value": "WEB"}, "release_label": {"value": "Example Records"}}}),
            {"--music-artist": "Fictional Band", "--music-album": "Paper Moons", "--music-media": "web", "--music-label": "Example Records"},
            ("--resolution", "--tmdb", "--tag"),
        ),
        (
            Meta(category="TV", tmdb_id=1, tvdb_id=3, tvmaze_id=4, season="S01"),
            {"--tmdb": "tv/1", "--tvdb": "3", "--tvmaze": "4", "--season": "1"},
            ("--igdb", "--mal", "--music-artist"),
        ),
    ],
)
def test_suggestions_follow_the_category(meta: Meta, expected: dict[str, str], absent: tuple[str, ...]) -> None:
    values = upload._editarg_suggestions(meta)

    assert values["--category"] == str(meta.category).lower()
    for flag, value in expected.items():
        assert values[flag] == value
    for flag in absent:
        assert flag not in values


@pytest.mark.parametrize("category", ["MOVIE", "TV", "GAME", "BOOK", "MUSIC", "XXX"])
def test_every_suggested_flag_exists_in_the_parser(category: str) -> None:
    known = {item["label"] for item in upload.cli_argument_catalog()}

    assert set(upload._editarg_suggestions(Meta(category=category, audiobook=True, mal_id=1))) <= known
