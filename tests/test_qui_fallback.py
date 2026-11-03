# ruff: noqa: S101

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from torf import Torrent

from src.clients import Clients
from src.meta import Meta
from src.qbitwait import Wait
from src.torrent_clients.qbittorrent import QbitAccess, QbittorrentClientMixin, _RetryableProxyResponseError, has_direct_qbit_auth, qui_request

PROXY_URL = "https://qui.invalid/proxy/fictionalproxykey123"
WEBUI_CLIENT = {"qbit_url": "http://127.0.0.1", "qbit_port": "8080", "qbit_user": "user", "qbit_pass": "pass"}


class _FailingSession:
    def __init__(self):
        self.calls = 0

    async def get(self, *_args, **_kwargs):
        self.calls += 1
        raise httpx.ConnectError(f"cannot reach {PROXY_URL}/api/v2/torrents/search")

    async def post(self, *_args, **_kwargs):
        return await self.get()

    async def aclose(self):
        return None


async def _response(status_code):
    return httpx.Response(status_code)


@pytest.mark.asyncio
async def test_qui_request_only_reports_failures_from_qui():
    assert (await qui_request(_response(200))).status_code == 200
    # qBittorrent answers 404 for an unknown hash; repeating it without qui would not help.
    assert (await qui_request(_response(404))).status_code == 404
    assert await qui_request(_response(502)) == "HTTP 502"

    failure = await qui_request(_FailingSession().get())
    assert isinstance(failure, str)
    assert failure.startswith("ConnectError")
    assert "fictionalproxykey123" not in failure


@pytest.mark.parametrize(
    ("client", "expected"),
    [
        (WEBUI_CLIENT, True),
        ({"qbit_url": "http://127.0.0.1", "qbit_port": "8080", "qbit_api_key": "key"}, True),
        ({"qbit_url": "http://127.0.0.1", "qbit_port": "8080", "qbit_user": "", "qbit_pass": ""}, False),
        ({"qbit_url": "", "qbit_port": "8080", "qbit_user": "user"}, False),
        ({"qbit_url": "http://127.0.0.1", "qbit_user": "user"}, False),
    ],
)
def test_direct_auth_requires_url_port_and_credentials(client, expected):
    assert has_direct_qbit_auth(client) is expected


@pytest.mark.asyncio
async def test_search_falls_back_to_webui_credentials_and_stays_there():
    mixin = QbittorrentClientMixin()
    session = _FailingSession()
    direct = SimpleNamespace(torrents_info=lambda: ["fictional torrent"])
    access = QbitAccess(dict(WEBUI_CLIENT, qui_proxy_url=PROXY_URL), PROXY_URL, session)

    with patch.object(mixin, "init_qbittorrent_client", AsyncMock(return_value=direct)) as init_client:
        assert await mixin._fetch_torrents(access, "Fictional.Movie") == ["fictional torrent"]
        assert await mixin._fetch_torrents(access, "Fictional.Movie") == ["fictional torrent"]

    init_client.assert_awaited_once()
    assert session.calls == 1
    assert access.proxy_url == ""
    assert access.qbt_client is direct


@pytest.mark.asyncio
async def test_search_without_webui_credentials_keeps_the_qui_failure():
    mixin = QbittorrentClientMixin()
    access = QbitAccess({"qui_proxy_url": PROXY_URL}, PROXY_URL, _FailingSession())

    with patch.object(mixin, "init_qbittorrent_client", AsyncMock()) as init_client:
        assert await mixin._fetch_torrents(access, "Fictional.Movie") == []

    init_client.assert_not_awaited()
    assert access.proxy_url == PROXY_URL


@pytest.mark.asyncio
async def test_add_falls_back_to_webui_credentials_after_qui_retries(tmp_path):
    release = tmp_path / "Fictional.Movie.2025-GROUP"
    release.mkdir()
    video = release / "fictional.mkv"
    video.write_bytes(b"fictional video")
    torrent = Torrent(path=release)
    torrent.generate()
    meta = Meta({"path": str(release), "filelist": [str(video)]})
    client = Clients({"TRACKERS": {"EXAMPLE": {}}})
    session = SimpleNamespace(get=AsyncMock(), post=AsyncMock(), aclose=AsyncMock())
    direct = object()
    add_direct = AsyncMock()

    with (
        patch.object(client, "init_qbittorrent_client", AsyncMock(return_value=direct)),
        patch.object(client, "_add_torrent_via_proxy", AsyncMock(side_effect=_RetryableProxyResponseError("proxy returned HTTP 502"))),
        patch.object(client, "_add_torrent_direct", add_direct),
        patch.object(client, "retry_qbt_operation", AsyncMock(return_value=[object()])),
        patch.object(client, "create_ssl_context_for_client", return_value=None),
        patch("src.torrent_clients.qbittorrent.httpx.AsyncClient", return_value=session),
    ):
        await client.qbittorrent(
            str(release), torrent, str(tmp_path), str(tmp_path), dict(WEBUI_CLIENT, qui_proxy_url=PROXY_URL), "", meta.filelist, meta, "EXAMPLE"
        )

    add_direct.assert_awaited_once()
    assert add_direct.call_args.args[0] is direct
    # Confirming, resuming and debugging the torrent continue without qui.
    session.get.assert_not_awaited()
    session.post.assert_not_awaited()


def test_wait_falls_back_to_webui_credentials(monkeypatch):
    qbit = MagicMock()
    qbit.return_value.torrents_info.return_value = [SimpleNamespace(hash="abc123", state="stalledUP")]
    monkeypatch.setattr("src.qbitwait.qbittorrentapi.Client", qbit)
    session = _FailingSession()
    monkeypatch.setattr("src.qbitwait.httpx.AsyncClient", lambda *_args, **_kwargs: session)
    waiter = Wait({"DEFAULT": {"default_torrent_client": "qbittorrent"}, "TORRENT_CLIENTS": {"qbittorrent": dict(WEBUI_CLIENT, qui_proxy_url=PROXY_URL)}})

    asyncio.run(waiter.wait_for_completion("abc123"))

    assert session.calls == 1
    assert waiter.proxy_url is None
    qbit.return_value.torrents_info.assert_called_once_with(hashes="abc123")


@pytest.fixture
def webui_client_test(monkeypatch):
    import web_ui.server as server

    for guard in ("_is_authenticated", "_verify_csrf_header", "_verify_same_origin", "_is_ip_allowed"):
        monkeypatch.setattr(server, guard, lambda *args: True)
    qbit = MagicMock()
    qbit.return_value.app_version.return_value = "v5.1.0"
    monkeypatch.setattr("qbittorrentapi.Client", qbit)
    server.limiter.reset()

    def run(status_code):
        def fake_get(url, **_kwargs):
            return httpx.Response(status_code, text='"v5.1.0"', request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx, "get", fake_get)
        payload = {"name": "qbittorrent", "config": dict(WEBUI_CLIENT, torrent_client="qbit", qui_proxy_url=PROXY_URL)}
        with server.app.test_request_context("/api/config_test_torrent_client", method="POST", json=payload):
            result = server.config_test_torrent_client()
        response, status = result if isinstance(result, tuple) else (result, 200)
        return response.get_json(), status, qbit

    yield run
    server.limiter.reset()


def test_webui_connection_test_reports_the_webui_fallback(webui_client_test):
    data, status, qbit = webui_client_test(502)

    assert status == 200
    assert data["success"] is True
    assert "qui proxy failed (HTTP 502)" in data["message"]
    assert "fictionalproxykey123" not in data["message"]
    qbit.assert_called_once()


def test_webui_connection_test_does_not_fall_back_on_404(webui_client_test):
    # The uploader treats 404 as a qBittorrent answer, so a wrong proxy path must fail the test.
    data, status, qbit = webui_client_test(404)

    assert status == 400
    assert data["success"] is False
    assert "not found" in data["error"]
    qbit.assert_not_called()
