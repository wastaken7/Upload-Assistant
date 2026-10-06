"""Exercise browsing quotas without sharing authentication state with other tests."""

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
    """Provide an authenticated browser with isolated media and IP-control files."""
    auth_root = tmp_path / "auth"
    auth_root.mkdir()
    monkeypatch.setattr(server, "cfg_dir", auth_root)
    monkeypatch.setattr(server.auth_mod, "get_config_dir", lambda: auth_root)
    media_root = tmp_path / "media"
    movie = media_root / "Movie"
    movie.mkdir(parents=True)
    (movie / "movie.mkv").touch()
    monkeypatch.setenv("UA_BROWSE_ROOTS", str(media_root))
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
    """Advance rate-limit windows without affecting authentication or session clocks."""
    # Advance only the limiter's clock; leave session expiration and other
    # application clocks unchanged. No sleeps or disabled limits are needed.
    clock = [time.time()]
    monkeypatch.setattr(memory_storage, "time", SimpleNamespace(time=lambda: clock[0]))
    return clock


@pytest.mark.parametrize(("route", "query"), BROWSE_ROUTES)
def test_browsing_does_not_inherit_hourly_or_daily_quotas(browser, rate_limit_clock, route, query):
    """Allow sustained browsing beyond both former long-window allowances."""
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
    """Allow repeated root restoration without exhausting a request allowance."""
    for _ in range(650):
        response = browser.get("/api/browse_roots", headers=HEADERS)
        assert response.status_code == 200, response.get_json()


@pytest.mark.parametrize(
    ("route", "query", "allowance"),
    [("/api/browse", {"path": ""}, 600), ("/api/browse_search", {"q": "movie"}, 60)],
)
def test_browse_burst_limits_recover_after_one_minute(browser, rate_limit_clock, route, query, allowance):
    """Reject a burst above its endpoint limit and admit requests after recovery."""
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
    """Keep every browsing endpoint protected despite relaxed request quotas."""
    anonymous = server.app.test_client()
    response = anonymous.get(route, query_string=query)
    assert response.status_code == 401


def test_other_routes_keep_their_default_limits(browser):
    """Preserve the hourly default on endpoints without browsing overrides."""
    for _ in range(50):
        assert browser.get("/api/csrf_token").status_code == 200
    assert browser.get("/api/csrf_token").status_code == 429


def test_invalid_basic_credentials_are_counted_before_html_redirect(browser, monkeypatch):
    """Block repeated password guesses on exempt root listing before verification."""
    record = {"username": "browse-user", "password_hash": "test-only-hash"}
    monkeypatch.setattr(server.auth_mod, "load_user", lambda: record)
    verified_passwords = []

    def reject_password(password_hash, password):
        """Record password verification while avoiding an expensive real hash."""
        verified_passwords.append((password_hash, password))
        return False

    monkeypatch.setattr(server.auth_mod, "verify_password", reject_password)
    anonymous = server.app.test_client()
    for _ in range(5):
        response = anonymous.get(
            "/api/browse_roots", auth=("browse-user", "incorrect"), headers={"Accept": "text/html"}
        )
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")
    blocked = anonymous.get(
        "/api/browse_roots", auth=("browse-user", "incorrect"), headers={"Accept": "text/html"}
    )
    assert blocked.status_code == 403
    assert verified_passwords == [("test-only-hash", "incorrect")] * 5


def test_anonymous_html_redirects_do_not_count_as_password_guesses(browser):
    """Keep ordinary browser visits from blacklisting users before they log in."""
    anonymous = server.app.test_client()
    for _ in range(10):
        response = anonymous.get("/api/browse_roots", headers={"Accept": "text/html"})
        assert response.status_code == 302
    assert server._get_ip_failures() == {}
    assert server._get_ip_blacklist() == []
