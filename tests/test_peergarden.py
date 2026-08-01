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


def test_peergarden_get_imdb_non_video_category():
    tracker = PeerGarden({"DEFAULT": {}, "TRACKERS": {"PEERGARDEN": {}}})

    meta = Meta()
    meta.category = "MUSIC"
    meta.imdb_id = 1234567

    imdb_data = asyncio.run(tracker.get_imdb(meta))
    assert imdb_data == {"imdb": "0"}


def test_peergarden_get_imdb_video_category_missing():
    tracker = PeerGarden({"DEFAULT": {}, "TRACKERS": {"PEERGARDEN": {}}})

    meta = Meta()
    meta.category = "MOVIE"
    meta.imdb_id = None

    imdb_data = asyncio.run(tracker.get_imdb(meta))
    assert imdb_data == {"imdb": "0"}


def test_peergarden_get_imdb_video_category_valid():
    tracker = PeerGarden({"DEFAULT": {}, "TRACKERS": {"PEERGARDEN": {}}})

    meta = Meta()
    meta.category = "MOVIE"
    meta.imdb_id = 1234567

    imdb_data = asyncio.run(tracker.get_imdb(meta))
    assert imdb_data == {"imdb": "1234567"}


def test_peergarden_get_data_pops_prohibited_fields():
    from unittest.mock import AsyncMock, patch

    tracker = PeerGarden({"DEFAULT": {}, "TRACKERS": {"PEERGARDEN": {}}})

    mock_data = {
        "name": "Test",
        "imdb": "0",
        "free": "0",
        "featured": "0",
        "doubleup": "0",
        "sticky": "0",
        "other_field": "val",
    }

    with patch("src.trackers.UNIT3D.UNIT3D.get_data", new_callable=AsyncMock) as mock_get_data:
        mock_get_data.return_value = mock_data

        result = asyncio.run(tracker.get_data(Meta()))

        assert "free" not in result
        assert "featured" not in result
        assert "doubleup" not in result
        assert "sticky" not in result
        assert result["imdb"] == "0"
        assert result["other_field"] == "val"


def test_peergarden_get_keywords_truncated_to_255():
    tracker = PeerGarden({"DEFAULT": {}, "TRACKERS": {"PEERGARDEN": {}}})

    meta = Meta()
    meta.keywords = ["action", "b" * 240, "adventure"]

    keywords_data = asyncio.run(tracker.get_keywords(meta))
    res = keywords_data["keywords"]
    assert len(res) <= 255
    assert res == f"action, {'b' * 240}"
    assert "adventure" not in res



