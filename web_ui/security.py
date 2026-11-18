"""Web UI authentication, sessions, CSRF, API tokens, 2FA and IP controls."""

import base64
import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import threading
import time
from collections.abc import Mapping, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import web_ui.auth as auth_mod
from web_ui import context as context_mod
from web_ui.context import _cfg_read, _cfg_write, console
from web_ui.flask_compat import current_app, g, jsonify, pyotp, request, session
from web_ui.request_utils import _as_dict, _as_str_list, _json_load_dict, _request_form_text, _request_header, _request_json_dict

# Load stable session secret (env/file/SECRET_KEY fallback). Use bytes directly.

session_secret = auth_mod.load_session_secret()


# Encrypted session helpers --------------------------------------------------
def _derive_aes_key() -> bytes | None:
    try:
        return auth_mod.derive_aes_key(session_secret)
    except Exception:
        return None


def _load_session_dict() -> dict[str, object]:
    try:
        enc = session.get("enc")
        if not isinstance(enc, str) or not enc:
            return {}
        key = _derive_aes_key()
        if not key:
            return {}
        dec = auth_mod.decrypt_text(key, enc)
        if not dec:
            return {}
        return _json_load_dict(dec)
    except Exception:
        return {}


def _commit_session_dict(d: dict[str, object]) -> None:
    with contextlib.suppress(Exception):
        key = _derive_aes_key()
        if not key:
            return
        raw = json.dumps(d, separators=(",", ":"), ensure_ascii=False)
        enc = auth_mod.encrypt_text(key, raw)
        session["enc"] = enc


def _load_user_record() -> dict[str, Any] | None:
    load_user_fn = getattr(auth_mod, "load_user", None)
    if not callable(load_user_fn):
        return None
    record = _as_dict(load_user_fn())
    # IP controls and access-log settings share the file before an account exists.
    if record is None or not record.get("password_hash"):
        return None
    return record


def _session_get(key: str, default: object = None) -> Any:
    return _load_session_dict().get(key, default)


def _session_set(key: str, value: object) -> None:
    d = _load_session_dict()
    d[key] = value
    _commit_session_dict(d)


def _ensure_csrf_token() -> str:
    """Return the current session CSRF token, creating it when required."""
    token = _session_get("csrf_token")
    if token:
        return str(token)
    if not _is_authenticated():
        return ""
    token = secrets.token_urlsafe(32)
    _session_set("csrf_token", token)
    return token


def _session_pop(key: str, default: object = None) -> object:
    d = _load_session_dict()
    val = d.pop(key, default)
    _commit_session_dict(d)
    return val


# IP control helpers --------------------------------------------------
def _get_ip_whitelist() -> list[str]:
    """Get the list of whitelisted IPs."""
    with contextlib.suppress(Exception):
        path = context_mod.cfg_dir / "webui_auth.json"
        if path.exists():
            data = _json_load_dict(path.read_text(encoding="utf-8"))
            val = data.get("ip_whitelist")
            items = _as_str_list(val)
            if items is not None:
                return items
    return []


def _get_ip_blacklist() -> list[str]:
    """Get the list of blacklisted IPs."""
    with contextlib.suppress(Exception):
        path = context_mod.cfg_dir / "webui_auth.json"
        if path.exists():
            data = _json_load_dict(path.read_text(encoding="utf-8"))
            val = data.get("ip_blacklist")
            items = _as_str_list(val)
            if items is not None:
                return items
    return []


def _set_ip_control(whitelist: list[str], blacklist: list[str]) -> bool:
    """Save both IP lists in one write so a failure cannot apply only one of them."""
    try:
        path = context_mod.cfg_dir / "webui_auth.json"
        data: dict[str, Any] = {}
        if path.exists():
            data = _json_load_dict(path.read_text(encoding="utf-8"))
        data["ip_whitelist"] = whitelist
        data["ip_blacklist"] = blacklist
        auth_mod.write_private_text(path, json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        return False
    return True


def _set_ip_blacklist(ips: list[str]) -> bool:
    """Set the list of blacklisted IPs, returning whether it was saved."""
    try:
        path = context_mod.cfg_dir / "webui_auth.json"
        data: dict[str, Any] = {}
        if path.exists():
            data = _json_load_dict(path.read_text(encoding="utf-8"))
        data["ip_blacklist"] = ips
        auth_mod.write_private_text(path, json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        return False
    return True


def _get_ip_failures() -> dict[str, list[int]]:
    """Get the dict of IP failure timestamps.

    Returns a mapping of `ip -> list[int]` (UNIX timestamps). For backward
    compatibility any integer legacy counts are converted into recent
    timestamps so they behave as recent failures.
    """
    with contextlib.suppress(Exception):
        path = context_mod.cfg_dir / "webui_auth.json"
        if path.exists():
            data = _json_load_dict(path.read_text(encoding="utf-8"))
            val = data.get("ip_failures")
            val_dict = _as_dict(val)
            if val_dict is not None:
                now = int(time.time())
                out: dict[str, list[int]] = {}
                for k, v in val_dict.items():
                    if isinstance(v, Sequence) and not isinstance(v, (str, bytes, bytearray)):
                        # Coerce list members to ints and filter invalid
                        value_list = cast(Sequence[Any], v)
                        try:
                            out[str(k)] = [int(x) for x in value_list]
                        except Exception:
                            out[str(k)] = []
                    elif isinstance(v, int):
                        # Legacy count: treat as recent failures
                        out[str(k)] = [now] * v
                return out
    return {}


def _set_ip_failures(failures: dict[str, list[int]]) -> None:
    """Set the dict of IP failure timestamps (ip -> list[timestamps])."""
    with contextlib.suppress(Exception):
        path = context_mod.cfg_dir / "webui_auth.json"
        data = {}
        if path.exists():
            try:
                data = _json_load_dict(path.read_text(encoding="utf-8"))
            except Exception:
                return
        data["ip_failures"] = failures
        auth_mod.write_private_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def _is_ip_allowed(ip: str) -> bool:
    """Check if an IP is allowed based on whitelist/blacklist."""
    whitelist = _get_ip_whitelist()
    blacklist = _get_ip_blacklist()

    # Blacklist takes absolute precedence. If an IP is blacklisted,
    # deny it even if it's present in the whitelist.
    if ip in blacklist:
        return False

    # If whitelist is set, only allow IPs in whitelist.
    if whitelist:
        return ip in whitelist

    # Otherwise, allow (not blacklisted).
    return True


def _handle_failed_auth(ip: str) -> None:
    """Handle failed authentication attempt. Track failures and blacklist if too many."""
    # Configuration: threshold and window (seconds)
    failure_threshold = 5
    failure_window = 300  # 5 minutes

    failures = _get_ip_failures()
    now = int(time.time())
    pts = failures.get(ip, [])
    # Prune old entries outside the window and append current timestamp
    pts = [t for t in pts if t >= now - failure_window]
    pts.append(now)
    failures[ip] = pts
    _set_ip_failures(failures)

    # Blacklist if threshold exceeded within window
    if len(pts) >= failure_threshold:
        blacklist = _get_ip_blacklist()
        if ip not in blacklist:
            blacklist.append(ip)
            _set_ip_blacklist(blacklist)


def _account_fingerprint() -> str | None:
    """Identify the current account credentials without exposing the password hash.

    Sessions and remember-me cookies carry this value, so recreating the account
    (the documented password reset) or changing its password signs out every
    existing browser.
    """
    record = _load_user_record()
    password_hash = record.get("password_hash") if record else None
    key = _derive_aes_key()
    if not isinstance(password_hash, str) or not password_hash or not key:
        return None
    return hmac.new(key, b"webui-account:" + password_hash.encode("utf-8"), hashlib.sha256).hexdigest()


def _account_fingerprint_matches(value: object) -> bool:
    fingerprint = _account_fingerprint()
    return fingerprint is not None and isinstance(value, str) and hmac.compare_digest(value, fingerprint)


def _is_authenticated() -> bool:
    if getattr(g, "authenticated", False):
        return True
    session_data = _load_session_dict()
    return bool(session_data.get("authenticated")) and _account_fingerprint_matches(session_data.get("account"))


def _mark_session_authenticated(username: str) -> None:
    """Replace the browser session with a fresh authenticated one.

    The password was just entered, so it also counts as a settings
    confirmation. Remember-me cookies restore sign-in without this.
    """
    fingerprint = _account_fingerprint()
    _commit_session_dict(
        {
            "authenticated": True,
            "username": username,
            "account": fingerprint,
            "csrf_token": secrets.token_urlsafe(32),
            "settings_reauth": _settings_reauth_state(fingerprint, _totp_enabled()),
        }
    )
    # Issue a new session id so an id known before sign-in cannot be reused.
    with contextlib.suppress(Exception):
        current_app.session_interface.regenerate(session)


# Settings changes can run programs (tool paths, post-upload hooks), so a
# signed-in browser must confirm the account password before changing them.
SETTINGS_REAUTH_SECONDS = 15 * 60
SETTINGS_REAUTH_HEADER = "X-UA-Reauth-Required"


def _mark_settings_reauthenticated(totp_verified: bool) -> None:
    """Allow settings changes from this browser session for a short time.

    ``totp_verified`` is the 2FA state checked by the caller, read before
    verification, so a concurrent 2FA change cannot be recorded as verified.
    """
    _session_set("settings_reauth", _settings_reauth_state(_account_fingerprint(), totp_verified))


def _settings_reauth_state(fingerprint: str | None, totp_enabled: bool) -> dict[str, object]:
    # Record the 2FA state that was verified: enabling 2FA elsewhere must
    # require the new factor before, for example, disabling it again.
    return {"until": time.time() + SETTINGS_REAUTH_SECONDS, "account": fingerprint, "totp": totp_enabled}


def _settings_reauth_valid() -> bool:
    """Return True when this session confirmed the password recently."""
    state = _session_get("settings_reauth")
    if not isinstance(state, Mapping):
        return False
    state_map = cast(Mapping[str, Any], state)
    until = state_map.get("until")
    return isinstance(until, (int, float)) and until > time.time() and _account_fingerprint_matches(state_map.get("account")) and state_map.get("totp") == _totp_enabled()


def _settings_reauth_required_response() -> Any | None:
    """Return a 403 response asking for password confirmation, or None if confirmed."""
    if _settings_reauth_valid():
        return None
    response = jsonify(
        {
            "success": False,
            "error": "Confirm your WebUI password to change settings.",
            "reauth_required": True,
            "totp_required": _totp_enabled(),
        }
    )
    response.status_code = 403
    response.headers[SETTINGS_REAUTH_HEADER] = "1"
    return response


_first_run_setup_code_value: str | None = None
_first_run_setup_code_lock = threading.Lock()


def _normalize_setup_code(code: str) -> str:
    return re.sub(r"[\s-]+", "", code).upper()


def _first_run_setup_code() -> str:
    """Return the one-time code that authorizes creating the first account.

    The code is printed to the server console when it is created, so only
    someone who can see the Upload Assistant output can create the account.
    """
    global _first_run_setup_code_value
    with _first_run_setup_code_lock:
        if _first_run_setup_code_value is None:
            alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
            raw = "".join(secrets.choice(alphabet) for _ in range(12))
            _first_run_setup_code_value = "-".join(raw[i : i + 4] for i in range(0, len(raw), 4))
            console.print(
                f"WebUI first-run setup code: {_first_run_setup_code_value} (enter it on the sign-in page to create the WebUI account)",
                markup=False,
            )
        return _first_run_setup_code_value


def _first_run_setup_code_matches(code: str) -> bool:
    expected = _normalize_setup_code(_first_run_setup_code())
    return bool(code) and hmac.compare_digest(_normalize_setup_code(code), expected)


def _clear_first_run_setup_code() -> None:
    global _first_run_setup_code_value
    with _first_run_setup_code_lock:
        _first_run_setup_code_value = None


def _cleanup_duplicate_sessions(username: str) -> None:
    """Remove other session files that belong to `username` to keep a
    single session file per user. This inspects files under the configured
    `SESSION_FILE_DIR` and attempts to decrypt stored `enc` payloads using
    the current derived AES key.
    """
    with contextlib.suppress(Exception):
        key = _derive_aes_key()
        if not key:
            return
        current_enc = session.get("enc")
        sdir = Path(current_app.config.get("SESSION_FILE_DIR", ""))
        if not sdir or not sdir.exists():
            return
        for p in sdir.iterdir():
            if not p.is_file():
                continue
            # Suppress per-file errors and continue processing other files.
            # Use contextlib.suppress to avoid a try/except/continue pattern
            # that Bandit flags (B112).
            with contextlib.suppress(Exception):
                txt = p.read_text(encoding="utf-8", errors="ignore").strip()
                candidate_enc = None
                # If file is JSON with an 'enc' key, use that
                try:
                    j = _json_load_dict(txt)
                    enc_value = j.get("enc")
                    if isinstance(enc_value, str):
                        candidate_enc = enc_value
                except Exception:
                    # Not JSON - treat whole file as enc payload
                    candidate_enc = txt

                if not candidate_enc:
                    continue

                # Skip the file that matches our current session payload
                if current_enc and candidate_enc == current_enc:
                    continue

                dec = None
                try:
                    dec = auth_mod.decrypt_text(key, candidate_enc)
                except Exception:
                    dec = None

                if not dec:
                    continue

                try:
                    obj = _json_load_dict(dec)
                    u = obj.get("username")
                except Exception:
                    u = None

                if u and u == username:
                    # Remove stale session file
                    with contextlib.suppress(Exception):
                        p.unlink()


# Runtime flags and stored totp
saved_totp_secret: str | None = None


# CSRF helpers ---------------------------------------------------------------
def _verify_csrf_header() -> bool:
    """Verify incoming request contains a valid CSRF token.

    Checks the `X-CSRF-Token` header first, then falls back to JSON/form field
    named `csrf_token` for compatibility with clients that embed it in the body.
    """
    try:
        # If client used a bearer token, treat that as sufficient for CSRF-safe API usage
        auth_header = _request_header("Authorization").strip()
        if auth_header.lower().startswith("bearer "):
            b = auth_header.split(None, 1)[1].strip()
            if b and _verify_api_token(b):
                return True

        token = _session_get("csrf_token")
        if not token:
            return False
        header = _request_header("X-CSRF-Token")
        if not header:
            data: dict[str, Any] = {}
            try:
                data = _request_json_dict()
            except Exception:
                data = {}
            form_token = _request_form_text("csrf_token")
            header = data.get("csrf_token") or (form_token if form_token else None)

        if not header:
            return False
        return hmac.compare_digest(str(token), str(header))
    except Exception:
        return False


def _verify_same_origin() -> bool:
    """Require same-origin browser metadata, Origin, or Referer headers.

    Fetch Metadata is preferred when the browser identifies the request as
    same-origin. Otherwise the Origin or Referer host must match the server's
    request host. Absence or mismatch results in False.
    """
    try:
        # Modern browsers provide Fetch Metadata independently of Referer.
        # This remains reliable when privacy settings or a reverse proxy omit
        # or rewrite the Referer/Host values. Sec-Fetch-* headers cannot be set
        # by cross-origin browser JavaScript, and protected routes still require
        # the per-session CSRF token separately.
        fetch_site = _request_header("Sec-Fetch-Site").strip().lower()
        if fetch_site == "same-origin":
            return True

        # Prefer comparing the origin/referer host:port (netloc) to the
        # request host. This is scheme-insensitive and avoids failures
        # when proxies/Cloudflare terminate TLS or don't forward the
        # original scheme.
        from urllib.parse import urlparse

        origin: str = _request_header("Origin")
        if origin and origin.strip().lower() != "null":
            with contextlib.suppress(Exception):
                parsed = urlparse(origin)
                if parsed.netloc:
                    return parsed.netloc.lower() == request.host.lower()
            # Fallback to strict host_url match if parsing fails
            host_url = (request.host_url or "").rstrip("/") + "/"
            return origin.rstrip("/") + "/" == host_url

        referer: str = _request_header("Referer") or _request_header("Referrer")
        if referer:
            with contextlib.suppress(Exception):
                parsed = urlparse(referer)
                if parsed.netloc:
                    return parsed.netloc.lower() == request.host.lower()
            host_url = (request.host_url or "").rstrip("/") + "/"
            return referer.startswith(host_url)

        return False
    except Exception:
        return False


# Load TOTP secret
try:
    saved_totp_secret = auth_mod.get_totp_secret()
except Exception:
    saved_totp_secret = None


# Persistent cookie key helpers -------------------------------------------------
def _get_persistent_cookie_key() -> bytes | None:
    """Return a bytes key used to HMAC-sign remember-me cookies.
    Read the persisted key from the config dir; if missing, generate and store one.
    """
    with contextlib.suppress(Exception):
        raw = _cfg_read("session_key")
        if raw:
            try:
                return bytes.fromhex(raw)
            except Exception:
                return raw.encode("utf-8")

    # Generate and persist to config if no persisted key found
    try:
        new = secrets.token_hex(32)
        with contextlib.suppress(Exception):
            _cfg_write("session_key", new)
        return bytes.fromhex(new)
    except Exception:
        return None


def _hash_api_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _normalize_token_store(store: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    normalized: dict[str, Any] = {}
    changed = False
    for key, value in store.items():
        info_dict = dict(_as_dict(value) or {})
        token_hash = str(key)
        if not re.fullmatch(r"[0-9a-f]{64}", token_hash):
            token_hash = _hash_api_token(token_hash)
            changed = True
        if not info_dict.get("token_id"):
            info_dict["token_id"] = secrets.token_hex(16)
            changed = True
        normalized[token_hash] = info_dict
    return normalized, changed


def _load_token_store() -> dict[str, Any]:
    try:
        get_api_tokens_fn = getattr(auth_mod, "get_api_tokens", None)
        if not callable(get_api_tokens_fn):
            return {}
        store = get_api_tokens_fn()
        if isinstance(store, Mapping):
            store_dict: dict[Any, Any] = cast(dict[Any, Any], store)
            result: dict[str, Any] = {}
            for key, value in store_dict.items():
                result[str(key)] = value
            normalized, changed = _normalize_token_store(result)
            if changed:
                _persist_token_store(normalized)
            return normalized
        return {}
    except Exception:
        return {}


def _persist_token_store(store: dict[str, Any]) -> None:
    with suppress(Exception):
        set_api_tokens_fn = getattr(auth_mod, "set_api_tokens", None)
        if callable(set_api_tokens_fn):
            set_api_tokens_fn(store)


def _create_api_token(username: str, label: str = "", persist: bool = True, token_value: str | None = None) -> str:
    """Create a new API token. If `persist` is False, do not write the token store to durable storage.
    Optionally accept `token_value` to use an externally-provided token string when persisting.
    """
    store = _load_token_store()
    token = token_value if token_value else secrets.token_urlsafe(96)
    token_hash = _hash_api_token(token)
    token_id = secrets.token_hex(16)
    expiry = None
    store[token_hash] = {"token_id": token_id, "user": username, "label": label, "created": int(datetime.now(UTC).timestamp()), "expiry": expiry}
    if persist:
        _persist_token_store(store)
    with contextlib.suppress(Exception):
        _write_audit_log("create_api_token", [username], None, {"id": token_id, "label": label}, True)
    return token


def _persist_existing_api_token(token: str, username: str, label: str = "") -> bool:
    """Persist an existing token string into the token store. Returns True on success."""
    if not token:
        return False
    store = _load_token_store()
    token_hash = _hash_api_token(token)
    if token_hash in store:
        return False
    expiry = None
    token_id = secrets.token_hex(16)
    store[token_hash] = {"token_id": token_id, "user": username, "label": label, "created": int(datetime.now(UTC).timestamp()), "expiry": expiry}
    _persist_token_store(store)
    with contextlib.suppress(Exception):
        _write_audit_log("create_api_token", [username], None, {"id": token_id, "label": label}, True)
    return True


def _verify_api_token(token: str) -> str | None:
    # Short legacy tokens are guessable; generated tokens are far longer.
    if not token or len(token) < 32:
        return None
    store = _load_token_store()
    info = store.get(_hash_api_token(token))
    info_dict = _as_dict(info)
    if info_dict is None:
        return None
    expiry = info_dict.get("expiry")
    if isinstance(expiry, int) and int(datetime.now(UTC).timestamp()) > expiry:
        return None
    user = info_dict.get("user")
    return str(user) if user is not None else None


def _get_token_info(token: str) -> dict[str, Any] | None:
    """Return stored token info dict or None."""
    if not token:
        return None
    store = _load_token_store()
    info = store.get(_hash_api_token(token))
    info_dict = _as_dict(info)
    if info_dict is None:
        return None
    expiry = info_dict.get("expiry")
    if isinstance(expiry, int) and int(datetime.now(UTC).timestamp()) > expiry:
        return None
    return info_dict


def _token_is_valid(token: str) -> bool:
    """Return True if token is valid. No per-token scopes enforced."""
    info = _get_token_info(token)
    return bool(info)


def _get_bearer_from_header() -> str | None:
    auth_header = _request_header("Authorization").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(None, 1)[1].strip()
    return None


def _revoke_api_token(token_or_id: str) -> bool:
    store = _load_token_store()
    token_hash = _hash_api_token(token_or_id) if token_or_id else ""
    store_key = token_hash if token_hash in store else None
    if store_key is None:
        for candidate_key, info in store.items():
            info_dict = _as_dict(info) or {}
            if info_dict.get("token_id") == token_or_id:
                store_key = candidate_key
                break
    if store_key is None:
        return False
    owner_info = _as_dict(store[store_key]) or {}
    owner = owner_info.get("user")
    token_id = owner_info.get("token_id")
    del store[store_key]
    _persist_token_store(store)
    with contextlib.suppress(Exception):
        _write_audit_log("revoke_api_token", [str(owner)] if owner is not None else [], {"id": token_id}, None, True)
    return True


def _list_api_tokens() -> dict[str, Any]:
    return _load_token_store()


def _create_remember_token(username: str, days: int = 30) -> str | None:
    key = _get_persistent_cookie_key()
    if not key:
        return None
    expiry = int(datetime.now(UTC).timestamp()) + days * 86400
    payload = json.dumps({"u": username, "e": expiry, "a": _account_fingerprint()}, separators=(",", ":")).encode("utf-8")
    b64 = base64.urlsafe_b64encode(payload).decode("ascii")
    sig = hmac.new(key, b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64}|{sig}"


def _verify_remember_token(token: str) -> str | None:
    key = _get_persistent_cookie_key()
    if not key or not token:
        return None
    try:
        parts = token.split("|")
        if len(parts) != 2:
            return None
        b64, sig = parts
        expected = hmac.new(key, b64.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        payload = base64.urlsafe_b64decode(b64.encode("ascii"))
        data = _json_load_dict(payload.decode("utf-8"))
        username = data.get("u")
        expiry_value = data.get("e")
        if expiry_value is None:
            expiry = 0
        elif isinstance(expiry_value, int):
            expiry = expiry_value
        elif isinstance(expiry_value, str):
            try:
                expiry = int(expiry_value)
            except TypeError, ValueError:
                return None
        else:
            return None
        if not username or expiry < int(datetime.now(UTC).timestamp()):
            return None
        if not _account_fingerprint_matches(data.get("a")):
            return None
        return str(username)
    except Exception:
        return None


def _hash_code(code: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", code.encode("utf-8"), b"upload-assistant-recovery-salt", 100000).hex()


def _generate_recovery_codes(n: int = 10, length: int = 10) -> list[str]:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # Crockford-like, avoid ambiguous chars
    return ["".join(secrets.choice(alphabet) for _ in range(length)) for _ in range(n)]


def _load_recovery_hashes() -> list[str]:
    # Load recovery hashes from the encrypted extras in the user record
    try:
        get_recovery_hashes_fn = getattr(auth_mod, "get_recovery_hashes", None)
        if not callable(get_recovery_hashes_fn):
            return []
        hashes = get_recovery_hashes_fn()
        if isinstance(hashes, Sequence) and not isinstance(hashes, (str, bytes, bytearray)):
            value_seq: Sequence[Any] = cast(Sequence[Any], hashes)
            return [str(item) for item in value_seq]
        return []
    except Exception:
        return []


def _persist_recovery_hashes(hashes: list[str]) -> None:
    with suppress(Exception):
        set_recovery_hashes_fn = getattr(auth_mod, "set_recovery_hashes", None)
        if callable(set_recovery_hashes_fn):
            set_recovery_hashes_fn(hashes)


def _consume_recovery_code(code: str) -> bool:
    """Return True if code matches an unused recovery code and mark it used (persist)."""
    if not code:
        return False
    hashes = _load_recovery_hashes()
    if not hashes:
        return False
    h = _hash_code(code.strip())
    if h in hashes:
        hashes.remove(h)
        _persist_recovery_hashes(hashes)
        return True
    return False


def _webui_auth_configured() -> bool:
    # Consider auth configured if a local user file exists
    return _load_user_record() is not None


def _webui_auth_ok() -> bool:
    """Return True when the incoming request is authenticated.

    Authentication sources:
    - Bearer token (API token) — validated via _verify_api_token(); when a
      persisted user exists ensure the token's username matches it.
    - Basic auth — only valid when a persisted user exists and credentials
      validate against that persisted user.
    """
    persisted = _load_user_record()

    # Bearer tokens for API clients
    bearer_token = _get_bearer_from_header()
    if bearer_token:
        user = _verify_api_token(bearer_token)
        if user:
            if persisted:
                stored_username = persisted.get("username")
                if stored_username and user != stored_username:
                    return False
            with contextlib.suppress(Exception):
                g.username = user
            return True
        return False

    # Basic auth is only supported against a persisted user
    auth = request.authorization
    if not auth or auth.type != "basic":
        return False
    if not persisted:
        return False
    # Basic auth carries no second factor, so it would bypass 2FA.
    if _totp_enabled():
        return False
    return auth_mod.verify_user(auth.username or "", auth.password or "")


def _totp_enabled() -> bool:
    # TOTP is enabled when a TOTP secret is configured either in persisted
    # storage or via environment (saved_totp_secret).
    persisted = _load_user_record()
    if persisted:
        return bool(auth_mod.get_totp_secret())
    return bool(saved_totp_secret)


def _verify_totp_code(code: str) -> bool:
    """Verify a TOTP code against the stored secret."""
    persisted = _load_user_record()
    secret = auth_mod.get_totp_secret() if persisted else saved_totp_secret

    if not secret:
        return False

    try:
        totp = pyotp.TOTP(secret)
        return bool(code and totp.verify(code))
    except Exception:
        return False


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        value_seq: Sequence[Any] = cast(Sequence[Any], value)
        return [_json_safe(v) for v in value_seq]
    if isinstance(value, Mapping):
        value_dict = cast(dict[Any, Any], value)
        return {str(k): _json_safe(v) for k, v in value_dict.items()}
    return str(value)


_SENSITIVE_KEY_PARTS = (
    "password",
    "pass",
    "secret",
    "token",
    "key",
    "totp",
    "api",
    "credential",
    "auth",
    "userhash",
    "client_id",
    "announce",
    "cookie",
    "login_answer",
    "proxy_url",
    "rtorrent_url",
    "username",
    "qbit_user",
    "deluge_user",
)


def _redact_sensitive(value: Any) -> Any:
    """Return a copy of the value with sensitive dictionary fields redacted.

    Keys containing any substring from ``_SENSITIVE_KEY_PARTS`` are redacted
    (case-insensitive).
    """
    sensitive_parts = _SENSITIVE_KEY_PARTS

    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        value_dict = cast(dict[Any, Any], value)
        for k, v in value_dict.items():
            try:
                lk = str(k).lower()
            except Exception:
                lk = ""
            if any(p in lk for p in sensitive_parts):
                out[str(k)] = "<redacted>"
            else:
                out[str(k)] = _redact_sensitive(v)
        return out
    if isinstance(value, (list, tuple)):
        value_seq: Sequence[Any] = cast(Sequence[Any], value)
        return [_redact_sensitive(v) for v in value_seq]
    # For primitives (str/int/etc.) we keep the value as-is — redaction is key-based
    return value


def _is_sensitive_key(key: Any) -> bool:
    """Return True when a config path component names a sensitive field."""
    if not isinstance(key, str):
        return False
    lowered = key.lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def _write_audit_log(action: str, path: list[str], old_value: Any, new_value: Any, success: bool, error: str | None = None) -> None:
    """Append an audit record to data/config_audit.log.

    Uses UTC ISO timestamps and attempts to record the acting user and remote
    address. Values are passed through `_json_safe` to ensure JSON-serializable
    output. Any exceptions writing the audit are logged to the console but do
    not raise to callers.
    """
    try:
        base_dir = context_mod.STATE_DIR
        audit_path = base_dir / "data" / "config_audit.log"
        # Determine acting user: session -> Basic auth username -> persisted user -> remote_addr
        persisted = _load_user_record()
        user = (
            _session_get("username")
            or (request.authorization.username if request.authorization is not None else None)
            or (persisted.get("username") if persisted else None)
            or request.remote_addr
        )
        # Redact sensitive fields from values before serializing to the audit log.
        path_is_sensitive = any(_is_sensitive_key(component) for component in path)
        redacted_old_value = "[REDACTED]" if path_is_sensitive and old_value not in (None, "") else _redact_sensitive(old_value)
        redacted_new_value = "[REDACTED]" if path_is_sensitive and new_value not in (None, "") else _redact_sensitive(new_value)
        audit: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "user": user,
            "remote_addr": request.remote_addr,
            "action": action,
            "path": path,
            "old_value": _json_safe(redacted_old_value),
            "new_value": _json_safe(redacted_new_value),
            "success": success,
            "error": error,
        }
        with Path(audit_path).open("a", encoding="utf-8") as af:
            # codeql[py/clear-text-storage-sensitive-data]
            af.write(json.dumps(audit, ensure_ascii=False) + "\n")
    except Exception as ae:
        with contextlib.suppress(Exception):
            console.print(f"Failed to write config audit record: {ae}", markup=False)


def _readable_secret_files() -> list[Path]:
    """List credential files that other local accounts can read (POSIX only)."""
    if os.name != "posix":
        return []
    data_dir = context_mod.STATE_DIR / "data"
    candidates = [data_dir / "config.py", context_mod.cfg_dir / "webui_auth.json", context_mod.cfg_dir / "session_secret", context_mod.cfg_dir / "session_key"]
    with contextlib.suppress(OSError):
        candidates.extend(path for path in (data_dir / "cookies").iterdir() if path.is_file())
    readable: list[Path] = []
    for path in candidates:
        with contextlib.suppress(OSError):
            if path.stat().st_mode & (stat.S_IRGRP | stat.S_IROTH):
                readable.append(path)
    return readable
