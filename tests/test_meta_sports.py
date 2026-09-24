# ruff: noqa: S101

import pytest

from src.meta import Meta
from src.sports import detect_sports

DISTINCTIVE_COMPETITIONS = [
    "Formula1",
    "Australian Open",
    "Copa Libertadores",
    "Copa Sudamericana",
    "Africa Cup of Nations",
    "Davis Cup",
    "Billie Jean King Cup",
    "Ryder Cup",
    "Solheim Cup",
    "World Snooker Championship",
    "PDC World Darts Championship",
]


@pytest.mark.parametrize("competition", DISTINCTIVE_COMPETITIONS)
@pytest.mark.parametrize("field", ["title", "name"])
def test_detects_distinctive_competition_release(competition, field) -> None:
    release = f"{competition} 2099 Example Round"
    if field == "name":
        release = release.upper().replace(" ", ".") + ".1080p-GROUP"

    assert detect_sports(Meta(category="TV", **{field: release}))


@pytest.mark.parametrize("competition", DISTINCTIVE_COMPETITIONS)
def test_competition_in_subject_metadata_does_not_identify_sports(competition) -> None:
    meta = Meta(
        category="TV", title="Example Family Story",
        keywords=[competition], overview=f"An example family watches the {competition}.",
    )

    assert not detect_sports(meta)


def test_distinctive_competition_requires_token_boundaries() -> None:
    assert not detect_sports(Meta(category="MOVIE", title="Example Solheim Cupping Story"))


def test_detects_sports_from_ufc_metadata() -> None:
    meta = Meta(
        title="UFC 331: Van vs. Pantoja 2",
        genres=["Action"],
        keywords=["mixed martial arts (mma)", "combat sports", "ufc"],
        overview="A mixed martial arts event produced by the Ultimate Fighting Championship.",
        production_companies=[{"name": "Ultimate Fighting Championship"}],
    )

    assert detect_sports(meta)


def test_detects_sports_from_explicit_category() -> None:
    assert detect_sports(Meta(category="SPORTS"))


@pytest.mark.parametrize("category", ["TV", "MOVIE"])
@pytest.mark.parametrize("metadata", [
    {"genres": ["Sport"]},
    {"genres": ["Esportes"]},
    {"keywords": ["baseball", "sport", "wrestling"]},
    {"combined_genres": "Animation, Comedy, Sport"},
    {"overview": "An example family attends a sports event and dreams of the Olympics."},
    {"production_companies": [{"name": "Ultimate Fighting Championship"}]},
])
def test_sports_subject_matter_does_not_override_regular_categories(category, metadata) -> None:
    meta = Meta(category=category, title="Example Story", **metadata)

    assert not detect_sports(meta)


def test_game_category_does_not_use_sports_metadata() -> None:
    assert not detect_sports(Meta(category="GAME", keywords=["UFC"]))


def test_detects_sports_from_release_title() -> None:
    assert detect_sports(Meta(name="Formula 1 2026 Round 08 Monaco Grand Prix 1080p"))


def test_detects_sports_event_from_title_without_league_name() -> None:
    assert detect_sports(Meta(category="TV", title="Example Boxing Event"))


@pytest.mark.parametrize("category", ["TV", "MOVIE"])
@pytest.mark.parametrize("title", [
    "The Wimbledon Example Mystery",
    "The Wimbledon Example Crime",
    "Wimbledon Example Mystery",
    "The World Cup Example Mystery",
    "Tour de France Example Mystery",
])
def test_event_mentions_in_story_titles_do_not_identify_sports(category, title) -> None:
    meta = Meta(
        category=category,
        title=title,
        original_title=title,
        regex_title=title,
        name=f"{title.replace(' ', '.')}.2099.1080p.WEB-DL-GROUP",
        name_notag=f"{title} 2099 1080p WEB-DL",
        genres=["Drama", "Sport"],
        keywords=["sport"],
    )

    assert not detect_sports(meta)


@pytest.mark.parametrize("manual_category,expected", [(None, False), ("sports", True), ("tv", False), ("movie", False)])
def test_ambiguous_event_title_uses_explicit_sports_override(manual_category, expected) -> None:
    meta = Meta(category="TV", title="Wimbledon 2099 Example Round", manual_category=manual_category)

    assert detect_sports(meta) is expected


@pytest.mark.parametrize("category", ["TV", "MOVIE"])
def test_explicit_category_disables_automatic_sports_detection(category) -> None:
    meta = Meta(category=category, title="Example Boxing Event", manual_category=category.lower())

    assert not detect_sports(meta)


@pytest.mark.parametrize("title", ["Example Open", "Example Cup", "Example Tour", "Example Championship"])
def test_generic_competition_words_do_not_identify_sports(title) -> None:
    assert not detect_sports(Meta(category="TV", title=title))


def test_does_not_classify_unrelated_action_movie_as_sports() -> None:
    meta = Meta(
        category="MOVIE",
        title="The Fighter",
        genres=["Action", "Drama"],
        keywords=["competition", "training"],
        overview="A retired soldier enters a dangerous underground competition.",
    )

    assert not detect_sports(meta)


def test_sports_acronyms_require_token_boundaries() -> None:
    assert not detect_sports(Meta(title="The Stuff Club"))


def test_is_sports_defaults_to_false_and_is_serialized() -> None:
    meta = Meta()

    assert meta.is_sports is False
    assert meta.to_dict()["is_sports"] is False
