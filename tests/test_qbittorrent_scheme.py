# ruff: noqa: S101

from unittest.mock import MagicMock

import pytest

from src.qbitwait import Wait
from src.torrent_clients.qbittorrent import QbittorrentClientMixin, qbittorrent_cached_clients


class _Client(QbittorrentClientMixin):
    pass


@pytest.mark.asyncio
async def test_injection_client_honors_explicit_https_scheme(monkeypatch):
    qbit = MagicMock()
    monkeypatch.setattr("src.torrent_clients.qbittorrent.qbittorrentapi.Client", qbit)
    qbittorrent_cached_clients.clear()
    client = {
        "qbit_url": "https://seedbox.example/qbittorrent",
        "qbit_port": 443,
        "qbit_user": "user",
        "qbit_pass": "pass",
    }

    await _Client().init_qbittorrent_client(client)

    assert qbit.call_args.kwargs["FORCE_SCHEME_FROM_HOST"] is True


def test_bandwidth_client_honors_explicit_https_scheme(monkeypatch):
    qbit = MagicMock()
    monkeypatch.setattr("src.qbitwait.qbittorrentapi.Client", qbit)
    config = {
        "DEFAULT": {"default_torrent_client": "qbittorrent"},
        "TORRENT_CLIENTS": {
            "qbittorrent": {
                "qbit_url": "https://seedbox.example/qbittorrent",
                "qbit_port": 443,
                "qbit_user": "user",
                "qbit_pass": "pass",
            }
        },
    }

    Wait(config)

    assert qbit.call_args.kwargs["FORCE_SCHEME_FROM_HOST"] is True
