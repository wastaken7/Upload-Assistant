"""Regression tests for InfinityHD TV naming rules."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.meta import Meta
from src.trackers.UNIT3D.darkpeers import DarkPeers
from src.trackers.UNIT3D.infinityhd import InfinityHD


@pytest.mark.parametrize("tracker_cls", [InfinityHD, DarkPeers])
@pytest.mark.parametrize(
    ("original_language", "imdb_info", "expected"),
    [
        # IMDb display title matches TMDB: fall back to IMDb's original title.
        ("en", {"title": "Clinic", "aka": "Clinic M.D."}, "Clinic AKA Clinic M.D. S01 1080p WEB-DL"),
        # IMDb display title differs from TMDB: it is the AKA.
        ("en", {"title": "Doctor Clinic", "aka": "Clinic M.D."}, "Clinic AKA Doctor Clinic S01 1080p WEB-DL"),
        # No distinct IMDb title at all: no AKA.
        ("en", {"title": "Clinic", "aka": "Clinic"}, "Clinic S01 1080p WEB-DL"),
        # Non-English origin keeps using only the romanized original title.
        ("ja", {"title": "Clinic", "aka": "Kurinikku"}, "Clinic AKA Kurinikku S01 1080p WEB-DL"),
    ],
)
def test_tv_aka_falls_back_to_imdb_original_title(tracker_cls, original_language, imdb_info, expected):
    tracker = tracker_cls.__name__.upper()
    meta = Meta(
        category="TV",
        title="Clinic",
        year=2004,
        season="S01",
        name="Clinic S01 1080p WEB-DL",
        original_language=original_language,
        imdb_info=imdb_info,
        language_checked=True,
        audio_languages=["English"],
    )
    adapter = tracker_cls({"DEFAULT": {"tmdb_api": "test-key"}, "TRACKERS": {tracker: {}}})
    adapter._tmdb_en_title = AsyncMock(return_value="Clinic")
    adapter._tv_title_needs_year = AsyncMock(return_value=False)

    assert asyncio.run(adapter.get_name(meta))["name"] == expected
