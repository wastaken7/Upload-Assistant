"""Account security routes: CSRF, 2FA, access log, IP control and API tokens."""

import json
from collections.abc import Sequence
from contextlib import suppress
from typing import Any, cast

import web_ui.auth as auth_mod
from web_ui import security as security_mod
from web_ui.context import access_logger, console
from web_ui.extensions import _rate_limit_key_func, limiter
from web_ui.flask_compat import Blueprint, jsonify, pyotp, request
from web_ui.request_utils import _as_dict, _request_json_dict
from web_ui.security import (
    _create_api_token,
    _ensure_csrf_token,
    _generate_recovery_codes,
    _get_ip_blacklist,
    _get_ip_whitelist,
    _hash_code,
    _list_api_tokens,
    _load_user_record,
    _persist_existing_api_token,
    _persist_recovery_hashes,
    _revoke_api_token,
    _session_get,
    _session_pop,
    _session_set,
    _set_ip_control,
)

bp = Blueprint("account", __name__)


@bp.route("/api/csrf_token")
@limiter.limit("7200 per hour", key_func=_rate_limit_key_func, override_defaults=True)
def csrf_token():
    """Return the per-session CSRF token for use by the frontend."""
    # Require authenticated web session for CSRF token access
    if not security_mod._is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401

    try:
        token = _ensure_csrf_token()
        return jsonify({"csrf_token": token, "success": True})
    except Exception:
        # Returning an empty CSRF token on error is an explicit non-secret
        # failure response; suppress Bandit's B105 false positive here.
        return jsonify({"csrf_token": "", "success": False}), 500  # nosec: B105 - not a hardcoded password


@bp.route("/api/settings_reauth", methods=["POST"])
@limiter.limit("5 per minute;30 per day", key_func=_rate_limit_key_func)
def settings_reauth():
    """Confirm the account password (and 2FA code) before settings changes."""
    if not security_mod._is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
    if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

    data = _request_json_dict()
    password = data.get("password")
    totp_code = str(data.get("totp_code") or "").strip()
    persisted = _load_user_record()
    username = persisted.get("username") if persisted else None
    password_ok = isinstance(username, str) and isinstance(password, str) and bool(password) and auth_mod.verify_user(username, password)
    totp_enabled = security_mod._totp_enabled()
    totp_ok = not totp_enabled or (bool(totp_code) and security_mod._verify_totp_code(totp_code))
    if not (password_ok and totp_ok):
        # The rate limit above bounds guessing. Failed sign-in tracking is not
        # used here: it adds the address to the permanent IP blacklist, which
        # would lock the owner out after a few typos in an open session.
        return jsonify({"success": False, "error": "Password or 2FA code did not match"}), 400

    security_mod._mark_settings_reauthenticated(totp_enabled)
    return jsonify({"success": True, "valid_seconds": security_mod.SETTINGS_REAUTH_SECONDS})


@bp.route("/api/2fa/status")
def twofa_status():
    """Check 2FA status"""
    # Require authenticated web session for 2FA status
    if not security_mod._is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401

    # Require CSRF and same-origin for reads of auth/2fa state
    if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

    return jsonify({"enabled": security_mod._totp_enabled(), "success": True})


@bp.route("/api/access_log/level", methods=["GET", "POST"])
def access_log_level_api():
    """Get or set the access logging level.

    GET: returns current level (no auth required for read).
    POST: set level (requires web session + CSRF).

    Valid levels: access_denied (default), access, disabled
    """
    if request.method == "GET":
        # Require authenticated web session and CSRF + same-origin for reads
        if not security_mod._is_authenticated():
            return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
        if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
            return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

        if access_logger is None:
            return jsonify({"success": False, "error": "Access logging unavailable"}), 500
        try:
            lvl = access_logger.get_level()
            return jsonify({"success": True, "level": lvl})
        except Exception:
            return jsonify({"success": False, "error": "Failed to read level"}), 500

    # POST: require authenticated web session and CSRF
    if not security_mod._is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
    if not security_mod._verify_csrf_header():
        return jsonify({"success": False, "error": "CSRF validation failed"}), 403
    # Require same-origin for token management actions
    if not security_mod._verify_same_origin():
        return jsonify({"success": False, "error": "Origin validation failed"}), 403
    if (reauth := security_mod._settings_reauth_required_response()) is not None:
        return reauth

    if access_logger is None:
        return jsonify({"success": False, "error": "Access logging unavailable"}), 500

    data: dict[str, object] = _request_json_dict()
    level = str(data.get("level", ""))
    if level not in ("access_denied", "access", "disabled"):
        return jsonify({"success": False, "error": "Invalid level"}), 400

    ok = access_logger.set_level(level)
    if ok:
        return jsonify({"success": True, "level": level})
    return jsonify({"success": False, "error": "Failed to persist level"}), 500


@bp.route("/api/access_log/entries", methods=["GET"])
def access_log_entries_api():
    """Get recent access log entries.

    GET: returns recent log entries (requires web session).
    Query params: n (number of entries, default 50, max 200)
    """
    # Require authenticated web session
    if not security_mod._is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401

    # Require CSRF + same-origin for reads of access-log entries
    if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

    if access_logger is None:
        return jsonify({"success": False, "error": "Access logging unavailable"}), 500

    try:
        n = request.args.get("n", "50")
        n = int(n)
        if n < 1 or n > 200:
            n = 50
    except ValueError, TypeError:
        n = 50

    try:
        entries = access_logger.tail(n)
        return jsonify({"success": True, "entries": entries})
    except Exception:
        return jsonify({"success": False, "error": "Failed to read log entries"}), 500


@bp.route("/api/ip_control", methods=["GET", "POST"])
def ip_control_api():
    """Get or set IP whitelist/blacklist.

    GET: returns current whitelist and blacklist (requires web session).
    POST: updates whitelist/blacklist. Body: {"whitelist": [...], "blacklist": [...]}
    (requires web session + CSRF).
    """
    # Require authenticated web session
    if not security_mod._is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401

    if request.method == "GET":
        # Require CSRF + same-origin for reads of IP control settings
        if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
            return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403
        try:
            whitelist = _get_ip_whitelist()
            blacklist = _get_ip_blacklist()
            return jsonify({"success": True, "whitelist": whitelist, "blacklist": blacklist})
        except Exception:
            return jsonify({"success": False, "error": "Failed to read IP control settings"}), 500

    elif request.method == "POST":
        # Require CSRF and same-origin for POST
        if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
            return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403
        if (reauth := security_mod._settings_reauth_required_response()) is not None:
            return reauth
        try:
            data_raw = request.get_json()
            data = _as_dict(data_raw) or {}
            if not data:
                return jsonify({"success": False, "error": "Invalid JSON"}), 400

            whitelist_raw = data.get("whitelist", [])
            blacklist_raw = data.get("blacklist", [])
            whitelist: list[str] = []
            blacklist: list[str] = []
            if isinstance(whitelist_raw, Sequence) and not isinstance(whitelist_raw, (str, bytes, bytearray)):
                whitelist_seq = cast(Sequence[Any], whitelist_raw)
                whitelist = [str(ip) for ip in whitelist_seq]
            if isinstance(blacklist_raw, Sequence) and not isinstance(blacklist_raw, (str, bytes, bytearray)):
                blacklist_seq = cast(Sequence[Any], blacklist_raw)
                blacklist = [str(ip) for ip in blacklist_seq]

            # Validate IP addresses
            import ipaddress

            for ip in [*whitelist, *blacklist]:
                if not ip:
                    return jsonify({"success": False, "error": f"Invalid IP format: {ip}"}), 400
                try:
                    ipaddress.ip_address(ip)
                except ValueError:
                    return jsonify({"success": False, "error": f"Invalid IP address: {ip}"}), 400

            # Report a policy that was not saved instead of claiming success.
            if not _set_ip_control(whitelist, blacklist):
                return jsonify({"success": False, "error": "Failed to update IP control settings"}), 500
            return jsonify({"success": True})
        except Exception as e:
            console.print(f"Error updating IP control: {e}", markup=False)
            return jsonify({"success": False, "error": "Failed to update IP control settings"}), 500
    return None


@bp.route("/api/2fa/setup", methods=["POST"])
def twofa_setup():
    """Setup 2FA - generate secret and return QR code URI"""
    # Require an authenticated web session (disallow API token / basic auth)
    if not security_mod._is_authenticated():
        return jsonify({"error": "Authentication required (web session)", "success": False}), 401
    # Require CSRF + same-origin for 2FA setup (sensitive auth action)
    if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"error": "CSRF/Origin validation failed", "success": False}), 403
    if (reauth := security_mod._settings_reauth_required_response()) is not None:
        return reauth
    if security_mod._totp_enabled():
        return jsonify({"error": "2FA already enabled", "success": False}), 400

    # Get username for QR code: prefer session, then persisted user, else generic
    persisted = _load_user_record()
    username = _session_get("username") or (persisted.get("username") if persisted else "user")

    # Generate secret and provisioning URI using pyotp
    secret = pyotp.random_base32()
    try:
        uri = pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name="Upload-Assistant")
    except Exception:
        uri = ""
    # Generate one-time recovery codes and store temporarily in session
    recovery_codes = _generate_recovery_codes()
    _session_set("temp_totp_secret", secret)
    _session_set("temp_recovery_codes", recovery_codes)

    return jsonify({"secret": secret, "uri": uri, "recovery_codes": recovery_codes, "success": True})


@bp.route("/api/2fa/enable", methods=["POST"])
def twofa_enable():
    """Enable 2FA after verification"""
    # Require an authenticated web session (disallow API token / basic auth)
    if not security_mod._is_authenticated():
        return jsonify({"error": "Authentication required (web session)", "success": False}), 401
    # Require CSRF + same-origin for enabling 2FA
    if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"error": "CSRF/Origin validation failed", "success": False}), 403
    if (reauth := security_mod._settings_reauth_required_response()) is not None:
        return reauth
    data = _request_json_dict()
    code = str(data.get("code", "")).strip()

    if not code:
        return jsonify({"error": "Code required", "success": False}), 400

    temp_secret = _session_get("temp_totp_secret")
    if not temp_secret:
        return jsonify({"error": "No setup in progress", "success": False}), 400

    # Verify the code with the temporary secret
    totp = pyotp.TOTP(temp_secret)
    if not totp.verify(code):
        return jsonify({"error": "Invalid code", "success": False}), 400

    # Save the secret permanently to encrypted user record
    with suppress(Exception):
        auth_mod.set_totp_secret(temp_secret)

    # Persist recovery codes (hashes) if provided
    temp_codes_raw: object = _session_get("temp_recovery_codes", [])
    temp_codes: list[str] = []
    if isinstance(temp_codes_raw, Sequence) and not isinstance(temp_codes_raw, (str, bytes, bytearray)):
        temp_codes_seq = cast(Sequence[Any], temp_codes_raw)
        temp_codes = [str(c) for c in temp_codes_seq]
    hashes = [_hash_code(c) for c in temp_codes]
    _persist_recovery_hashes(hashes)

    # Update global variable
    security_mod.saved_totp_secret = temp_secret

    # Clear temp session
    _session_pop("temp_totp_secret", None)
    _session_pop("temp_recovery_codes", None)

    return jsonify({"success": True, "recovery_codes": temp_codes})


@bp.route("/api/2fa/disable", methods=["POST"])
def twofa_disable():
    """Disable 2FA"""
    # Require an authenticated web session (disallow API token / basic auth)
    if not security_mod._is_authenticated():
        return jsonify({"error": "Authentication required (web session)", "success": False}), 401
    # Require CSRF + same-origin for disabling 2FA
    if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"error": "CSRF/Origin validation failed", "success": False}), 403
    if (reauth := security_mod._settings_reauth_required_response()) is not None:
        return reauth
    if not security_mod._totp_enabled():
        return jsonify({"error": "2FA not enabled", "success": False}), 400

    try:
        auth_mod.set_twofa_state(None, [])
    except OSError, ValueError, TypeError, auth_mod.EncryptionError, json.JSONDecodeError:
        return jsonify({"error": "Failed to disable 2FA", "success": False}), 500

    # Update global variable
    security_mod.saved_totp_secret = None

    return jsonify({"success": True})


@bp.route("/api/tokens", methods=["GET", "POST", "DELETE"])
def api_tokens():
    """Manage API bearer tokens (create/list/revoke).

    Protected: requires a logged-in session or basic auth. Tokens themselves
    can be used as Bearer auth for API calls.
    """
    # Require a browser session (remember-me or login) and a valid CSRF token.
    # Disallow managing tokens via Basic or Bearer API auth to ensure token
    # lifecycle actions are only possible from the web UI with CSRF protection.
    # Use the encrypted-session helpers so we read values stored inside the
    # encrypted `enc` payload rather than top-level Flask session keys.
    if not security_mod._is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
    if not security_mod._verify_csrf_header():
        return jsonify({"success": False, "error": "CSRF validation failed"}), 403
    if request.method != "GET" and (reauth := security_mod._settings_reauth_required_response()) is not None:
        return reauth

    if request.method == "GET":
        store = _list_api_tokens()
        # Return metadata only (do not leak token values)
        tokens: list[dict[str, Any]] = []
        for info in store.values():
            info_dict = _as_dict(info) or {}
            tokens.append(
                {
                    "id": info_dict.get("token_id"),
                    "user": info_dict.get("user"),
                    "label": info_dict.get("label"),
                    "created": info_dict.get("created"),
                    "expiry": info_dict.get("expiry"),
                }
            )
        read_only = False
        return jsonify({"success": True, "tokens": tokens, "read_only": read_only})

    if request.method == "POST":
        data = _request_json_dict()
        action = data.get("action")
        label = str(data.get("label", ""))
        # No expiry: tokens are non-expiring by default;
        persisted = _load_user_record()
        username = str(
            _session_get("username")
            or (request.authorization.username if request.authorization is not None else None)
            or (persisted.get("username") if persisted else None)
            or ""
        )
        if not username:
            return jsonify({"success": False, "error": "Unable to determine username for token"}), 400

        # Two-step flow supported:
        # - action == 'generate' (or persist=false): generate a token and do NOT persist it.
        # - action == 'store': persist an externally-provided token string (token field required).
        if action == "store":
            token_value = str(data.get("token") or "")
            if not token_value:
                return jsonify({"success": False, "error": "Token value required for store action"}), 400
            # Stored tokens grant upload access, so refuse short guessable values.
            if len(token_value) < 32:
                return jsonify({"success": False, "error": "Token must be at least 32 characters"}), 400
            # Persist tokens to the config store
            ok = _persist_existing_api_token(token_value, username, label=str(label))
            if ok:
                return jsonify({"success": True, "persisted": True})
            return jsonify({"success": False, "error": "Failed to persist token (already exists?)"}), 400

        # default/generate
        persist_flag = bool(data.get("persist", True))
        token = _create_api_token(username, label=label, persist=persist_flag)
        persisted = persist_flag
        return jsonify({"success": True, "token": token, "persisted": persisted})

    if request.method == "DELETE":
        data = _request_json_dict()
        tid = str(data.get("id") or "")
        if not tid:
            return jsonify({"success": False, "error": "Token id required"}), 400
        ok = _revoke_api_token(tid)
        if ok:
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Failed to revoke token"}), 500
    return None
