import asyncio

import pytest

from src.meta import _TRACKER_ID_ALIASES, Meta
from src.trackers.UNIT3D.dreadvault import DreadVault
from src.trackersetup import tracker_class_map


def _tracker() -> DreadVault:
    return DreadVault({"TRACKERS": {"DREADVAULT": {"api_key": ""}}})


def test_dreadvault_is_registered_with_full_tracker_name():
    assert tracker_class_map["DREADVAULT"] is DreadVault  # noqa: S101
    assert DreadVault.display_name == "DreadVault"  # noqa: S101
    assert DreadVault.supported_categories == ("TV", "MOVIE")  # noqa: S101


def test_dreadvault_dvl_alias_resolves_to_the_canonical_name():
    # DVL is the site's own abbreviation, confirmed by DreadVault staff.
    assert _TRACKER_ID_ALIASES["DVL"] == "DREADVAULT"  # noqa: S101
    assert Meta().canonical_tracker_name("dvl") == "DREADVAULT"  # noqa: S101


def test_dreadvault_bans_the_published_groups():
    # Published on the site's rules page 2026-08-24; DreadVault exposes no
    # /api/bannedReleaseGroups endpoint, so this list is maintained by hand.
    assert set(DreadVault.banned_groups) == {  # noqa: S101
        "BONE",
        "EVO",
        "NeoNoir",
        "PSA",
        "RARBG",
        "VXT",
        "YIFY",
        "YTS",
    }


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


def test_dreadvault_accepts_horror_inside_a_compound_keyword():
    tracker = _tracker()
    meta = Meta(combined_genres="Drama, Thriller", keywords=["psychological horror"], unattended=True)
    assert asyncio.run(tracker.get_additional_checks(meta))  # noqa: S101


def test_dreadvault_accepts_horror_with_incidental_mature_keywords():
    tracker = _tracker()
    meta = Meta(combined_genres="Horror, Thriller", keywords=["adult animation", "orgy", "erotic"], unattended=True)
    assert asyncio.run(tracker.get_additional_checks(meta))  # noqa: S101


def test_dreadvault_rejects_non_horror_when_unattended():
    tracker = _tracker()
    meta = Meta(combined_genres="Action, Comedy", unattended=True)
    assert not asyncio.run(tracker.get_additional_checks(meta))  # noqa: S101


def test_dreadvault_only_blocks_exact_duplicates():
    assert DreadVault.exact_match_only is True  # noqa: S101


def test_dreadvault_adult_keyword_skips_when_unattended():
    tracker = _tracker()
    meta = Meta(combined_genres="Horror", keywords=["porn"], unattended=True)
    assert not asyncio.run(tracker.get_additional_checks(meta))  # noqa: S101


def test_dreadvault_rejects_adult_content():
    tracker = _tracker()
    meta = Meta(combined_genres="Horror", keywords=["porn"], unattended=True)
    assert not asyncio.run(tracker.get_additional_checks(meta))  # noqa: S101
