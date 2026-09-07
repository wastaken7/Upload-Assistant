from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

import src.prowlarr as prowlarr
import web_ui.server as server
from src.cookie_auth import CookieValidator
from src.meta import Meta


def _indexer(definition: str | None, *, api_key: str = "", cookie: str = "", enabled: bool = True, base_url: str = "https://tracker.example/") -> dict[str, Any]:
    fields: list[dict[str, Any]] = [
        {"name": "definitionFile", "value": definition},
        {"name": "baseUrl", "value": base_url},
    ]
    if api_key:
        fields.append({"name": "apikey", "value": api_key})
    if cookie:
        fields.append({"name": "cookie", "value": cookie})
    return {"enable": enabled, "fields": fields}


def test_resolve_prowlarr_credentials_maps_supported_api_keys_and_cookies() -> None:
    report = prowlarr.resolve_prowlarr_credentials(
        [
            _indexer("aither-api", api_key="aither-key"),
            _indexer("bjshare", cookie="session=abc; clearance=xyz", base_url="https://bj-share.info/"),
            _indexer("uploadcx", api_key="upload-key"),
            _indexer("xingyung", cookie="session=xyz", base_url="https://pt.xingyungept.org/"),
            _indexer("disabled-api", api_key="ignored", enabled=False),
        ],
        {"AITHER", "BJSHARE", "ULCX", "XINGYUNGEPT"},
    )

    assert report.enabled_indexers == 4
    assert report.matched_indexers == 4
    assert report.credentials["AITHER"].api_key == "aither-key"
    assert report.credentials["BJSHARE"].cookie == "session=abc; clearance=xyz"
    assert report.credentials["ULCX"].api_key == "upload-key"
    assert report.credentials["XINGYUNGEPT"].cookie == "session=xyz"


def test_resolve_rejects_masked_and_malformed_credentials() -> None:
    report = prowlarr.resolve_prowlarr_credentials(
        [
            _indexer("aither-api", api_key="********"),
            _indexer("bjshare", cookie="not-a-cookie", base_url="https://bj-share.info/"),
            _indexer(None, api_key="********"),
            {"enable": True, "fields": "invalid"},
        ],
        {"AITHER", "BJSHARE"},
    )

    assert report.credentials == {}
    assert report.masked_credentials == 2
    assert report.unsupported_indexers == 2


def test_apply_prowlarr_credentials_only_fills_missing_api_key() -> None:
    config: dict[str, Any] = {
        "TRACKERS": {
            "AITHER": {"api_key": "local-key"},
            "BJSHARE": {"announce_url": "https://announce.example/passkey"},
        }
    }
    report = prowlarr.ProwlarrCredentialReport(
        credentials={
            "AITHER": prowlarr.ProwlarrCredential(api_key="remote-key"),
            "BLUTOPIA": prowlarr.ProwlarrCredential(api_key="remote-blu"),
            "BJSHARE": prowlarr.ProwlarrCredential(cookie="session=remote", base_url="https://bj-share.info/"),
        }
    )

    applied = prowlarr.apply_prowlarr_credentials(config, report)

    assert config["TRACKERS"]["AITHER"]["api_key"] == "local-key"
    assert config["TRACKERS"]["BLUTOPIA"]["api_key"] == "remote-blu"
    assert config["TRACKERS"]["BJSHARE"]["announce_url"] == "https://announce.example/passkey"
    assert "AITHER" not in applied
    assert applied == {"BLUTOPIA", "BJSHARE"}


def test_prowlarr_cookie_jar_scopes_cookies_to_indexer_host() -> None:
    jar = prowlarr.prowlarr_cookie_jar(
        {
            "_prowlarr_cookie": {
                "header": "session=abc; clearance=xyz",
                "base_url": "https://bj-share.info/",
            }
        }
    )

    assert jar is not None
    cookies = {cookie.name: cookie for cookie in jar}
    assert {name: cookie.value for name, cookie in cookies.items()} == {"session": "abc", "clearance": "xyz"}
    assert all(cookie.domain == "bj-share.info" for cookie in cookies.values())
    assert all(cookie.secure for cookie in cookies.values())


@pytest.mark.asyncio
async def test_cookie_validator_prefers_local_file_over_prowlarr(tmp_path: Path) -> None:
    cookies_dir = tmp_path / "data" / "cookies"
    cookies_dir.mkdir(parents=True)
    (cookies_dir / "BJSHARE.txt").write_text(
        "# Netscape HTTP Cookie File\n.bj-share.info\tTRUE\t/\tTRUE\t0\tsession\tlocal\n",
        encoding="utf-8",
    )
    config = {
        "TRACKERS": {
            "BJSHARE": {
                "_prowlarr_cookie": {
                    "header": "session=remote",
                    "base_url": "https://bj-share.info/",
                }
            }
        }
    }
    meta = Meta()
    meta.base_dir = str(tmp_path)

    jar = await CookieValidator(config).load_session_cookies(meta, "BJSHARE")

    assert jar is not None
    assert {cookie.name: cookie.value for cookie in jar} == {"session": "local"}


@pytest.mark.asyncio
async def test_cookie_validator_uses_prowlarr_when_file_is_missing(tmp_path: Path) -> None:
    config = {
        "TRACKERS": {
            "BRASILTRACKER": {
                "_prowlarr_cookie": {
                    "header": "session=remote",
                    "base_url": "https://brasiltracker.org/",
                }
            }
        }
    }
    meta = Meta()
    meta.base_dir = str(tmp_path)

    jar = await CookieValidator(config).load_session_cookies(meta, "BRASILTRACKER")

    assert jar is not None
    assert {cookie.name: cookie.value for cookie in jar} == {"session": "remote"}
    assert not (tmp_path / "data" / "cookies" / "BRASILTRACKER.txt").exists()


class _FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code
        self.request = httpx.Request("GET", "http://prowlarr.test")

    def json(self) -> Any:
        return self.payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            response = httpx.Response(self.status_code, request=self.request)
            raise httpx.HTTPStatusError("failure", request=self.request, response=response)


class _FakeClient:
    def __init__(self, responses: list[_FakeResponse]):
        self.responses = responses
        self.urls: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def get(self, url: str) -> _FakeResponse:
        self.urls.append(url)
        return self.responses.pop(0)


def test_fetch_uses_indexer_and_status_endpoints(monkeypatch) -> None:
    client = _FakeClient([_FakeResponse([_indexer("aither-api", api_key="key")]), _FakeResponse({"version": "2.5.2"})])
    monkeypatch.setattr(prowlarr.httpx, "Client", lambda **_kwargs: client)

    report = prowlarr.fetch_prowlarr_credentials("http://prowlarr.test/", "secret", {"AITHER"}, include_status=True)

    assert client.urls == ["http://prowlarr.test/api/v1/indexer", "http://prowlarr.test/api/v1/system/status"]
    assert report.version == "2.5.2"


def test_fetch_reports_authentication_failure_without_response_body(monkeypatch) -> None:
    client = _FakeClient([_FakeResponse({"secret": "must-not-leak"}, status_code=401)])
    monkeypatch.setattr(prowlarr.httpx, "Client", lambda **_kwargs: client)

    with pytest.raises(prowlarr.ProwlarrError, match="rejected the API key") as error:
        prowlarr.fetch_prowlarr_credentials("http://prowlarr.test", "secret", {"AITHER"})

    assert "must-not-leak" not in str(error.value)


def test_fetch_reports_timeout(monkeypatch) -> None:
    class TimeoutClient(_FakeClient):
        def get(self, url: str) -> _FakeResponse:
            raise httpx.ReadTimeout("slow", request=httpx.Request("GET", url))

    monkeypatch.setattr(prowlarr.httpx, "Client", lambda **_kwargs: TimeoutClient([]))

    with pytest.raises(prowlarr.ProwlarrError, match="timed out"):
        prowlarr.fetch_prowlarr_credentials("http://prowlarr.test", "secret", {"AITHER"})


def test_tracker_catalog_marks_prowlarr_cookie_source(monkeypatch, tmp_path: Path) -> None:
    user_config = {
        "DEFAULT": {"prowlarr_url": "http://prowlarr.test", "prowlarr_api_key": "secret"},
        "TRACKERS": {"BJSHARE": {"announce_url": "https://tracker.example/passkey/announce"}},
    }
    example_config = {"TRACKERS": {"BJSHARE": {"announce_url": ""}}}

    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_verify_same_origin", lambda: True)
    monkeypatch.setattr(server, "STATE_DIR", tmp_path)
    monkeypatch.setattr(
        server,
        "_load_config_from_file",
        lambda path: example_config if path.name == "example_config.py" else user_config,
    )
    monkeypatch.setattr(
        prowlarr,
        "fetch_prowlarr_credentials",
        lambda *_args, **_kwargs: prowlarr.ProwlarrCredentialReport(
            credentials={"BJSHARE": prowlarr.ProwlarrCredential(cookie="session=remote", base_url="https://bj-share.info/")}
        ),
    )

    response = server.app.test_client().get("/api/trackers")

    tracker = next(item for item in response.get_json()["trackers"] if item["name"] == "BJSHARE")
    assert tracker["configured"] is True
    assert tracker["cookie_configured"] is True
    assert tracker["credential_source"] == "prowlarr"

    user_config["TRACKERS"]["BJSHARE"]["announce_url"] = ""
    response = server.app.test_client().get("/api/trackers")
    tracker = next(item for item in response.get_json()["trackers"] if item["name"] == "BJSHARE")
    assert tracker["configured"] is False
    assert tracker["cookie_configured"] is True


def test_config_test_prowlarr_requires_session_and_csrf(monkeypatch) -> None:
    monkeypatch.setattr(server, "_is_authenticated", lambda: False)
    response = server.app.test_client().post("/api/config_test_prowlarr", json={})
    assert response.status_code == 401

    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: False)
    response = server.app.test_client().post("/api/config_test_prowlarr", json={})
    assert response.status_code == 403


def test_config_test_prowlarr_returns_no_secrets(monkeypatch) -> None:
    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_verify_same_origin", lambda: True)
    monkeypatch.setattr(
        prowlarr,
        "fetch_prowlarr_credentials",
        lambda *_args, **_kwargs: prowlarr.ProwlarrCredentialReport(
            credentials={"BJSHARE": prowlarr.ProwlarrCredential(cookie="session=secret", base_url="https://bj-share.info/")},
            enabled_indexers=2,
            matched_indexers=1,
            masked_credentials=1,
            unsupported_indexers=1,
            version="2.5.2",
        ),
    )

    response = server.app.test_client().post(
        "/api/config_test_prowlarr",
        json={"url": "http://prowlarr.test", "api_key": "top-secret"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["credential_trackers"] == ["BJSHARE"]
    assert payload["cookie_trackers"] == ["BJSHARE"]
    assert "top-secret" not in response.text
    assert "session=secret" not in response.text
