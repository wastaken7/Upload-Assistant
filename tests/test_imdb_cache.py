# ruff: noqa: S101

import asyncio

from src.imdb import imdb_manager
from src.metadata_cache import cache_for, is_cache_miss


class _Response:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class _Client:
    def __init__(self, data):
        self.data = data
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, *args, **kwargs):
        self.requests.append((args, kwargs))
        return _Response(self.data)


def test_imdb_graphql_errors_are_not_negative_cached(monkeypatch, tmp_path):
    async def run():
        monkeypatch.setattr("src.imdb.httpx.AsyncClient", lambda: _Client({"errors": [{"message": "temporarily unavailable"}]}))
        config = {"DEFAULT": {"metadata_cache_dir": "cache"}}

        assert await imdb_manager.get_imdb_info_api(1, base_dir=tmp_path, config=config) == {}
        assert is_cache_miss(await cache_for(tmp_path, config).get("imdb", "title", "tt0000001|None"))

    asyncio.run(run())


def test_imdb_graphql_requests_include_imdb_referer(monkeypatch, tmp_path):
    async def run():
        client = _Client({"data": {"title": {}}})
        monkeypatch.setattr("src.imdb.httpx.AsyncClient", lambda: client)

        await imdb_manager.get_imdb_info_api(1, base_dir=tmp_path, config={"DEFAULT": {"metadata_cache_dir": "cache"}})

        assert client.requests[0][1]["headers"]["Referer"] == "https://www.imdb.com/"

    asyncio.run(run())
