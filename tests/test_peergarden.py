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


def test_peergarden_anime_tv_uses_anime_category():
    tracker = PeerGarden({"DEFAULT": {}, "TRACKERS": {"PEERGARDEN": {}}})

    meta = Meta()
    meta.category = "TV"
    meta.anime = True

    category_data = asyncio.run(tracker.get_category_id(meta))
    assert category_data == {"category_id": "11"}


def test_peergarden_anime_movie_uses_movie_category():
    tracker = PeerGarden({"DEFAULT": {}, "TRACKERS": {"PEERGARDEN": {}}})

    meta = Meta()
    meta.category = "MOVIE"
    meta.anime = True

    category_data = asyncio.run(tracker.get_category_id(meta))
    assert category_data == {"category_id": "1"}


def test_peergarden_has_exact_match_only_attr():
    tracker = PeerGarden({"DEFAULT": {}, "TRACKERS": {"PEERGARDEN": {}}})
    assert getattr(tracker, "exact_match_only", False) is True
    assert getattr(tracker, "allows_dupes", False) is True


def test_peergarden_filter_dupes_allows_different_release_group_or_encode():
    from src.dupe_checking import DupeChecker

    meta = Meta()
    meta.name = "Movie.2024.1080p.WEB-DL.GroupB"
    meta.filelist = ["/path/to/Movie.2024.1080p.WEB-DL.GroupB.mkv"]
    meta.source_size = 4200000000

    candidate = {
        "name": "Movie.2024.1080p.WEB-DL.GroupA",
        "size": 4000000000,
        "files": ["Movie.2024.1080p.WEB-DL.GroupA.mkv"],
        "file_count": 1,
        "id": 101,
    }

    dupe_checker = DupeChecker({"DEFAULT": {}})
    result = asyncio.run(dupe_checker.filter_dupes([candidate], meta, "PEERGARDEN"))

    assert result == []


def test_peergarden_filter_dupes_blocks_exact_renamed_release():
    from src.dupe_checking import DupeChecker

    meta = Meta()
    meta.name = "Awesome.Movie.2024.1080p"
    meta.filelist = ["/path/to/movie.2024.1080p.web-dl.x264-release.mkv"]
    meta.source_size = 4000000000

    candidate = {
        "name": "Renamed.Movie.Title.2024",
        "size": 4000000000,
        "files": ["movie.2024.1080p.web-dl.x264-release.mkv"],
        "file_count": 1,
        "id": 202,
    }

    dupe_checker = DupeChecker({"DEFAULT": {}})
    result = asyncio.run(dupe_checker.filter_dupes([candidate], meta, "PEERGARDEN"))

    assert len(result) == 1
    assert result[0]["id"] == 202


def test_peergarden_filter_dupes_allows_same_filename_with_different_size():
    from src.dupe_checking import DupeChecker

    meta = Meta()
    meta.name = "Awesome.Movie.2024.1080p"
    meta.filelist = ["/path/to/movie.2024.1080p.web-dl.x264-release.mkv"]
    meta.source_size = 4000000000

    candidate = {
        "name": "Renamed.Movie.Title.2024",
        "size": 4100000000,
        "files": ["movie.2024.1080p.web-dl.x264-release.mkv"],
        "file_count": 1,
        "id": 203,
    }

    dupe_checker = DupeChecker({"DEFAULT": {}})
    result = asyncio.run(dupe_checker.filter_dupes([candidate], meta, "PEERGARDEN"))

    assert result == []


def test_peergarden_filter_dupes_blocks_exact_disc_release():
    from src.dupe_checking import DupeChecker

    meta = Meta()
    meta.is_disc = "BDMV"
    meta.name = "Movie.2024.UHD.COMPLETE.BLURAY"
    meta.source_size = 45000000000

    candidate = {
        "name": "Movie.2024.UHD.COMPLETE.BLURAY",
        "size": 45000000000,
        "files": [],
        "file_count": 120,
        "id": 303,
    }

    dupe_checker = DupeChecker({"DEFAULT": {}})
    result = asyncio.run(dupe_checker.filter_dupes([candidate], meta, "PEERGARDEN"))

    assert len(result) == 1
    assert result[0]["id"] == 303


def test_peergarden_filter_dupes_blocks_exact_renamed_disc_release():
    from src.dupe_checking import DupeChecker

    meta = Meta()
    meta.is_disc = "BDMV"
    meta.name = "Movie.2024.UHD.COMPLETE.BLURAY"
    meta.source_size = 45000000000

    candidate = {
        "name": "Renamed.Movie.2024.UHD.COMPLETE.BLURAY",
        "size": 45000000000,
        "files": [],
        "file_count": 120,
        "id": 305,
    }

    dupe_checker = DupeChecker({"DEFAULT": {}})
    result = asyncio.run(dupe_checker.filter_dupes([candidate], meta, "PEERGARDEN"))

    assert len(result) == 1
    assert result[0]["id"] == 305


def test_peergarden_filter_dupes_allows_different_size_disc_release():
    from src.dupe_checking import DupeChecker

    meta = Meta()
    meta.is_disc = "BDMV"
    meta.name = "Movie.2024.UHD.COMPLETE.BLURAY"
    meta.source_size = 45000000000

    candidate = {
        "name": "Movie.2024.1080p.COMPLETE.BLURAY",
        "size": 25000000000,
        "files": [],
        "file_count": 80,
        "id": 304,
    }

    dupe_checker = DupeChecker({"DEFAULT": {}})
    result = asyncio.run(dupe_checker.filter_dupes([candidate], meta, "PEERGARDEN"))

    assert result == []
