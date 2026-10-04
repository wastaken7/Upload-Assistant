import json
import time
from types import SimpleNamespace

import limits.storage.memory as memory_storage
import pytest

import web_ui.server as server


BROWSE_ROUTES = [
    ("/api/browse_roots", {}),
    ("/api/browse", {"path": ""}),
    ("/api/browse_search", {"q": "movie"}),
]
HEADERS = {"X-CSRF-Token": "browse-limit-test", "Sec-Fetch-Site": "same-origin"}


@pytest.fixture
def browser(tmp_path, monkeypatch):
    movie = tmp_path / "Movie"
    movie.mkdir()
    (movie / "movie.mkv").touch()
    monkeypatch.setenv("UA_BROWSE_ROOTS", str(tmp_path))
    server.limiter.reset()
    client = server.app.test_client()
    with client.session_transaction() as session:
        session["enc"] = server.auth_mod.encrypt_text(
            server._derive_aes_key(),
            json.dumps({"authenticated": True, "csrf_token": HEADERS["X-CSRF-Token"]}),
        )
    yield client
    server.limiter.reset()


@pytest.fixture
def rate_limit_clock(monkeypatch):
    # Advance only the limiter's clock; leave session expiration and other
    # application clocks unchanged. No sleeps or disabled limits are needed.
    clock = [time.time()]
    monkeypatch.setattr(memory_storage, "time", SimpleNamespace(time=lambda: clock[0]))
    return clock


@pytest.mark.parametrize(("route", "query"), BROWSE_ROUTES)
def test_browsing_does_not_inherit_hourly_or_daily_quotas(browser, rate_limit_clock, route, query):
    # 250 requests within five minutes exceeds both former defaults while
    # remaining below the short-window limits, including recursive search.
    for _ in range(5):
        for _ in range(50):
            response = browser.get(route, query_string=query, headers=HEADERS)
            assert response.status_code == 200, response.get_json()
            assert response.get_json()["success"] is True
            assert response.get_json()["items"]
        rate_limit_clock[0] += 61


def test_browse_roots_are_exempt_from_request_limits(browser):
    for _ in range(650):
        response = browser.get("/api/browse_roots", headers=HEADERS)
        assert response.status_code == 200, response.get_json()


@pytest.mark.parametrize(
    ("route", "query", "allowance"),
    [("/api/browse", {"path": ""}, 600), ("/api/browse_search", {"q": "movie"}, 60)],
)
def test_browse_burst_limits_recover_after_one_minute(browser, rate_limit_clock, route, query, allowance):
    for _ in range(allowance):
        response = browser.get(route, query_string=query, headers=HEADERS)
        assert response.status_code == 200, response.get_json()
    limited = browser.get(route, query_string=query, headers=HEADERS)
    assert limited.status_code == 429
    assert limited.get_json()["success"] is False
    assert "Too many requests" in limited.get_json()["error"]

    rate_limit_clock[0] += 61
    recovered = browser.get(route, query_string=query, headers=HEADERS)
    assert recovered.status_code == 200, recovered.get_json()


@pytest.mark.parametrize(("route", "query"), BROWSE_ROUTES)
def test_browsing_still_requires_authentication(browser, route, query):
    anonymous = server.app.test_client()
    response = anonymous.get(route, query_string=query)
    assert response.status_code == 401


def test_other_routes_keep_their_default_limits(browser):
    for _ in range(50):
        assert browser.get("/api/csrf_token").status_code == 200
    assert browser.get("/api/csrf_token").status_code == 429
