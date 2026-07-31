import asyncio

import httpx
import pytest

from src.torrent_clients.qbittorrent import QbittorrentClientMixin, _RetryableProxyResponseError


class FakeProxySession:
    def __init__(self, post_responses, get_responses):
        self.post_responses = iter(post_responses)
        self.get_responses = iter(get_responses)
        self.post_calls = 0
        self.get_calls = 0

    async def post(self, *_args, **_kwargs):
        self.post_calls += 1
        return next(self.post_responses)

    async def get(self, *_args, **_kwargs):
        self.get_calls += 1
        return next(self.get_responses)


@pytest.mark.asyncio
async def test_proxy_retry_retries_a_transient_http_status(monkeypatch):
    client = QbittorrentClientMixin()
    attempts = 0

    async def no_sleep(_seconds):
        return None

    async def operation():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _RetryableProxyResponseError("proxy returned HTTP 502")
        return "added"

    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    result = await client.retry_qbt_operation(
        operation,
        "Add torrent to qBittorrent via proxy",
        max_retries=1,
        retryable_errors=(TimeoutError, httpx.HTTPError, _RetryableProxyResponseError),
    )

    assert result == "added"  # noqa: S101
    assert attempts == 2  # noqa: S101


@pytest.mark.asyncio
async def test_proxy_retry_retries_httpx_connection_errors(monkeypatch):
    client = QbittorrentClientMixin()
    attempts = 0

    async def no_sleep(_seconds):
        return None

    async def operation():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("proxy unavailable")
        return "added"

    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    result = await client.retry_qbt_operation(
        operation,
        "Add torrent to qBittorrent via proxy",
        max_retries=1,
        retryable_errors=(TimeoutError, httpx.HTTPError, _RetryableProxyResponseError),
    )

    assert result == "added"  # noqa: S101
    assert attempts == 2  # noqa: S101


@pytest.mark.asyncio
async def test_proxy_retry_checks_for_existing_torrent_before_second_post(monkeypatch):
    client = QbittorrentClientMixin()
    session = FakeProxySession(
        post_responses=[httpx.Response(502)],
        get_responses=[httpx.Response(502), httpx.Response(200, json=[{"hash": "abc123"}])],
    )

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    await client._add_torrent_via_proxy(session, "https://qbit-proxy.example", "abc123", {"savepath": "/data"}, {})

    assert session.post_calls == 1  # noqa: S101
    assert session.get_calls == 2  # noqa: S101
