import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from src.meta import Meta
from src.trackers import retroflix as rtf_module
from src.trackers.retroflix import RetroFlix, bearer_authorization


def _config(**values: Any) -> dict[str, Any]:
    tracker: dict[str, Any] = {"api_key": "", "username": "", "password": "", "anon": False, "announce_url": "https://tracker.example/announce"}
    tracker.update(values)
    return {"DEFAULT": {}, "TRACKERS": {"RETROFLIX": tracker}}


def _meta(tmp_path: Path, **values: Any) -> Meta:
    defaults: dict[str, Any] = {
        "category": "MOVIE",
        "base_dir": str(tmp_path),
        "uuid": "release",
        "name": "Fictional Film 1985 1080p BluRay DD 2.0 x264-FAKEGRP",
        "title": "Fictional Film",
        "year": 1985,
        "imdb_id": 1234567,
    }
    defaults.update(values)
    return Meta(**defaults)


def _mock_http(monkeypatch: pytest.MonkeyPatch, handler: Any) -> list[httpx.Request]:
    requests: list[httpx.Request] = []
    real_client = httpx.AsyncClient

    def recording(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    def client(*_args: Any, **kwargs: Any) -> httpx.AsyncClient:
        return real_client(transport=httpx.MockTransport(recording), timeout=kwargs.get("timeout"))

    monkeypatch.setattr(rtf_module.httpx, "AsyncClient", client)
    return requests


@pytest.mark.parametrize(
    ("token", "expected"),
    [("abc.def", "Bearer abc.def"), ("  abc.def  ", "Bearer abc.def"), ("Bearer abc.def", "Bearer abc.def"), ("bearer abc", "bearer abc"), ("", ""), (None, "")],
)
def test_bearer_authorization(token: Any, expected: str) -> None:
    assert bearer_authorization(token) == expected


def test_search_includes_dead_torrents_and_sends_a_bearer_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    results: list[dict[str, Any]] = [{"id": 7, "name": "Fictional.Film.1985.720p.BluRay-OTHER", "size": 123, "url": "https://retroflix.club/browse/t/7/fictional"}]
    requests = _mock_http(monkeypatch, lambda _request: httpx.Response(200, json=results))

    dupes = asyncio.run(RetroFlix(_config(api_key="tok")).search_existing(_meta(tmp_path)))

    assert requests[0].url.params["includingDead"] == "included"
    assert requests[0].url.params["imdbId"] == "tt1234567"
    assert requests[0].headers["Authorization"] == "Bearer tok"
    assert dupes[0]["download"] == "https://retroflix.club/api/torrent/7/download"


def test_valid_token_does_not_log_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    requests = _mock_http(monkeypatch, lambda _request: httpx.Response(200, json={}))

    assert asyncio.run(RetroFlix(_config(api_key="tok", username="user", password="pw")).api_test(_meta(tmp_path))) is True
    assert [request.url.path for request in requests] == ["/api/test"]


def test_rejected_token_is_renewed_in_memory_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/test":
            return httpx.Response(401, json={"error": True, "message": "Unauthorized"})
        return httpx.Response(201, json={"token": "fresh"})

    requests = _mock_http(monkeypatch, handler)
    config = _config(api_key="old", username="user", password="pw")

    assert asyncio.run(RetroFlix(config).api_test(_meta(tmp_path))) is True
    assert [request.url.path for request in requests] == ["/api/test", "/api/login"]
    assert json.loads(requests[1].content) == {"username": "user", "password": "pw"}
    assert config["TRACKERS"]["RETROFLIX"]["api_key"] == "fresh"
    assert list(tmp_path.iterdir()) == []


def test_missing_token_logs_in_directly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    requests = _mock_http(monkeypatch, lambda _request: httpx.Response(201, json={"token": "fresh"}))

    assert asyncio.run(RetroFlix(_config(username="user", password="pw")).api_test(_meta(tmp_path))) is True
    assert [request.url.path for request in requests] == ["/api/login"]


@pytest.mark.parametrize("status", [400, 401, 429])
def test_failed_login_skips_the_tracker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    _mock_http(monkeypatch, lambda _request: httpx.Response(status, json={"message": "nope"}))
    config = _config(username="user", password="pw")

    assert asyncio.run(RetroFlix(config).api_test(_meta(tmp_path))) is False
    assert config["TRACKERS"]["RETROFLIX"]["api_key"] == ""


def test_no_token_and_no_credentials_sends_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    requests = _mock_http(monkeypatch, lambda _request: httpx.Response(500))

    assert asyncio.run(RetroFlix(_config()).api_test(_meta(tmp_path))) is False
    assert requests == []


def test_network_error_does_not_log_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    requests = _mock_http(monkeypatch, handler)

    assert asyncio.run(RetroFlix(_config(api_key="tok", username="user", password="pw")).api_test(_meta(tmp_path))) is False
    assert [request.url.path for request in requests] == ["/api/test"]


def test_upload_form_sends_the_description_without_screenshots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_generator(_self: Any, _meta: Meta, **kwargs: Any) -> str:
        calls.append(kwargs)
        return "[b]Notes[/b]"

    monkeypatch.setattr(rtf_module.DescriptionBuilder, "general_description_generator", fake_generator)
    meta = _meta(tmp_path)
    (tmp_path / "tmp" / "release").mkdir(parents=True)
    (tmp_path / "tmp" / "release" / "MEDIAINFO.txt").write_text("Width : 1 920 pixels", encoding="utf-8")

    data = asyncio.run(RetroFlix(_config()).get_data(meta))

    assert data["descr"] == "[b]Notes[/b]"
    assert calls[0]["screenshots"] is False
    assert data["mediaInfo"] == "Width : 1,920 pixels"


def test_preview_defers_the_description(tmp_path: Path) -> None:
    preview = asyncio.run(RetroFlix(_config()).get_payload_preview(_meta(tmp_path)))

    descr = next(field for field in preview.fields if field.key == "descr")
    assert descr.kind == "deferred"
