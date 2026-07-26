"""Regression tests for Seedpool category and type mappings."""
# ruff: noqa: S101

import asyncio

from src.meta import Meta
from src.trackers.UNIT3D.seedpool import Seedpool


def _tracker() -> Seedpool:
    return Seedpool({"DEFAULT": {}, "TRACKERS": {"SEEDPOOL": {}}})


def test_seedpool_supports_music_game_and_book_categories():
    tracker = _tracker()

    assert {"MUSIC", "GAME", "BOOK"}.issubset(tracker.supported_categories)
    assert asyncio.run(tracker.get_category_id(Meta(category="MUSIC"))) == {"category_id": "5"}
    assert asyncio.run(tracker.get_category_id(Meta(category="GAME"))) == {"category_id": "3"}
    assert asyncio.run(tracker.get_category_id(Meta(category="BOOK"))) == {"category_id": "7"}
    assert asyncio.run(tracker.get_category_id(Meta(category="BOOK", audiobook=True))) == {"category_id": "9"}
    assert asyncio.run(tracker.get_category_id(Meta(category="GAME", name="FIFA 26"))) == {"category_id": "3"}


def test_seedpool_maps_music_book_and_game_types_to_current_site_ids():
    tracker = _tracker()

    assert asyncio.run(tracker.get_type_id(Meta(category="MUSIC", format="FLAC"))) == {"type_id": "11"}
    assert asyncio.run(tracker.get_type_id(Meta(category="BOOK", comic=True, type="CBZ"))) == {"type_id": "40"}
    assert asyncio.run(tracker.get_type_id(Meta(category="BOOK", audiobook=True, format="MP3"))) == {"type_id": "13"}
    assert asyncio.run(tracker.get_type_id(Meta(category="GAME", platform="Nintendo Switch"))) == {"type_id": "15"}
