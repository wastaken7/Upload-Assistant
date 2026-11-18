"""HTML pages and login/logout routes."""

import contextlib
import traceback
from contextlib import suppress

import web_ui.auth as auth_mod
from src.args import cli_argument_catalog
from src.webui_paths import MAX_UPLOAD_PATHS
from web_ui import security as security_mod
from web_ui.context import APP_VERSION, console
from web_ui.extensions import limiter
from web_ui.flask_compat import Blueprint, Response, current_app, get_remote_address, jsonify, redirect, render_template, request, session, url_for
from web_ui.request_utils import _request_form_text, _request_header
from web_ui.security import (
    _cleanup_duplicate_sessions,
    _clear_first_run_setup_code,
    _consume_recovery_code,
    _create_remember_token,
    _ensure_csrf_token,
    _first_run_setup_code,
    _first_run_setup_code_matches,
    _handle_failed_auth,
    _load_user_record,
    _mark_session_authenticated,
    _verify_totp_code,
)

bp = Blueprint("pages", __name__)


@bp.route("/")
def index():
    """Serve the main UI"""
    try:
        return render_template(
            "index.html",
            app_version=APP_VERSION,
            csrf_token=_ensure_csrf_token(),
            cli_arguments=cli_argument_catalog(),
            max_upload_paths=MAX_UPLOAD_PATHS,
            screenshot_mode=request.args.get("screenshot") == "1",
        )
    except Exception as e:
        console.print(f"Error loading template: {e}", markup=False)
        console.print(traceback.format_exc(), markup=False)
        return "<pre>Internal server error</pre>", 500


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute;100 per day", key_func=get_remote_address, error_message="Too many attempts, please try again later.")
def login_page():
    if request.method == "POST":
        # Quick IP block check: short-circuit heavy work for known-bad IPs.
        if not security_mod._is_ip_allowed(get_remote_address()):
            return Response("Too many requests", status=429, mimetype="text/plain")
        username = _request_form_text("username").strip()
        password = _request_form_text("password").strip()
        totp_code = _request_form_text("totp_code").strip()
        remember = _request_form_text("remember") == "1"

        persisted = _load_user_record()
        if persisted:
            # Persisted user exists: require matching credentials
            if auth_mod.verify_user(username, password):
                if security_mod._totp_enabled() and not (totp_code and _verify_totp_code(totp_code)):
                    _handle_failed_auth(get_remote_address())
                    return render_template("login.html", error="Credentials did not match", show_2fa=security_mod._totp_enabled(), setup_mode=False)

                _mark_session_authenticated(username)
                if remember:
                    session.permanent = True
                resp = redirect(url_for("pages.index"))
                if remember:
                    with contextlib.suppress(Exception):
                        token = _create_remember_token(username)
                        if token:
                            resp.set_cookie("ua_remember", token, max_age=30 * 86400, httponly=True, secure=True, samesite="Lax")
                with suppress(Exception):
                    _cleanup_duplicate_sessions(username)
                return resp
            # Credentials don't match persisted user
            _handle_failed_auth(get_remote_address())
            return render_template("login.html", error="Credentials did not match", setup_mode=False)
        # No persisted user: allow UI-driven creation (first-run setup). The
        # setup code is only shown in the server console, so a visitor who
        # reaches an exposed WebUI first cannot claim the account.
        if username and password:
            if not _first_run_setup_code_matches(_request_form_text("setup_code")):
                _handle_failed_auth(get_remote_address())
                return render_template("login.html", error="Setup code did not match. Copy it from the Upload Assistant console output.", setup_mode=True)
            try:
                auth_mod.create_user(username, password)
            except ValueError as exc:
                return render_template("login.html", error=str(exc), setup_mode=True)
            except Exception:
                return render_template("login.html", error="Unable to create account", setup_mode=True)
            _clear_first_run_setup_code()

            _mark_session_authenticated(username)
            if remember:
                session.permanent = True
                with contextlib.suppress(Exception):
                    token = _create_remember_token(username)
                    if token:
                        resp = redirect(url_for("pages.config_page"))
                        resp.set_cookie("ua_remember", token, max_age=30 * 86400, httponly=True, secure=True, samesite="Lax")
                        with suppress(Exception):
                            _cleanup_duplicate_sessions(username)
                        return resp

            with suppress(Exception):
                _cleanup_duplicate_sessions(username)
            return redirect(url_for("pages.config_page"))
        # No username/password provided
        _handle_failed_auth(get_remote_address())
        return render_template("login.html", error="Credentials did not match", setup_mode=True)

    # Show 2FA field if enabled
    show_2fa = security_mod._totp_enabled()
    setup_mode = _load_user_record() is None
    if setup_mode:
        _first_run_setup_code()
    return render_template("login.html", show_2fa=show_2fa, setup_mode=setup_mode)


@bp.route("/logout", methods=["GET", "POST"])  # prefer POST from the UI
def logout():
    # Accept both GET and POST for compatibility, but UI should use POST.
    # Remove encrypted session payload
    # Clear all server-side session data
    try:
        session.clear()
    except Exception:
        # Fallback: remove encrypted payload if clear fails
        session.pop("enc", None)

    resp = redirect(url_for("pages.login_page"))
    # Remove remember cookie if present
    resp.delete_cookie("ua_remember")
    # Also remove the browser session cookie (Flask's session cookie name)
    try:
        resp.delete_cookie(current_app.session_cookie_name)
    except Exception:
        # Fallback to common cookie name
        resp.delete_cookie("session")
    return resp


@bp.route("/login/recovery", methods=["GET", "POST"])
@limiter.limit("10 per minute;100 per day", key_func=get_remote_address, error_message="Too many attempts, please try again later.")
def login_recovery():
    """Handle login using a recovery code. This is a separate endpoint to
    keep recovery-code input distinct from strict 2FA inputs so password
    managers treat the 2FA input as a one-time code field.
    """
    # If GET, render the dedicated recovery page (minimal inputs)
    if request.method == "GET":
        return render_template("login_recovery.html", show_2fa=security_mod._totp_enabled())

    # POST: process recovery code login
    # Quick IP block check: short-circuit heavy work for known-bad IPs.
    if not security_mod._is_ip_allowed(get_remote_address()):
        return Response("Too many requests", status=429, mimetype="text/plain")

    username = _request_form_text("username").strip()
    password = _request_form_text("password").strip()
    recovery_code = _request_form_text("recovery_code").strip()
    remember = _request_form_text("remember") == "1"

    if not security_mod._totp_enabled():
        return render_template("login_recovery.html", error="Recovery codes are not enabled", show_2fa=False)

    persisted = _load_user_record()
    # If a persisted user exists, require those credentials + recovery code
    if persisted:
        if username and password and recovery_code and _consume_recovery_code(recovery_code) and auth_mod.verify_user(username, password):
            _mark_session_authenticated(username)
            if remember:
                session.permanent = True
                with contextlib.suppress(Exception):
                    token = _create_remember_token(username)
                    if token:
                        resp = redirect(url_for("pages.index"))
                        resp.set_cookie("ua_remember", token, max_age=30 * 86400, httponly=True, secure=True, samesite="Lax")
                        return resp
            return redirect(url_for("pages.index"))
        # Failed recovery attempt -> record and show recovery page
        _handle_failed_auth(get_remote_address())
        return render_template("login_recovery.html", error="Recovery code invalid", show_2fa=security_mod._totp_enabled())

    _handle_failed_auth(get_remote_address())
    return render_template("login_recovery.html", error="Recovery code invalid", show_2fa=security_mod._totp_enabled())


@bp.route("/config")
def config_page():
    """Serve the config UI"""
    # Require a CSRF token or same-origin Referer for the config page when
    # the user is authenticated to reduce cross-site information leakage.
    if security_mod._is_authenticated() and not security_mod._verify_csrf_header():
        referer = _request_header("Referer")
        # Compute an "effective" scheme taking into account common proxies
        # that may not set X-Forwarded-Proto but do set Cloudflare headers.
        effective_scheme = None
        try:
            xf_proto = _request_header("X-Forwarded-Proto")
            if xf_proto:
                effective_scheme = xf_proto.split(",", 1)[0].strip()
            else:
                cf_visitor = _request_header("Cf-Visitor")
                if cf_visitor:
                    try:
                        import json as _json

                        cfv = _json.loads(cf_visitor)
                        effective_scheme = str(cfv.get("scheme")) if cfv.get("scheme") else None
                    except Exception:
                        effective_scheme = None
        except Exception:
            effective_scheme = None

        if not effective_scheme:
            try:
                effective_scheme = request.scheme
            except Exception:
                effective_scheme = "http"

        effective_host_url = f"{effective_scheme}://{request.host}/"

        # Parse the Referer and compare host:port (netloc) with the request host.
        try:
            from urllib.parse import urlparse

            parsed = urlparse(referer or "")
            referer_netloc = parsed.netloc
        except Exception:
            referer_netloc = ""

        # Accept same-origin when referer host matches request.host
        if referer_netloc != request.host:
            # Log diagnostic info to help debug reverse-proxy header mismatches
            console.print(f"[yellow]CSRF check failed for /config: host_url={effective_host_url}, Referer={referer}")
            # Return a helpful error including the observed host_url and referer
            return (
                jsonify(
                    {
                        "error": "CSRF token missing or invalid",
                        "success": False,
                        "debug": {"host_url": effective_host_url, "referer": referer, "request_host": request.host},
                    }
                ),
                403,
            )

    try:
        return render_template(
            "config.html",
            app_version=APP_VERSION,
            csrf_token=_ensure_csrf_token(),
        )
    except Exception as e:
        console.print(f"Error loading config template: {e}", markup=False)
        console.print(traceback.format_exc(), markup=False)
        return "<pre>Internal server error</pre>", 500


@bp.route("/stats")
def stats_page():
    """Serve the privacy-preserving statistics dashboard."""
    if not security_mod._is_authenticated():
        return redirect(url_for("pages.login_page"))
    return render_template("stats.html", app_version=APP_VERSION, csrf_token=_ensure_csrf_token())


@bp.route("/history")
def history_page():
    """Serve the local upload history."""
    if not security_mod._is_authenticated():
        return redirect(url_for("pages.login_page"))
    return render_template("history.html", app_version=APP_VERSION, csrf_token=_ensure_csrf_token())
