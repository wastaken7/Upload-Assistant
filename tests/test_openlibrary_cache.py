# ruff: noqa: S101

import asyncio

from src.metadata_cache import cache_for
from src.openlibrary import openlibrary_manager


def test_openlibrary_uses_central_cache_for_metadata_and_authors(tmp_path):
    async def run():
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
