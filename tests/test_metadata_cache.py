# ruff: noqa: S101

import asyncio
from pathlib import Path

import data.config as config_module
from src.metadata_cache import cache_for, is_cache_miss, set_run_disabled


def test_default_cache_root_is_the_configured_checkout():
    assert cache_for("").root == Path(config_module.__file__).resolve().parent.parent / "data" / "cache" / "metadata"


def test_metadata_cache_uses_provider_subdirectories_and_ttl(tmp_path):
    async def run():
        cache = cache_for(tmp_path, {"DEFAULT": {"metadata_cache_dir": "cache", "metadata_cache_default_ttl_hours": 1}})
        await cache.set("TMDB", "localized", "movie:1:pt-BR", {"title": "Teste"})
        assert await cache.get("tmdb", "localized", "movie:1:pt-BR") == {"title": "Teste"}
        assert len(list((tmp_path / "cache" / "tmdb" / "localized").glob("*.json"))) == 1

    asyncio.run(run())


def test_metadata_cache_can_be_disabled_for_one_run(tmp_path):
    async def run():
        cache = cache_for(tmp_path, {"DEFAULT": {"metadata_cache_dir": "cache"}})
        set_run_disabled(True)
        try:
            await cache.set("imdb", "title", "tt1", {"title": "Ignored"})
            assert is_cache_miss(await cache.get("imdb", "title", "tt1"))
        finally:
            set_run_disabled(False)

    asyncio.run(run())
