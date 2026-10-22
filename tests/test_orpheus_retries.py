"""Retries for Orpheus API requests: read-only lookups and the upload POST."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.meta import Meta
from src.music.models import MusicRelease
from src.trackers.GAZELLE.orpheus import Orpheus

Handler = Callable[[httpx.Request], httpx.Response]


def _adapter(max_retries: int = 3) -> Orpheus:
    return Orpheus({"DEFAULT": {}, "TRACKERS": {"ORPHEUS": {"api_key": "fictional-token", "max_retries": max_retries}}})


def _run(coroutine_factory: Callable[[], Any], responses: list[Callable[[httpx.Request], httpx.Response]]) -> tuple[Any, int, AsyncMock]:
    """Run the coroutine with each request answered by the next handler; return (result, requests, sleep)."""
    calls = 0
    client = httpx.AsyncClient

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return responses[min(calls, len(responses)) - 1](request)

    def create_client(**kwargs: Any) -> httpx.AsyncClient:
        return client(transport=httpx.MockTransport(handle), **kwargs)

    sleep = AsyncMock()
    with (
        patch("src.trackers.GAZELLE.orpheus.httpx.AsyncClient", new=create_client),
        patch("src.trackers.GAZELLE.orpheus.asyncio.sleep", new=sleep),
    ):
        result = asyncio.run(coroutine_factory())
    return result, calls, sleep


def _status(code: int) -> Handler:
    return lambda request: httpx.Response(code, request=request)


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"status": "success", "response": {"id": 7}}, request=request)


def _raise(error_type: type[httpx.TransportError]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error_type("fictional failure", request=request)

    return handler


@pytest.mark.parametrize("first", [_status(503), _status(502), _raise(httpx.ReadTimeout), _raise(httpx.ConnectError)])
def test_read_only_lookups_retry_transient_failures(first: Handler) -> None:
    adapter = _adapter()
    result, calls, sleep = _run(lambda: adapter._api_get(Meta(), {"action": "browse"}, 5.0, "duplicate search"), [first, _ok])

    assert result == {"id": 7}
    assert calls == 2
    sleep.assert_awaited_once()


def test_read_only_lookups_do_not_retry_client_errors() -> None:
    adapter = _adapter()
    result, calls, sleep = _run(lambda: adapter._api_get(Meta(), {"action": "browse"}, 5.0, "duplicate search"), [_status(404), _ok])

    assert result is None
    assert calls == 1
    sleep.assert_not_awaited()


def test_read_only_lookups_stop_after_max_retries() -> None:
    adapter = _adapter(max_retries=2)
    result, calls, _sleep = _run(lambda: adapter._api_get(Meta(), {"action": "browse"}, 5.0, "duplicate search"), [_status(503)])

    assert result is None
    assert calls == 2


def _upload(tmp_path: Path, adapter: Orpheus, meta: Meta) -> Callable[[], Any]:
    torrent_path = tmp_path / "[ORPHEUS].torrent"
    torrent_path.write_bytes(b"fictional torrent")
    release = MusicRelease(root=str(tmp_path))
    return lambda: adapter._post_upload(meta, {"title": "Fictional Album"}, torrent_path, release)


@pytest.mark.parametrize("first", [_raise(httpx.ConnectError), _raise(httpx.ConnectTimeout), _status(503), _status(429)])
def test_upload_retries_only_requests_orpheus_never_processed(tmp_path: Path, first: Handler) -> None:
    adapter = _adapter()
    meta = Meta(tracker_status={})
    result, calls, _sleep = _run(_upload(tmp_path, adapter, meta), [first, _ok])

    assert result == {"status": "success", "response": {"id": 7}}
    assert calls == 2


def _not_json(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text="<html>stored, but not JSON</html>", request=request)


@pytest.mark.parametrize("failure", [_raise(httpx.ReadTimeout), _status(502), _status(500), _not_json])
def test_upload_is_not_repeated_when_it_may_have_succeeded(tmp_path: Path, failure: Handler) -> None:
    adapter = _adapter()
    meta = Meta(tracker_status={})
    result, calls, sleep = _run(_upload(tmp_path, adapter, meta), [failure, _ok])

    assert result is None
    assert calls == 1
    sleep.assert_not_awaited()
    assert "check the site" in meta.tracker_status["ORPHEUS"]["status_message"]
