"""Authentication hardening for WebUIs exposed to the internet or shared hosts."""

import json
import os
import stat

import pytest

import web_ui.server as server
from src.usenetcreate import _redact_command, _redact_pesto_command

PASSWORD = "Fictional-Passphrase-2026!"


@pytest.fixture
def auth_root(tmp_path, monkeypatch):
    """Isolate the account file, IP controls and rate limits for each test."""
    root = tmp_path / "auth"
    root.mkdir()
    monkeypatch.setattr(server, "cfg_dir", root)
    monkeypatch.setattr(server.auth_mod, "get_config_dir", lambda: root)
    monkeypatch.setattr(server, "_first_run_setup_code_value", None)
    server.limiter.reset()
    yield root
    server.limiter.reset()


def _session_client(account: str | None):
    client = server.app.test_client()
    with client.session_transaction() as session:
        session["enc"] = server.auth_mod.encrypt_text(
            server._derive_aes_key(),
            json.dumps({"authenticated": True, "account": account, "csrf_token": "hardening-test"}),
        )
    return client


def test_first_account_requires_console_setup_code(auth_root):
    client = server.app.test_client()
    form = {"username": "fictional-user", "password": PASSWORD}

    rejected = client.post("/login", data={**form, "setup_code": "WRONG-CODE-0000"})
    assert rejected.status_code == 200
    assert b"Setup code did not match" in rejected.data
    assert server._load_user_record() is None

    code = server._first_run_setup_code().lower().replace("-", " ")
    accepted = client.post("/login", data={**form, "setup_code": code})
    assert accepted.status_code == 302
    assert server._load_user_record() is not None
    assert server._first_run_setup_code_value is None


def test_sessions_and_remember_cookies_end_when_account_is_recreated(auth_root):
    server.auth_mod.create_user("fictional-user", PASSWORD)
    fingerprint = server._account_fingerprint()
    with server.app.test_request_context("/"):
        remember = server._create_remember_token("fictional-user")
        assert server._verify_remember_token(remember) == "fictional-user"

    assert _session_client(fingerprint).get("/api/csrf_token").status_code == 200
    assert _session_client(None).get("/api/csrf_token").status_code == 401

    # Documented password reset: delete the account file and create a new one.
    (auth_root / "webui_auth.json").unlink()
    server.auth_mod.create_user("fictional-user", "Another-Fictional-Passphrase-2026!")

    assert _session_client(fingerprint).get("/api/csrf_token").status_code == 401
    with server.app.test_request_context("/"):
        assert server._verify_remember_token(remember) is None


def test_basic_auth_cannot_bypass_two_factor(auth_root, monkeypatch):
    server.auth_mod.create_user("fictional-user", PASSWORD)
    client = server.app.test_client()
    assert client.get("/api/sessions", auth=("fictional-user", PASSWORD)).status_code == 200

    monkeypatch.setattr(server, "_totp_enabled", lambda: True)
    assert client.get("/api/sessions", auth=("fictional-user", PASSWORD)).status_code == 401


def test_stored_api_tokens_must_not_be_guessable(auth_root, monkeypatch):
    server.auth_mod.create_user("fictional-user", PASSWORD)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    client = _session_client(server._account_fingerprint())
    response = client.post("/api/tokens", json={"action": "store", "token": "short"})
    assert response.status_code == 400
    assert server._list_api_tokens() == {}


def test_api_responses_are_not_cached_or_sniffed(auth_root):
    response = server.app.test_client().get("/api/health")
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_wildcard_cors_origin_is_rejected(monkeypatch):
    monkeypatch.setenv("UA_WEBUI_CORS_ORIGINS", "https://ua.example.invalid, *")
    with pytest.raises(ValueError, match="explicit origins"):
        server._parse_cors_origins()


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
def test_private_files_are_created_owner_only(tmp_path):
    target = tmp_path / "session_key"
    target.write_text("old", encoding="utf-8")
    target.chmod(0o644)
    server.auth_mod.write_private_text(target, "new")
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert target.read_text(encoding="utf-8") == "new"


def test_command_redaction_hides_attached_and_separate_passwords():
    rendered = _redact_command(["7z", "a", "-pFictionalSecret", "-mhe=on", "out.7z"])
    assert "FictionalSecret" not in rendered
    assert "-p********" in rendered

    rendered = _redact_command(["nyuu", "-u", "fictional-user", "-p", "fictional-pass", "-S"])
    assert "fictional-user" not in rendered
    assert "fictional-pass" not in rendered

    rendered = _redact_pesto_command(["pesto", "--password=fictional-pass", "--proxy", "socks5://fictional"])
    assert "fictional-pass" not in rendered
    assert "socks5://fictional" not in rendered
