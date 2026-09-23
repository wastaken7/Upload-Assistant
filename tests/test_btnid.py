import asyncio
import json

import httpx

from src.btnid import BtnIdManager
from src.get_tracker_data import TrackerDataManager
from src.meta import Meta


def test_btn_id_lookup_uses_documented_torrent_by_id(monkeypatch) -> None:
    requests: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"result": {"TorrentID": "123", "ImdbID": "456", "TvdbID": "789"}})

    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=transport, **kwargs))

    result = asyncio.run(BtnIdManager.get_btn_torrents("token", "123"))

    assert result == (456, 789)  # noqa: S101
    assert requests[0]["method"] == "getTorrentById"  # noqa: S101
    assert requests[0]["params"] == {"key": "token", "id": "123"}  # noqa: S101
    assert "jsonrpc" not in requests[0]  # noqa: S101


def test_btn_id_lookup_handles_missing_torrent(monkeypatch) -> None:
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json={"result": None}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=transport, **kwargs))

    assert asyncio.run(BtnIdManager.get_btn_torrents("token", "123")) == (0, 0)  # noqa: S101


def test_btn_metadata_lookup_accepts_configured_api_key_without_length_rule(monkeypatch, tmp_path) -> None:
    async def fake_lookup(api_key: str, torrent_id: str, _api_url: str) -> tuple[int, int]:
        assert (api_key, torrent_id) == ("token", "123")  # noqa: S101
        return 456, 789

    monkeypatch.setattr(BtnIdManager, "get_btn_torrents", fake_lookup)
    manager = TrackerDataManager({"DEFAULT": {}, "TRACKERS": {"BROADCASTHENET": {"api_key": "token"}}})
    meta = Meta(base_dir=str(tmp_path), uuid="example", tracker_ids={"BTN": "123"})

    result = asyncio.run(manager._collect_explicit_tracker_candidate("BROADCASTHENET", meta, "", "", True))

    assert result is not None  # noqa: S101
    assert result[1].imdb_id == 456 and result[1].tvdb_id == 789  # noqa: S101
