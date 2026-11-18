# ruff: noqa: S101

import json
from unittest.mock import MagicMock

import pytest

import web_ui.context as webui_context
import web_ui.extensions as webui_extensions
import web_ui.routes.config as config_routes
import web_ui.security as webui_security
import web_ui.server as server
from web_ui.config_store import REDACTED_PLACEHOLDER, _is_sensitive_config_path

EXAMPLE = {
    "DEFAULT": {
        "tmdb_api": "",
        "twitch_client_id": "",
        "twitch_client_secret": "",
        "tvdb_token": "",
        "prowlarr_url": "",
        "prowlarr_api_key": "",
        "screens": 4,
    },
    "TRACKERS": {
        "FICT": {
            "api_key": "",
            "announce_url": "https://fict.invalid/announce/customannounceurl",
            "login_answer": "",
            "api_upload": True,
        },
    },
    "TORRENT_CLIENTS": {
        "qbittorrent": {
            "torrent_client": "qbit",
            "qbit_url": "http://127.0.0.1",
            "qbit_port": "8080",
            "qbit_user": "",
            "qbit_pass": "",
        },
    },
}

SECRETS = {
    "tmdb_api": "fictional-tmdb-key",
    "twitch_client_id": "fictional-twitch-id",
    "twitch_client_secret": "fictional-twitch-secret",
    "tvdb_token": "fictional-tvdb-token",
    "prowlarr_api_key": "fictional-prowlarr-key",
    "api_key": "fictional-tracker-key",
    "login_answer": "fictional-answer",
    "qbit_user": "fictional-user",
    "qbit_pass": "fictional-pass",
}


@pytest.fixture
def redaction_config(tmp_path, monkeypatch):
    user = json.loads(json.dumps(EXAMPLE))
    user["DEFAULT"].update({key: SECRETS[key] for key in ("tmdb_api", "twitch_client_id", "twitch_client_secret", "tvdb_token", "prowlarr_api_key")})
    user["DEFAULT"]["prowlarr_url"] = "http://prowlarr.invalid"
    user["TRACKERS"]["FICT"].update(api_key=SECRETS["api_key"], login_answer=SECRETS["login_answer"])
    user["TORRENT_CLIENTS"]["qbittorrent"].update(qbit_user=SECRETS["qbit_user"], qbit_pass=SECRETS["qbit_pass"])
    example_path = tmp_path / "code/data/example_config.py"
    config_path = tmp_path / "state/data/config.py"
    for path, config in ((example_path, EXAMPLE), (config_path, user)):
        path.parent.mkdir(parents=True)
        path.write_text(f"config = {config!r}\n", encoding="utf-8")
    monkeypatch.setattr(webui_context, "CODE_DIR", example_path.parent.parent)
    monkeypatch.setattr(webui_context, "STATE_DIR", config_path.parent.parent)
    for guard in ("_is_authenticated", "_verify_csrf_header", "_verify_same_origin", "_is_ip_allowed"):
        monkeypatch.setattr(webui_security, guard, lambda *args: True)
    monkeypatch.setattr(webui_security, "_write_audit_log", lambda *args: None)
    webui_extensions.limiter.reset()
    yield config_path
    webui_extensions.limiter.reset()


def _call(path, view, payload=None):
    method = "POST" if payload is not None else "GET"
    with server.app.test_request_context(path, method=method, json=payload):
        response = server.app.make_response(view())
    return response.get_json(), response.status_code


def _flatten(items, prefix=()):
    for item in items:
        path = (*prefix, item["key"])
        if item.get("children") is not None and "value" not in item:
            yield from _flatten(item["children"], path)
        else:
            yield path, item


def test_config_options_never_sends_saved_credentials(redaction_config):
    data, status = _call("/api/config_options", config_routes.config_options)

    assert status == 200
    body = json.dumps(data)
    for secret in SECRETS.values():
        assert secret not in body
    values = {path: item.get("value") for section in data["sections"] for path, item in _flatten(section["items"], (section["section"],))}
    assert values[("DEFAULT", "twitch_client_secret")] == REDACTED_PLACEHOLDER
    assert values[("TORRENT_CLIENTS", "qbittorrent", "qbit_pass")] == REDACTED_PLACEHOLDER
    # Non-credentials, non-strings and public example placeholders stay readable.
    assert values[("DEFAULT", "prowlarr_url")] == "http://prowlarr.invalid"
    assert values[("DEFAULT", "screens")] == 4
    assert values[("TRACKERS", "FICT", "api_upload")] is True
    assert values[("TRACKERS", "FICT", "announce_url")] == EXAMPLE["TRACKERS"]["FICT"]["announce_url"]
    assert values[("TORRENT_CLIENTS", "qbittorrent", "qbit_url")] == "http://127.0.0.1"


def test_config_update_refuses_to_save_the_placeholder(redaction_config):
    before = redaction_config.read_bytes()

    data, status = _call(
        "/api/config_update",
        config_routes.config_update,
        {"updates": [{"path": ["DEFAULT", "twitch_client_secret"], "value": REDACTED_PLACEHOLDER}]},
    )

    assert status == 400
    assert data["success"] is False
    assert redaction_config.read_bytes() == before


def test_config_update_does_not_echo_new_credentials(redaction_config):
    data, status = _call(
        "/api/config_update",
        config_routes.config_update,
        {"updates": [{"path": ["DEFAULT", "twitch_client_secret"], "value": "fictional-new-secret"}]},
    )

    assert status == 200
    assert data["values"] == [REDACTED_PLACEHOLDER]
    assert "fictional-new-secret" in redaction_config.read_text(encoding="utf-8")


def test_torrent_client_test_uses_saved_credentials_for_placeholders(redaction_config, monkeypatch):
    qbit = MagicMock()
    qbit.return_value.app_version.return_value = "v5.1.0"
    monkeypatch.setattr("qbittorrentapi.Client", qbit)
    draft = dict(EXAMPLE["TORRENT_CLIENTS"]["qbittorrent"], qbit_user=REDACTED_PLACEHOLDER, qbit_pass=REDACTED_PLACEHOLDER)

    data, status = _call(
        "/api/config_test_torrent_client",
        config_routes.config_test_torrent_client,
        {"name": "renamed-client", "saved_name": "qbittorrent", "config": draft},
    )

    assert status == 200, data
    kwargs = qbit.call_args.kwargs
    assert kwargs["username"] == SECRETS["qbit_user"]
    assert kwargs["password"] == SECRETS["qbit_pass"]


def test_prowlarr_test_uses_saved_key_for_placeholder(redaction_config, monkeypatch):
    import src.prowlarr as prowlarr

    seen = {}

    def fake_fetch(base_url, api_key, *_args, **_kwargs):
        seen["api_key"] = api_key
        raise prowlarr.ProwlarrError("stop")

    monkeypatch.setattr(prowlarr, "fetch_prowlarr_credentials", fake_fetch)

    _call(
        "/api/config_test_prowlarr",
        config_routes.config_test_prowlarr,
        {"url": "http://prowlarr.invalid", "api_key": REDACTED_PLACEHOLDER},
    )

    assert seen["api_key"] == SECRETS["prowlarr_api_key"]


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (["DEFAULT", "twitch_client_id"], True),
        (["DEFAULT", "twitch_client_secret"], True),
        (["DEFAULT", "music_discogs_token"], True),
        (["TRACKERS", "FICT", "login_answer"], True),
        (["TRACKERS", "FICT", "cookies"], True),
        (["TORRENT_CLIENTS", "rtorrent", "rtorrent_url"], True),
        (["TORRENT_CLIENTS", "deluge", "deluge_pass"], True),
        (["TRACKERS", "FICT", "cookie_file"], False),
        (["TRACKERS", "FICT", "login_question"], False),
        (["DEFAULT", "screens"], False),
    ],
)
def test_sensitive_config_paths(path, expected):
    assert _is_sensitive_config_path(path) is expected


def test_torrent_client_test_refuses_saved_credentials_for_a_new_address(redaction_config, monkeypatch):
    qbit = MagicMock()
    monkeypatch.setattr("qbittorrentapi.Client", qbit)
    draft = dict(EXAMPLE["TORRENT_CLIENTS"]["qbittorrent"], qbit_url="http://collector.invalid", qbit_user=REDACTED_PLACEHOLDER, qbit_pass=REDACTED_PLACEHOLDER)

    data, status = _call(
        "/api/config_test_torrent_client",
        config_routes.config_test_torrent_client,
        {"name": "qbittorrent", "config": draft},
    )

    assert status == 400
    assert "Re-enter" in data["error"]
    qbit.assert_not_called()


def test_torrent_client_test_accepts_new_address_with_typed_credentials(redaction_config, monkeypatch):
    qbit = MagicMock()
    qbit.return_value.app_version.return_value = "v5.1.0"
    monkeypatch.setattr("qbittorrentapi.Client", qbit)
    draft = dict(EXAMPLE["TORRENT_CLIENTS"]["qbittorrent"], qbit_url="http://other.invalid", qbit_user="typed-user", qbit_pass="typed-pass")

    _data, status = _call(
        "/api/config_test_torrent_client",
        config_routes.config_test_torrent_client,
        {"name": "qbittorrent", "config": draft},
    )

    assert status == 200
    assert qbit.call_args.kwargs["password"] == "typed-pass"


def test_prowlarr_test_refuses_saved_key_for_a_new_url(redaction_config, monkeypatch):
    import src.prowlarr as prowlarr

    fetch = MagicMock()
    monkeypatch.setattr(prowlarr, "fetch_prowlarr_credentials", fetch)

    data, status = _call(
        "/api/config_test_prowlarr",
        config_routes.config_test_prowlarr,
        {"url": "http://collector.invalid", "api_key": REDACTED_PLACEHOLDER},
    )

    assert status == 400
    assert "Re-enter" in data["error"]
    fetch.assert_not_called()


@pytest.fixture
def reauth_account(monkeypatch):
    import web_ui.auth as auth_mod
    import web_ui.routes.account as account_routes

    for module in (webui_security, account_routes):
        monkeypatch.setattr(module, "_load_user_record", lambda: {"username": "tester", "password_hash": "hash"})
    monkeypatch.setattr(webui_security, "_account_fingerprint", lambda: "fingerprint")
    monkeypatch.setattr(auth_mod, "verify_user", lambda username, password: username == "tester" and password == "right-password")
    failures = []
    monkeypatch.setattr(webui_security, "_handle_failed_auth", failures.append)
    return failures


@pytest.mark.real_settings_reauth
@pytest.mark.parametrize(
    ("path", "view", "payload"),
    [
        ("/api/config_update", config_routes.config_update, {"updates": [{"path": ["DEFAULT", "screens"], "value": 6}]}),
        ("/api/config_test_prowlarr", config_routes.config_test_prowlarr, {"url": "http://prowlarr.invalid", "api_key": "typed"}),
        ("/api/config_test_torrent_client", config_routes.config_test_torrent_client, {"name": "qbittorrent", "config": {"torrent_client": "watch"}}),
    ],
)
def test_settings_changes_require_a_recent_password_confirmation(redaction_config, reauth_account, path, view, payload):
    before = redaction_config.read_bytes()

    with server.app.test_request_context(path, method="POST", json=payload):
        response = view()

    assert response.status_code == 403
    assert response.headers[webui_security.SETTINGS_REAUTH_HEADER] == "1"
    assert response.get_json()["reauth_required"] is True
    assert redaction_config.read_bytes() == before


@pytest.mark.real_settings_reauth
def test_settings_reauth_unlocks_changes_for_the_session(redaction_config, reauth_account, monkeypatch):
    import web_ui.routes.account as account_routes

    monkeypatch.setattr(webui_security, "_totp_enabled", lambda: False)
    with server.app.test_request_context("/api/settings_reauth", method="POST", json={"password": "wrong"}):
        result = account_routes.settings_reauth()
        assert result[1] == 400
        assert not webui_security._settings_reauth_valid()
    assert reauth_account == []

    with server.app.test_request_context("/api/settings_reauth", method="POST", json={"password": "right-password"}):
        response = account_routes.settings_reauth()
        assert response.get_json()["success"] is True
        assert webui_security._settings_reauth_valid()
        # Confirmation is tied to the account; a password change voids it.
        monkeypatch.setattr(webui_security, "_account_fingerprint", lambda: "new-fingerprint")
        assert not webui_security._settings_reauth_valid()


@pytest.mark.real_settings_reauth
def test_settings_reauth_requires_the_2fa_code_when_enabled(redaction_config, reauth_account, monkeypatch):
    import web_ui.routes.account as account_routes

    monkeypatch.setattr(webui_security, "_totp_enabled", lambda: True)
    monkeypatch.setattr(webui_security, "_verify_totp_code", lambda code: code == "123456")

    with server.app.test_request_context("/api/settings_reauth", method="POST", json={"password": "right-password"}):
        assert account_routes.settings_reauth()[1] == 400
        assert not webui_security._settings_reauth_valid()
    with server.app.test_request_context("/api/settings_reauth", method="POST", json={"password": "right-password", "totp_code": "123456"}):
        assert account_routes.settings_reauth().get_json()["success"] is True
        assert webui_security._settings_reauth_valid()


@pytest.mark.real_settings_reauth
def test_password_sign_in_counts_as_a_settings_confirmation(redaction_config, reauth_account):
    with server.app.test_request_context("/login", method="POST"):
        assert not webui_security._settings_reauth_valid()
        webui_security._mark_session_authenticated("tester")
        assert webui_security._settings_reauth_valid()


TRANSMISSION_SAVED = {
    "torrent_client": "transmission",
    "transmission_protocol": "https",
    "transmission_host": "seedbox.invalid",
    "transmission_port": 443,
    "transmission_path": "/Private/RPC",
    "transmission_username": "fictional-user",
    "transmission_password": "fictional-pass",
}


@pytest.mark.parametrize(
    ("draft_changes", "expected"),
    [
        ({}, True),
        ({"transmission_path": "/private/rpc"}, False),  # paths are case-sensitive
        ({"transmission_path": None, "transmission_protocol": None}, False),  # omitted fields fall back to http + default path
        ({"transmission_host": "SEEDBOX.invalid"}, False),
        ({"transmission_path": "/Private/RPC/"}, False),  # trailing slashes are significant
        ({"transmission_port": True}, False),  # a JSON true is not port 443
        ({"VERIFY_WEBUI_CERTIFICATE": REDACTED_PLACEHOLDER}, False),  # a placeholder cannot skip the check
        ({"VERIFY_WEBUI_CERTIFICATE": False}, False),
        ({"VERIFY_WEBUI_CERTIFICATE": True}, True),
    ],
)
def test_transmission_destination_check(draft_changes, expected):
    from web_ui.config_store import TORRENT_CLIENT_DESTINATION_KEYS, _destination_matches

    draft = dict(TRANSMISSION_SAVED, transmission_password=REDACTED_PLACEHOLDER)
    for key, value in draft_changes.items():
        if value is None:
            draft.pop(key)
        else:
            draft[key] = value

    assert _destination_matches(draft, TRANSMISSION_SAVED, TORRENT_CLIENT_DESTINATION_KEYS) is expected


def test_destination_check_uses_defaults_for_fields_missing_from_saved_config():
    from web_ui.config_store import TORRENT_CLIENT_DESTINATION_KEYS, _destination_matches

    saved = {"torrent_client": "transmission", "transmission_host": "seedbox.invalid", "transmission_port": 9091}
    draft = dict(saved, transmission_protocol="http", transmission_path="/transmission/rpc", VERIFY_WEBUI_CERTIFICATE=True)

    assert _destination_matches(draft, saved, TORRENT_CLIENT_DESTINATION_KEYS) is True


def test_config_update_refuses_placeholder_inside_a_section_update(redaction_config):
    before = redaction_config.read_bytes()
    section = dict(EXAMPLE["TORRENT_CLIENTS"]["qbittorrent"], qbit_user="typed-user", qbit_pass=REDACTED_PLACEHOLDER)

    data, status = _call(
        "/api/config_update",
        config_routes.config_update,
        {"updates": [{"path": ["TORRENT_CLIENTS", "qbittorrent"], "value": section}]},
    )

    assert status == 400
    assert "qbittorrent/qbit_pass" in data["error"]
    assert redaction_config.read_bytes() == before


@pytest.mark.real_settings_reauth
def test_enabling_2fa_voids_a_password_only_confirmation(redaction_config, reauth_account, monkeypatch):
    totp = {"enabled": False}
    monkeypatch.setattr(webui_security, "_totp_enabled", lambda: totp["enabled"])

    with server.app.test_request_context("/api/settings_reauth", method="POST"):
        webui_security._mark_settings_reauthenticated(totp_verified=False)
        assert webui_security._settings_reauth_valid()
        totp["enabled"] = True
        assert not webui_security._settings_reauth_valid()


@pytest.mark.real_settings_reauth
def test_failed_confirmations_do_not_blacklist_the_address(redaction_config, reauth_account, monkeypatch):
    import web_ui.routes.account as account_routes

    monkeypatch.setattr(webui_security, "_totp_enabled", lambda: False)
    for _ in range(5):
        with server.app.test_request_context("/api/settings_reauth", method="POST", json={"password": "wrong"}):
            assert account_routes.settings_reauth()[1] == 400

    assert reauth_account == []


def test_audit_log_redacts_torrent_client_usernames():
    assert webui_security._is_sensitive_key("qbit_user")
    assert webui_security._is_sensitive_key("deluge_user")
    assert webui_security._redact_sensitive({"qbit_user": "fictional-user", "qbit_url": "http://127.0.0.1"}) == {
        "qbit_user": "<redacted>",
        "qbit_url": "http://127.0.0.1",
    }


@pytest.mark.real_settings_reauth
def test_confirmation_records_the_2fa_state_that_was_checked(redaction_config, reauth_account, monkeypatch):
    import web_ui.routes.account as account_routes

    states = iter([False, True, True])  # 2FA is enabled elsewhere right after the check
    monkeypatch.setattr(webui_security, "_totp_enabled", lambda: next(states))

    with server.app.test_request_context("/api/settings_reauth", method="POST", json={"password": "right-password"}):
        assert account_routes.settings_reauth().get_json()["success"] is True
        assert not webui_security._settings_reauth_valid()
