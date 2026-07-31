import asyncio

import httpx
import pytest

from src.torrent_clients.qbittorrent import QbittorrentClientMixin, _RetryableProxyResponseError


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
