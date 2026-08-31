from pathlib import Path

import web_ui.server as server


def test_configured_trackers_include_defaults_and_non_default_setup() -> None:
    trackers_section = {
        "default_trackers": "AITHER",
        "AITHER": {"api_key": ""},
        "BLUTOPIA": {"api_key": "configured-key"},
        "FLOOD": {
            "api_key": "",
            "announce_url": "https://flood.st/announce/Custom_Announce_URL",
        },
    }
    example_trackers = {
        "AITHER": {"api_key": ""},
        "BLUTOPIA": {"api_key": ""},
        "FLOOD": {
            "api_key": "",
            "announce_url": "https://flood.st/announce/Custom_Announce_URL",
        },
    }
    supported_trackers = {"AITHER": object(), "BLUTOPIA": object(), "FLOOD": object()}

    configured = server._configured_tracker_names(
        trackers_section,
        example_trackers,
        ["AITHER"],
        supported_trackers,
    )

    assert configured == {"AITHER", "BLUTOPIA"}


def test_configured_trackers_include_cookie_and_legacy_btn_setup() -> None:
    supported_trackers = {
        "BROADCASTHENET": object(),
        "MAKINGOFF": object(),
        "UNSUPPORTED": object(),
    }

    configured = server._configured_tracker_names(
        {},
        {},
        [],
        supported_trackers,
        {"MAKINGOFF", "NOT_SUPPORTED"},
        {"DEFAULT": {"btn_api": "legacy-key"}},
    )

    assert configured == {"BROADCASTHENET", "MAKINGOFF"}


def test_whitespace_only_legacy_btn_key_is_not_configured() -> None:
    configured = server._configured_tracker_names(
        {},
        {},
        [],
        {"BROADCASTHENET": object()},
        user_config={"DEFAULT": {"btn_api": "  \t  "}},
    )

    assert configured == set()


def test_cookie_discovery_continues_after_one_lookup_failure(tmp_path: Path) -> None:
    valid_cookie = tmp_path / "MAKINGOFF.txt"
    valid_cookie.write_text("cookie data", encoding="utf-8")
    lookups: list[str] = []

    def find_cookie_file(_base_dir: str, tracker_name: str, _config: dict[str, object] | None) -> str:
        lookups.append(tracker_name)
        if tracker_name == "BROKEN":
            raise AttributeError("invalid cookie_file value")
        if tracker_name == "MAKINGOFF":
            return str(valid_cookie)
        return str(tmp_path / "missing.txt")

    configured = server._configured_cookie_tracker_names(
        {"BROKEN": object(), "MAKINGOFF": object(), "LATER": object()},
        {},
        tmp_path,
        find_cookie_file,
    )

    assert lookups == ["BROKEN", "MAKINGOFF", "LATER"]
    assert configured == {"MAKINGOFF"}


def test_tracker_status_http_classification_is_advisory() -> None:
    assert server._tracker_status_from_http_code(200)[0] == "available"
    assert server._tracker_status_from_http_code(403)[0] == "available"
    assert server._tracker_status_from_http_code(429)[0] == "issue"
    assert server._tracker_status_from_http_code(503)[0] == "issue"


def test_tracker_status_probe_identifies_timeouts(monkeypatch) -> None:
    class FakeTimeoutError(Exception):
        pass

    class FakeHttpx:
        TimeoutException = FakeTimeoutError

        @staticmethod
        def Client(**_kwargs):
            raise FakeTimeoutError

    monkeypatch.setattr(server, "_dynamic_import", lambda _name: FakeHttpx)

    result = server._probe_tracker_url("AITHER", "https://aither.cc")

    assert result["state"] == "unavailable"
    assert result["reason"] == "timeout"
    assert "timed out" in result["message"]


def test_tracker_status_cache_marks_expired_results_stale(monkeypatch) -> None:
    monkeypatch.setattr(server.time, "time", lambda: 2_000.0)
    with server._tracker_status_cache_lock:
        server._tracker_status_cache.clear()
        server._tracker_status_cache["AITHER"] = {
            "name": "AITHER",
            "state": "available",
            "message": "The tracker website responded.",
            "checked_at": "2026-08-31T12:00:00+00:00",
            "_checked_epoch": 2_000.0 - server._TRACKER_STATUS_CACHE_SECONDS - 1,
        }

    payload = server._tracker_status_cache_payload(["AITHER", "BLUTOPIA"])

    assert payload["AITHER"]["stale"] is True
    assert "_checked_epoch" not in payload["AITHER"]
    assert payload["BLUTOPIA"]["state"] == "not_checked"

    with server._tracker_status_cache_lock:
        server._tracker_status_cache.clear()


def test_refresh_tracker_status_rejects_unknown_tracker(monkeypatch) -> None:
    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_verify_same_origin", lambda: True)
    monkeypatch.setattr(
        server,
        "_supported_tracker_status_targets",
        lambda: {"AITHER": "https://aither.cc"},
    )

    response = server.app.test_client().post(
        "/api/tracker_status",
        json={"trackers": ["NOT-A-TRACKER"]},
    )

    assert response.status_code == 400
    assert response.get_json()["success"] is False
