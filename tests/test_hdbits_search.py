import asyncio

import pytest

from src.meta import Meta
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

    assert result == (None, None, None, None, None, None)  # noqa: S101
