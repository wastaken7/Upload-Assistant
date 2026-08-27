# ruff: noqa: S101

import asyncio

import pytest

import src.tvdb as tvdb_module
from src.tvdb import TVDB, TvdbData


class _RecordingCache:
    def __init__(self):
        self.writes = []

    async def get(self, *_args):
        return object()

    async def set(self, *args, **kwargs):
        self.writes.append((args, kwargs))


class _FailingClient:
    async def search(self, *_args, **_kwargs):
        raise RuntimeError("TVDB unavailable")

    async def search_by_remote_id(self, _remote_id):
        return [{"series": {"id": 123, "name": "Fallback"}}]

    async def get_series_extended(self, _series_id, **_kwargs):
        raise RuntimeError("TVDB unavailable")

    async def get_episode_extended(self, _episode_id, **_kwargs):
        raise RuntimeError("TVDB unavailable")


class _ErrorResponse:
    status_code = 503

    def raise_for_status(self):
        raise RuntimeError("TVDB unavailable")


class _RequestClient:
    async def request(self, *_args, **_kwargs):
        return _ErrorResponse()


class _ClosableClient:
    def __init__(self):
        self.closed = False

    async def aclose(self):
        self.closed = True


def _install_failing_tvdb(monkeypatch):
    cache = _RecordingCache()
    monkeypatch.setattr(tvdb_module, "_get_tvdb_or_warn", lambda _config: _FailingClient())
    monkeypatch.setattr(tvdb_module, "cache_for", lambda **_kwargs: cache)
    monkeypatch.setattr(tvdb_module, "is_cache_miss", lambda _value: True)
    return cache


def test_tvdb_request_preserves_http_failures():
    async def run():
        client = TVDB.__new__(TVDB)
        client.token = object()
        client._client = _RequestClient()

        with pytest.raises(RuntimeError, match="TVDB unavailable"):
            await client._request("GET", "/search")

    asyncio.run(run())


def test_close_tvdb_closes_and_resets_shared_client(monkeypatch):
    async def run():
        client = _ClosableClient()
        monkeypatch.setattr(tvdb_module, "tvdb", client)

        await tvdb_module.close_tvdb()

        assert client.closed is True
        assert tvdb_module.tvdb is None

    asyncio.run(run())


def test_upload_main_closes_tvdb_after_failure(monkeypatch):
    async def run():
        import upload

        closed = False

        async def fail_upload(_base_dir):
            raise RuntimeError("upload failed")

        async def record_close():
            nonlocal closed
            closed = True

        monkeypatch.setattr(upload, "do_the_thing", fail_upload)
        monkeypatch.setattr(upload, "close_tvdb", record_close)

        await upload.main()

        assert closed is True

    asyncio.run(run())


def test_failed_series_search_is_not_negative_cached(monkeypatch):
    async def run():
        cache = _install_failing_tvdb(monkeypatch)

        with pytest.raises(RuntimeError, match="TVDB unavailable"):
            await TvdbData({}).search_tvdb_series("Example", "2020")

        assert cache.writes == []

    asyncio.run(run())


def test_failed_series_metadata_is_not_cached(monkeypatch):
    async def run():
        cache = _install_failing_tvdb(monkeypatch)

        assert await TvdbData({}).get_tvdb_by_external_id(1, None) == (123, "Fallback")
        assert cache.writes == []

    asyncio.run(run())


def test_failed_episode_lookup_is_not_negative_cached(monkeypatch):
    async def run():
        cache = _install_failing_tvdb(monkeypatch)

        assert await TvdbData({}).get_imdb_id_from_tvdb_episode_id(123) is None
        assert cache.writes == []

    asyncio.run(run())
