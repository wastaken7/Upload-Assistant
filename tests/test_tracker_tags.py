import asyncio
from types import SimpleNamespace

import pytest

from src.trackers.bjshare import BJShare
from src.trackers.brasiltracker import BrasilTracker


@pytest.mark.parametrize("tracker_class", [BJShare, BrasilTracker])
def test_get_tags_removes_accents_from_mapped_tags(tracker_class):
    tracker = object.__new__(tracker_class)
    tracker.main_tmdb_data = {}
    meta = SimpleNamespace(category="MOVIE", genres=["Action", "Mystery"], keywords=[])

    tags = asyncio.run(tracker.get_tags(meta))

    assert tags == "acao, misterio"  # noqa: S101
    assert tags.isascii()  # noqa: S101
