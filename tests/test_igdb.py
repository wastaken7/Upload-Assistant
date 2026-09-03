import asyncio
from typing import Any, ClassVar
from unittest.mock import AsyncMock

from src.igdb import IGDBAPI


class _Response:
    def __init__(self, data: Any, status_code: int = 200):
        self._data = data
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._data


def test_search_is_lightweight_and_selected_detail_is_rich(tmp_path, monkeypatch):
    class FakeClient:
        responses: ClassVar[list[_Response]] = [
            _Response([{"id": 1, "name": "Game", "platforms": [{"name": "PC"}]}]),
            _Response([{"id": 1, "name": "Game", "game_modes": [{"name": "Single player"}]}]),
        ]
        queries: ClassVar[list[str]] = []

        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, **kwargs):
            self.queries.append(kwargs["content"])
            return self.responses.pop(0)

    api = IGDBAPI("id", "secret", str(tmp_path))
    monkeypatch.setattr(api, "get_access_token", AsyncMock(return_value="token"))
    monkeypatch.setattr("src.igdb.httpx.AsyncClient", FakeClient)

    results = asyncio.run(api.search_game("Game"))
    detail = asyncio.run(api.fetch_game_by_id("1"))

    assert results and results[0]["name"] == "Game"  # noqa: S101
    assert detail and detail["game_modes"][0]["name"] == "Single player"  # noqa: S101
    assert "summary" not in FakeClient.queries[0]  # noqa: S101
    assert "game_modes.name" in FakeClient.queries[1]  # noqa: S101


def test_time_to_beat_is_normalized_and_cached(tmp_path, monkeypatch):
    class FakeClient:
        calls = 0

        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, **_kwargs):
            type(self).calls += 1
            return _Response([{"hastily": 3600, "normally": 7200, "completely": 0}])

    api = IGDBAPI("id", "secret", str(tmp_path))
    monkeypatch.setattr(api, "get_access_token", AsyncMock(return_value="token"))
    monkeypatch.setattr("src.igdb.httpx.AsyncClient", FakeClient)

    first = asyncio.run(api.fetch_time_to_beat(1))
    second = asyncio.run(api.fetch_time_to_beat(1))

    assert first == second == {"hastily": 3600, "normally": 7200}  # noqa: S101
    assert FakeClient.calls == 1  # noqa: S101
