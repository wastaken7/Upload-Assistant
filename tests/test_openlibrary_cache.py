# ruff: noqa: S101

import asyncio

from src.metadata_cache import cache_for
from src.openlibrary import openlibrary_manager


def _fail_if_network(*_args, **_kwargs):
    raise AssertionError("OpenLibrary cache hit attempted a network request")


class _Response:
    status_code = 200

    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class _Client:
    def __init__(self, data):
        self.data = data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, *_args, **_kwargs):
        return _Response(self.data)


def test_openlibrary_uses_central_cache_for_metadata_and_authors(tmp_path, monkeypatch):
    async def run():
        monkeypatch.setattr("src.openlibrary.httpx.AsyncClient", _fail_if_network)
        cache = cache_for(tmp_path)
        await cache.set("openlibrary", "work", "OL1W", {"title": "Cached work"})
        await cache.set("openlibrary", "isbn", "9780000000001", {"title": "Cached ISBN"})
        await cache.set("openlibrary", "author", "OL1A", {"name": "Cached author"})
        await cache.set("openlibrary", "work", "OL404W", {"not_found": True}, negative=True)

        assert await openlibrary_manager.search_by_work_id("OL1W", tmp_path) == {"title": "Cached work"}
        assert await openlibrary_manager.search_by_isbn("978-0000000001", tmp_path) == {"title": "Cached ISBN"}
        assert await openlibrary_manager.get_author_name("/authors/OL1A", None, cache) == "Cached author"
        assert await openlibrary_manager.search_by_work_id("OL404W", tmp_path) is None
        assert not (tmp_path / "tmp" / "openlibrary_cache").exists()

    asyncio.run(run())


def test_openlibrary_ignores_null_cover_ids(tmp_path, monkeypatch):
    async def run():
        monkeypatch.setattr("src.openlibrary.httpx.AsyncClient", lambda **_kwargs: _Client({"title": "No cover", "covers": [None]}))

        metadata = await openlibrary_manager.search_by_work_id("OL2W", tmp_path)

        assert metadata == {"title": "No cover", "openlibrary": "OL2W"}

    asyncio.run(run())
