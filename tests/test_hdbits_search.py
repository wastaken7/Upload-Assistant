# ruff: noqa: S101

import asyncio

import pytest

from src.get_tracker_data import TrackerDataManager
from src.meta import Meta
from src.trackermeta import update_metadata_from_tracker
from src.trackers.hdbits import HDBits


class _AuthErrorResponse:
    is_success = True

    @staticmethod
    def json() -> dict[str, object]:
        return {"status": 4, "message": "Missing authentication data (username)"}


class _FakeAsyncClient:
    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        pass

    @staticmethod
    async def post(*_args: object, **_kwargs: object) -> _AuthErrorResponse:
        return _AuthErrorResponse()


def test_hdbits_search_returns_six_values_for_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.trackers.hdbits.httpx.AsyncClient", lambda **_kwargs: _FakeAsyncClient())
    tracker = HDBits({"TRACKERS": {"HDBITS": {}}})

    result = asyncio.run(tracker.search_filename("Gladiator.2000.mkv", "file", Meta(category="MOVIE")))

    assert result == (None, None, None, None, None, None)


def test_hdbits_explicit_id_uses_hdb_meta_key() -> None:
    class _Tracker:
        @staticmethod
        async def get_info_from_torrent_id(torrent_id: str) -> tuple[int, None, str, None, str]:
            assert torrent_id == "12345"
            return 1602620, None, "Amour.2012.1080p.BluRay.x264", None, ""

    meta = Meta({"tracker_ids": {"HDBITS": "12345"}, "unattended": True})

    updated_meta, matched = asyncio.run(update_metadata_from_tracker("HDBITS", _Tracker(), meta, "Amour", "Amour"))

    assert matched
    assert updated_meta.imdb_id == 1602620
    assert updated_meta.get_tracker_id("HDBITS") == "12345"


def test_hdbits_use_for_search_false_skips_explicit_id(tmp_path) -> None:
    async def run() -> None:
        manager = TrackerDataManager({"TRACKERS": {"HDBITS": {"use_for_search": False}}})
        meta = Meta({"base_dir": str(tmp_path), "tracker_ids": {"HDBITS": "12345"}, "unattended": True})

        await manager.get_tracker_data(None, meta, "Amour", "Amour")

        assert meta.matched_tracker == ""

    asyncio.run(run())
