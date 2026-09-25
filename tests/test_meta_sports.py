# ruff: noqa: S101

import pytest

from src.meta import Meta
from src.sports import detect_sports

DISTINCTIVE_COMPETITIONS = [
    "F1",
    "EPL",
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
@pytest.mark.parametrize("field", ["title", "original_title", "name", "name_notag", "regex_title"])
def test_detects_distinctive_competition_release(competition, field) -> None:
    release = f"{competition} 2099 Round 2"
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
    assert not detect_sports(Meta(category="MOVIE", title="Solheim Cupping Round 2"))


@pytest.mark.parametrize("competition", ["Formula 1", "Formula One", "NBA", "UFC", "Grand Prix", *DISTINCTIVE_COMPETITIONS])
@pytest.mark.parametrize("template", [
    "{competition}",
    "{competition} 2099",
    "{competition} Example Story",
    "{competition} Round Table Story",
    "Example: The Impossible {competition} Story",
    "Example Story About {competition} Round 2",
])
def test_competition_names_require_event_release_structure(competition, template) -> None:
    title = template.format(competition=competition)
    meta = Meta(
        category="TV", title=title,
        name=f"{title.replace(' ', '.')}.S01.2099.1080p.WEB-DL-GROUP",
    )

    assert not detect_sports(meta)


@pytest.mark.parametrize("competition", ["UFC", "Ultimate Fighting Championship"])
def test_detects_numbered_fighting_event(competition) -> None:
    assert detect_sports(Meta(title=f"{competition} 123 Example Event"))


@pytest.mark.parametrize("competition", ["F1", "Formula1", "Formula 1", "Formula One"])
def test_formula_grand_prix_is_event_detail(competition) -> None:
    release = f"{competition}.2099.Example.Grand.Prix.1080p.WEB-GROUP"

    assert detect_sports(Meta(category="TV", name=release))


def test_epl_matchup_is_sports() -> None:
    assert detect_sports(Meta(name="EPL.2099.01.02.Team.A.vs.Team.B.1080p.WEB-GROUP"))


@pytest.mark.parametrize("title", [
    "07.F1.2099.Round.08.Example.Race",
    "Example Formula 1 Grand Prix Story",
    "EPL Example Grand Prix Story",
    "F1 Example Grand Prixes Story",
    "F100 Round 2",
    "EPLExample Team A vs Team B",
])
def test_new_sports_matches_remain_conservative(title) -> None:
    assert not detect_sports(Meta(category="TV", title=title))


def test_event_details_in_other_metadata_do_not_complete_title() -> None:
    meta = Meta(title="NBA Example Story", name="Example Round 2", overview="Example A vs Example B")

    assert not detect_sports(meta)


@pytest.mark.parametrize("event", ["Final", "Semifinal", "Quarter Final", "Round 2", "Qualifying", "Player A vs. Player B"])
@pytest.mark.parametrize("field", ["title", "name"])
@pytest.mark.parametrize("competition", ["Australian Open", "Formula1", "NBA"])
def test_competition_requires_event_context(event, field, competition) -> None:
    release = f"{competition} 2099 {event}"
    if field == "name":
        release = release.replace(" ", ".") + ".1080p-GROUP"

    assert detect_sports(Meta(category="TV", **{field: release}))


def test_detects_sports_from_ufc_metadata() -> None:
    meta = Meta(
        title="UFC 331: Fighter A vs. Fighter B",
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
    assert detect_sports(Meta(name="Formula 1 2026 Round 08 Example Grand Prix 1080p"))


def test_generic_event_phrase_does_not_identify_sports() -> None:
    assert not detect_sports(Meta(category="TV", title="Example Boxing Event"))


@pytest.mark.parametrize("category", ["TV", "MOVIE"])
@pytest.mark.parametrize("title", [
    "The Wimbledon Example Mystery",
    "The Wimbledon Example Crime",
    "Wimbledon Example Mystery",
    "The World Cup Example Mystery",
    "Tour de France Example Mystery",
    "The Australian Open Example Mystery",
    "Australian Open Example Mystery",
    "Australian Open",
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
@pytest.mark.parametrize("title", ["Wimbledon 2099 Example Round", "Australian Open 2099"])
def test_ambiguous_event_title_uses_explicit_sports_override(manual_category, expected, title) -> None:
    meta = Meta(category="TV", title=title, manual_category=manual_category)

    assert detect_sports(meta) is expected


@pytest.mark.parametrize("category", ["TV", "MOVIE"])
def test_explicit_category_disables_automatic_sports_detection(category) -> None:
    meta = Meta(category=category, title="UFC 123 Example Event", manual_category=category.lower())

    assert not detect_sports(meta)


@pytest.mark.parametrize("title", ["Example Open", "Example Cup", "Example Tour", "Example Championship"])
def test_generic_competition_words_do_not_identify_sports(title) -> None:
    assert not detect_sports(Meta(category="TV", title=title))


def test_does_not_classify_unrelated_action_movie_as_sports() -> None:
    meta = Meta(
        category="MOVIE",
        title="Example Drama",
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
