import asyncio

import pytest

from src.meta import Meta
from src.trackers.UNIT3D.dreadvault import DreadVault
from src.trackersetup import tracker_class_map


def _tracker() -> DreadVault:
    return DreadVault({"TRACKERS": {"DREADVAULT": {"api_key": ""}}})


def test_dreadvault_is_registered_with_full_tracker_name():
    assert tracker_class_map["DREADVAULT"] is DreadVault  # noqa: S101
    assert DreadVault.display_name == "DreadVault"  # noqa: S101
    assert DreadVault.supported_categories == ("TV", "MOVIE")  # noqa: S101


@pytest.mark.parametrize(
    "combined_genres",
    [
        "Horror",
        "Horror, Thriller",
        "Horror, Mystery, Thriller",
        "Thriller, Horror",
        ["Horror"],
        ["Horror", "Thriller"],
    ],
)
def test_dreadvault_accepts_horror_regardless_of_genre_order(combined_genres):
    tracker = _tracker()
    meta = Meta(combined_genres=combined_genres, unattended=True)
    assert asyncio.run(tracker.get_additional_checks(meta))  # noqa: S101


def test_dreadvault_accepts_horror_from_keywords():
    tracker = _tracker()
    meta = Meta(combined_genres="", keywords=["horror"], unattended=True)
    assert asyncio.run(tracker.get_additional_checks(meta))  # noqa: S101


def test_dreadvault_rejects_non_horror_when_unattended():
    tracker = _tracker()
    meta = Meta(combined_genres="Action, Comedy", unattended=True)
    assert not asyncio.run(tracker.get_additional_checks(meta))  # noqa: S101


def test_dreadvault_rejects_adult_content():
    tracker = _tracker()
    meta = Meta(combined_genres="Horror", keywords=["porn"], unattended=True)
    assert not asyncio.run(tracker.get_additional_checks(meta))  # noqa: S101
