import asyncio
from unittest.mock import Mock

import src.dupe_checking as dupe_checking
from src.dupe_checking import DupeChecker
from src.meta import Meta
from src.trackers.USENET.suio import Suio


def test_suio_uses_exact_match_only_duplicate_detection():
    assert Suio.exact_match_only is False  # noqa: S101


def test_tracker_config_overrides_exact_match_only(monkeypatch):
    async def non_exact_match(_candidate, _meta, **_kwargs):
        return False

    monkeypatch.setattr(DupeChecker, "is_exact_match", non_exact_match)
    candidate = {"name": "related release", "size": 1, "files": []}

    result = asyncio.run(DupeChecker({"TRACKERS": {"SUIO": {"exact_match_only": False}}}).filter_dupes([candidate], Meta(), "SUIO"))

    assert len(result) == 1  # noqa: S101
    assert result[0]["name"] == candidate["name"]  # noqa: S101


def test_suio_exact_match_ignores_size():
    meta = Meta(name="Release", filelist=["/path/Release.mkv"], source_size=100)
    candidate = {"name": "Renamed Release", "size": 200, "files": ["Release.mkv"], "file_count": 1}

    result = asyncio.run(DupeChecker({"TRACKERS": {"SUIO": {"exact_match_only": True}}}).filter_dupes([candidate], meta, "SUIO"))

    assert len(result) == 1  # noqa: S101


def test_suio_incomplete_candidate_is_not_exact_without_file_list():
    meta = Meta(name="Release", filelist=["/path/Release.mkv"], source_size=100)
    candidate = {"name": "Related Release", "size": 200, "files": [], "file_count": 1}

    result = asyncio.run(DupeChecker.is_exact_match(candidate, meta, ignore_size=True))

    assert result is False  # noqa: S101


def test_tracker_config_ignores_exact_match_only_when_tracker_does_not_support_it(monkeypatch):
    warning = Mock()
    monkeypatch.setattr(dupe_checking.logger, "warning", warning)
    candidate = {"name": "related release", "size": 1, "files": []}

    result = asyncio.run(DupeChecker({"TRACKERS": {"ASIANCINEMA": {"exact_match_only": True}}}).filter_dupes([candidate], Meta(), "ASIANCINEMA"))

    assert len(result) == 1  # noqa: S101
    warning.assert_called_once()
    assert "ignored" in warning.call_args.args[0]  # noqa: S101
