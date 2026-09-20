# ruff: noqa: S101

from src.meta import Meta
from src.sports import detect_sports


def test_detects_sports_from_ufc_metadata() -> None:
    meta = Meta(
        title="UFC 331: Van vs. Pantoja 2",
        genres=["Action"],
        keywords=["mixed martial arts (mma)", "combat sports", "ufc"],
        overview="A mixed martial arts event produced by the Ultimate Fighting Championship.",
        production_companies=[{"name": "Ultimate Fighting Championship"}],
    )

    assert detect_sports(meta)


def test_detects_sports_from_category_or_genre() -> None:
    assert detect_sports(Meta(category="SPORTS"))
    assert detect_sports(Meta(genres=["Sport"]))
    assert detect_sports(Meta(genres=["Esportes"]))


def test_game_category_does_not_use_sports_metadata() -> None:
    assert not detect_sports(Meta(category="GAME", keywords=["UFC"]))


def test_detects_sports_from_release_title() -> None:
    assert detect_sports(Meta(name="Formula 1 2026 Round 08 Monaco Grand Prix 1080p"))


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
