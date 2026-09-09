from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import sqlite3

import httpx
import pytest

import src.api_key_expiry as expiry
import src.prowlarr as prowlarr
import web_ui.server as server
from src.meta import Meta
from src.trackers.UNIT3D.aither import Aither
from src.trackers.UNIT3D.lst import LST
from src.trackersetup import TrackerSetup


def response(value=None, *, status=200, payload=None):
    return httpx.Response(
        status,
        headers={"X-Api-Key-Expires-At": value} if value is not None else {},
        json=payload if payload is not None else {"data": []},
        request=httpx.Request("GET", "https://lst.gg/api/torrents/filter"),
    )


def test_dates_are_normalized_and_cache_is_specific_to_tracker_site_and_key(tmp_path):
    observed = expiry.record_api_key_expiry("LST", "secret-key", "https://lst.gg", response("2027-08-22T01:00:00+01:00"), tmp_path)
    assert observed["expires_at"] == "2027-08-22T00:00:00+00:00"
    assert expiry.get_api_key_expiry("LST", "secret-key", "https://lst.gg/", tmp_path)["expires_at"] == observed["expires_at"]
    for tracker, key, site in [("LST", "replacement", "https://lst.gg"), ("AITHER", "secret-key", "https://lst.gg"), ("LST", "secret-key", "https://another.site")]:
        assert expiry.get_api_key_expiry(tracker, key, site, tmp_path)["state"] == "unknown"
    cache = tmp_path / "data" / "api_key_expiry.sqlite3"
    assert b"secret-key" not in cache.read_bytes()
    assert "identity" not in observed


@pytest.mark.parametrize("offset,state", [(14 * 86400 + 1, "valid"), (14 * 86400, "expiring"), (1, "expiring"), (0, "expired"), (-1, "expired")])
def test_warning_boundaries(tmp_path, offset, state):
    now = datetime(2026, 9, 8, tzinfo=UTC)
    expires = (now + timedelta(seconds=offset)).isoformat()
    expiry.record_api_key_expiry("LST", "key", LST.base_url, response(expires), tmp_path)
    assert expiry.get_api_key_expiry("LST", "key", LST.base_url, tmp_path, now=now)["state"] == state


@pytest.mark.parametrize("value", ["garbage", "", "2027-01-01", "2027-01-01T00:00:00", "999999999999"])
def test_invalid_or_timezone_naive_metadata_preserves_previous_date(tmp_path, value):
    expiry.record_api_key_expiry("LST", "key", LST.base_url, response("2027-08-22T00:00:00Z"), tmp_path)
    assert expiry.record_api_key_expiry("LST", "key", LST.base_url, response(value), tmp_path, payload={}) is None
    assert expiry.get_api_key_expiry("LST", "key", LST.base_url, tmp_path)["expires_at"] == "2027-08-22T00:00:00+00:00"


def test_missing_header_is_no_expiry_only_for_confirmed_trackers(tmp_path):
    assert expiry.record_api_key_expiry("BLUTOPIA", "key", "https://blutopia.cc", response(), tmp_path, payload={}) is None
    assert expiry.record_api_key_expiry("LST", "key", LST.base_url, response(), tmp_path, payload={})["state"] == "no_expiry"
    # HTML/non-JSON and failed authentication are not evidence of no expiry.
    assert expiry.record_api_key_expiry("LST", "key", LST.base_url, response(), tmp_path) is None
    assert expiry.record_api_key_expiry("LST", "key", LST.base_url, response(status=401), tmp_path, payload={}) is None
    assert expiry.record_api_key_expiry("LST", "key", LST.base_url, response(status=403), tmp_path, payload={}) is None


def test_user_json_fallback_explicit_null_and_header_precedence(tmp_path):
    data = {"api_key": {"expires_at": "2027-08-22T00:00:00+00:00"}}
    result = expiry.record_api_key_expiry("BLUTOPIA", "key", "https://blutopia.cc", response(), tmp_path, payload=data)
    assert result["expires_at"] == data["api_key"]["expires_at"]
    result = expiry.record_api_key_expiry("BLUTOPIA", "key", "https://blutopia.cc", response(), tmp_path, payload={"api_key": {"expires_at": None}})
    assert result["state"] == "no_expiry"
    result = expiry.record_api_key_expiry("LST", "key", LST.base_url, response("2027-12-01T00:00:00Z"), tmp_path, payload=data)
    assert result["expires_at"].startswith("2027-12-01")


def test_failed_response_preserves_cache_and_cache_failure_is_advisory(tmp_path, monkeypatch):
    original = expiry.record_api_key_expiry("LST", "key", LST.base_url, response("2027-08-22T00:00:00Z"), tmp_path)
    assert expiry.record_api_key_expiry("LST", "key", LST.base_url, response(status=500), tmp_path, payload={}) is None
    assert expiry.get_api_key_expiry("LST", "key", LST.base_url, tmp_path) == original
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("unavailable")
    monkeypatch.setattr(expiry.sqlite3, "connect", fail)
    assert expiry.get_api_key_expiry("LST", "key", LST.base_url, tmp_path)["state"] == "unknown"
    assert expiry.record_api_key_expiry("LST", "key", LST.base_url, response("2027-08-22T00:00:00Z"), tmp_path)["expires_at"] == original["expires_at"]


def test_concurrent_observations_do_not_lose_other_trackers(tmp_path):
    def write(number):
        expiry.record_api_key_expiry(f"TRACKER{number}", "key", "https://tracker.test", response("2027-08-22T00:00:00Z"), tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(write, range(12)))
    for number in range(12):
        assert expiry.get_api_key_expiry(f"TRACKER{number}", "key", "https://tracker.test", tmp_path)["expires_at"]


def test_cli_warns_once_per_run_and_only_for_selected_trackers(tmp_path, monkeypatch):
    messages = []
    monkeypatch.setattr(expiry.logger, "warning", lambda message, **_kwargs: messages.append(message))
    expiry.reset_api_key_expiry_warnings()
    config = {"TRACKERS": {"LST": {"api_key": "secret-key"}, "AITHER": {"api_key": "other-key"}}}
    meta = Meta(base_dir=str(tmp_path), trackers=["LST"])
    soon = response((datetime.now(UTC) + timedelta(days=5)).isoformat())
    expiry.observe_tracker_response(config, meta, "AITHER", soon, {})
    assert not messages
    expiry.observe_tracker_response(config, meta, "LST", soon, {})
    TrackerSetup(config).trackers_enabled(meta)
    expiry.observe_tracker_response(config, meta, "LST", soon, {})
    assert len(messages) == 1
    assert "LST: API key expires" in messages[0]
    assert "secret-key" not in messages[0]
    expiry.reset_api_key_expiry_warnings()
    TrackerSetup(config).trackers_enabled(meta)
    assert len(messages) == 2


def test_cli_expired_warning_and_silent_unknown_or_no_expiry(tmp_path, monkeypatch):
    messages = []
    monkeypatch.setattr(expiry.logger, "warning", lambda message, **_kwargs: messages.append(message))
    expiry.reset_api_key_expiry_warnings()
    for state in ["unknown", "no_expiry", "valid"]:
        expiry.warn_api_key_expiry("LST", "key", LST.base_url, tmp_path, status={"state": state})
    assert not messages
    expiry.record_api_key_expiry("LST", "key", LST.base_url, response("2020-01-01T00:00:00Z"), tmp_path)
    expiry.warn_api_key_expiry("LST", "key", LST.base_url, tmp_path)
    assert "API key expired on" in messages[0]


@pytest.fixture
def web(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "STATE_DIR", tmp_path)
    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_verify_same_origin", lambda: True)
    monkeypatch.setattr(server, "_load_config_from_file", lambda _path: {"TRACKERS": {"LST": {"api_key": "saved-key"}}})
    return server.app.test_client()


@pytest.mark.parametrize("guard,code", [("_is_authenticated", 401), ("_verify_csrf_header", 403), ("_verify_same_origin", 403)])
def test_web_check_requires_session_csrf_and_same_origin(web, monkeypatch, guard, code):
    monkeypatch.setattr(server, guard, lambda: False)
    assert web.post("/api/tracker_api_key_status", json={"tracker": "LST"}).status_code == code


def fake_client(monkeypatch, result):
    requests = []
    class Client:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, url, **kwargs):
            requests.append((url, kwargs))
            return result
    monkeypatch.setattr(httpx, "Client", Client)
    return requests


def test_web_check_uses_draft_key_fixed_search_endpoint_and_does_not_save_config(web, monkeypatch, tmp_path):
    calls = fake_client(monkeypatch, response("2027-08-22T00:00:00Z"))
    result = web.post("/api/tracker_api_key_status", json={"tracker": "LST", "api_key": "draft-secret", "refresh": True, "url": "https://untrusted.test"})
    assert result.status_code == 200
    assert result.json["expiry"]["expires_at"] == "2027-08-22T00:00:00+00:00"
    assert calls == [(LST.search_url, {"headers": {"Authorization": "Bearer draft-secret", "Accept": "application/json"}, "params": {"perPage": 1}})]
    assert "draft-secret" not in result.text
    assert not (tmp_path / "data" / "config.py").exists()
    assert expiry.get_api_key_expiry("LST", "saved-key", LST.base_url, tmp_path)["state"] == "unknown"
    cached = web.post("/api/tracker_api_key_status", json={"tracker": "LST", "api_key": "draft-secret"})
    assert cached.json["expiry"] == result.json["expiry"]
    assert len(calls) == 1


@pytest.fixture(params=[None, [], {"LST": None}, {"LST": []}], ids=["null-section", "list-section", "null-tracker", "list-tracker"])
def malformed_tracker_config(request, monkeypatch):
    monkeypatch.setattr(server, "_load_config_from_file", lambda _path: {"TRACKERS": request.param})


def test_web_check_uses_draft_key_with_malformed_saved_config(web, malformed_tracker_config, monkeypatch):
    calls = fake_client(monkeypatch, response("2027-08-22T00:00:00Z"))
    result = web.post("/api/tracker_api_key_status", json={"tracker": "LST", "api_key": "draft-secret", "refresh": True})
    assert result.status_code == 200
    assert result.json["success"] is True
    assert result.json["expiry"]["expires_at"] == "2027-08-22T00:00:00+00:00"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer draft-secret"


@pytest.mark.parametrize("refresh", [False, True])
def test_web_check_without_key_handles_malformed_saved_config(web, malformed_tracker_config, monkeypatch, refresh):
    calls = fake_client(monkeypatch, response("2027-08-22T00:00:00Z"))
    result = web.post("/api/tracker_api_key_status", json={"tracker": "LST", "refresh": refresh})
    if refresh:
        assert result.status_code == 400
        assert result.json["error"] == "Enter an API key or configure a Prowlarr credential source"
    else:
        assert result.status_code == 200
        assert result.json["expiry"]["state"] == "unknown"
    assert not calls


def test_web_check_uses_saved_key_when_draft_is_omitted(web, monkeypatch):
    calls = fake_client(monkeypatch, response("2027-08-22T00:00:00Z"))
    result = web.post("/api/tracker_api_key_status", json={"tracker": "LST", "refresh": True})
    assert result.status_code == 200
    assert calls[0][1]["headers"]["Authorization"] == "Bearer saved-key"


def test_web_check_rejects_explicit_null_key_without_using_saved_key(web, monkeypatch):
    calls = fake_client(monkeypatch, response("2027-08-22T00:00:00Z"))
    result = web.post("/api/tracker_api_key_status", json={"tracker": "LST", "api_key": None, "refresh": True})
    assert result.status_code == 400
    assert result.json["error"] == "Enter a valid API key"
    assert not calls


def test_web_check_uses_prowlarr_only_for_missing_key(web, monkeypatch):
    monkeypatch.setattr(server, "_load_config_from_file", lambda _path: {"DEFAULT": {"prowlarr_url": "https://prowlarr.test", "prowlarr_api_key": "prowlarr-secret"}})
    monkeypatch.setattr(prowlarr, "fetch_prowlarr_credentials", lambda *_args: prowlarr.ProwlarrCredentialReport(credentials={"LST": prowlarr.ProwlarrCredential(api_key="remote-secret")}))
    calls = fake_client(monkeypatch, response("2027-08-22T00:00:00Z"))
    result = web.post("/api/tracker_api_key_status", json={"tracker": "LST", "api_key": "", "refresh": True})
    assert result.json["credential_source"] == "prowlarr"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer remote-secret"
    assert "remote-secret" not in result.text


@pytest.mark.parametrize("code", [401, 403, 429, 500, 302])
def test_failed_web_check_does_not_claim_expiry_or_leak_response(web, monkeypatch, code):
    fake_client(monkeypatch, response(status=code, payload={"secret": "must-not-leak"}))
    result = web.post("/api/tracker_api_key_status", json={"tracker": "LST", "refresh": True})
    assert result.status_code == 400
    assert "must-not-leak" not in result.text
    assert "expiry" not in result.json


def test_catalog_exposes_cached_metadata_without_secret(web, tmp_path):
    expiry.record_api_key_expiry("LST", "saved-key", LST.base_url, response("2027-08-22T00:00:00Z"), tmp_path)
    result = web.get("/api/trackers")
    tracker = next(item for item in result.json["trackers"] if item["name"] == "LST")
    assert tracker["api_key_expiry_supported"]
    assert tracker["api_key_expiry"]["expires_at"] == "2027-08-22T00:00:00+00:00"
    assert "saved-key" not in result.text


@pytest.mark.asyncio
async def test_unit3d_search_captures_header(tmp_path, monkeypatch):
    class Client:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, **kwargs):
            return response("2027-08-22T00:00:00Z")
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    tracker = Aither({"TRACKERS": {"AITHER": {"api_key": "key"}}})
    await tracker.search_existing(Meta(base_dir=str(tmp_path), category="TV", tmdb=123, season="S01", resolution="1080p", type="WEBDL"))
    assert expiry.get_api_key_expiry("AITHER", "key", Aither.base_url, tmp_path)["expires_at"] == "2027-08-22T00:00:00+00:00"
