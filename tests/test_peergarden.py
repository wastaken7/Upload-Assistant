"""Regression tests for PeerGarden tracker mappings."""

from __future__ import annotations

import asyncio

from src.meta import Meta
from src.trackers.UNIT3D.peergarden import PeerGarden


def test_peergarden_reverse_book_category_mapping():
    tracker = PeerGarden({"DEFAULT": {}, "TRACKERS": {"PEERGARDEN": {}}})

    categories = asyncio.run(tracker.get_category_id(Meta(), reverse=True))

    assert categories["6"] == "BOOK"


def test_peergarden_unknown_resolution_uses_other_id():
    tracker = PeerGarden({"DEFAULT": {}, "TRACKERS": {"PEERGARDEN": {}}})

    resolution = asyncio.run(tracker.get_resolution_id(Meta(), resolution="unknown"))

    assert resolution == {"resolution_id": "10"}
