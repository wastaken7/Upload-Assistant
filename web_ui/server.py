"""Upload Assistant Web UI server."""

import contextlib
import importlib
import os
import sys
import traceback
from contextlib import suppress
from datetime import timedelta
from pathlib import Path
from typing import Any

from web_ui import context as context_mod
from web_ui import flask_compat as flask_compat_mod
from web_ui import security as security_mod
from web_ui.context import access_logger, console
from web_ui.extensions import limiter
from web_ui.flask_compat import CORS, Flask, Response, Session, g, get_remote_address, jsonify, redirect, request, url_for
from web_ui.paths import set_runtime_browse_roots
from web_ui.request_utils import _request_cookie_text, _request_form_text, _request_header
from web_ui.routes import account as routes_account
from web_ui.routes import browse as routes_browse
from web_ui.routes import config as routes_config
from web_ui.routes import history as routes_history
from web_ui.routes import pages as routes_pages
from web_ui.routes import review as routes_review
from web_ui.routes import sessions as routes_sessions
from web_ui.routes import system as routes_system
from web_ui.routes import trackers as routes_trackers
from web_ui.security import (
    _first_run_setup_code,
    _handle_failed_auth,
    _load_user_record,
    _readable_secret_files,
    _session_get,
    _verify_remember_token,
    _webui_auth_configured,
    session_secret,
)
from web_ui.session_state import set_execution_preview_target

# upload.py imports these from web_ui.server.
__all__ = ["app", "set_execution_preview_target", "set_runtime_browse_roots"]

sys.path.insert(0, str(Path(__file__).parent.parent))


def _parse_trusted_proxy_count(raw_value: str | None) -> int:
    """Parse the explicitly trusted number of reverse proxies."""
    value = (raw_value or "").strip()
    if not value:
        return 0
    try:
        count = int(value)
    except ValueError as exc:
        raise ValueError("UA_WEBUI_TRUSTED_PROXY_COUNT must be an integer from 0 to 10") from exc
    if count < 0 or count > 10:
        raise ValueError("UA_WEBUI_TRUSTED_PROXY_COUNT must be an integer from 0 to 10")
    return count


def _apply_proxy_fix(wsgi_app: object, trusted_proxy_count: int) -> object:
    """Trust forwarded host, scheme, and client IP only when configured."""
    if trusted_proxy_count == 0:
        return wsgi_app
    return flask_compat_mod.ProxyFix(
        wsgi_app,
        x_for=trusted_proxy_count,
        x_proto=trusted_proxy_count,
        x_host=trusted_proxy_count,
    )


app: Any = Flask(__name__)
trusted_proxy_count = _parse_trusted_proxy_count(os.environ.get("UA_WEBUI_TRUSTED_PROXY_COUNT"))
app.wsgi_app = _apply_proxy_fix(app.wsgi_app, trusted_proxy_count)
app.config["UA_WEBUI_TRUSTED_PROXY_COUNT"] = trusted_proxy_count
app.secret_key = session_secret
sess_dir = context_mod.cfg_dir / "sessions"
sess_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = False
# Ensure permanent sessions (when set) expire after 30 days to match remember-me cookie
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

# Prefer CacheLib's FileSystemCache when available. Set `SESSION_CACHELIB`
# to an instance of `FileSystemCache` so Flask-Session uses CacheLib's
# implementation and avoids the deprecated `SESSION_FILE_DIR` path.
_session_cache = None
try:
    FileSystemCache = importlib.import_module("cachelib.file").FileSystemCache

    with contextlib.suppress(Exception):
        _session_cache = FileSystemCache(str(sess_dir), mode=0o600)
except Exception:
    _session_cache = None

if _session_cache is not None:
    # Use CacheLib-backed cache for sessions (preferred)
    app.config["SESSION_CACHELIB"] = _session_cache
    try:
        CacheLibSessionInterface = importlib.import_module("flask_session.cachelib").CacheLibSessionInterface

        # Set the session interface directly to the CacheLib-backed implementation
        # Pass the cache as the `client` kwarg to avoid binding it to the
        # positional `app` parameter of the constructor.
        app.session_interface = CacheLibSessionInterface(client=_session_cache)
    except Exception:
        # If for some reason the adapter class isn't available, fall back
        # to letting Flask-Session initialize via Session(app).
        Session(app)
else:
    # Fallback for environments without CacheLib: keep legacy file-dir config
    app.config["SESSION_FILE_DIR"] = str(sess_dir)
    Session(app)

# Initialize Flask-Limiter for rate limiting
limiter.init_app(app)
CORS_fn = CORS


def _parse_cors_origins() -> list[str]:
    raw = os.environ.get("UA_WEBUI_CORS_ORIGINS", "").strip()
    if not raw:
        return []
    origins: list[str] = []
    for part in raw.split(","):
        part = part.strip()
        if part == "*":
            # Credentialed CORS for every origin would let any website read the
            # CSRF token and act as the signed-in user.
            raise ValueError("UA_WEBUI_CORS_ORIGINS must list explicit origins; '*' is not allowed")
        if part:
            origins.append(part)
    return origins


cors_origins = _parse_cors_origins()
if not cors_origins:
    # Cross-site callers are not configured, so keep browser sessions same-site.
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
if cors_origins:
    # Allow the CSRF header and support credentials so browser-based
    # cross-origin requests can send cookies for authenticated sessions.
    CORS_fn(
        app,
        resources={r"/api/*": {"origins": cors_origins}},
        allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
        supports_credentials=True,
    )


@app.before_request
def _require_auth_for_webui():  # pyright: ignore[reportUnusedFunction]
    """Enforce IP and authentication checks, recording rejected API credentials."""
    # Health endpoint can be used for orchestration checks.
    if request.path == "/api/health":
        return None

    # Check IP access control
    client_ip = get_remote_address()
    if not security_mod._is_ip_allowed(client_ip):
        # Log the blocked attempt
        if access_logger:
            with contextlib.suppress(AttributeError):
                access_logger.log(
                    endpoint=request.path,
                    method=request.method,
                    remote_addr=client_ip,
                    username=None,
                    success=False,
                    status=403,
                    headers={"User-Agent": _request_header("User-Agent")},
                    details="IP blocked",
                )
        return jsonify({"error": "Access denied", "success": False}), 403

    # Try to restore session from a long-lived remember-me cookie if present
    with contextlib.suppress(Exception):
        if not security_mod._is_authenticated():
            token = _request_cookie_text("ua_remember")
            if token:
                username = _verify_remember_token(token)
                if username:
                    # Only accept remember token if it matches the persisted user (if any)
                    persisted = _load_user_record()
                    if persisted:
                        stored = persisted.get("username")
                        if stored and username == stored:
                            g.authenticated = True
                            g.username = username
        # Any failure to validate the cookie should not block request flow; fallback to normal auth

    if request.path.startswith("/api/"):
        # For API, allow basic auth
        if security_mod._webui_auth_ok():
            return None
        # Or session auth
        if security_mod._is_authenticated():
            # Set username in g for logging if available
            with contextlib.suppress(Exception):
                username = str(_session_get("username") or "")
                if username:
                    g.username = username
            return None
        # If request accepts HTML (browser), redirect to login; else 401 for API clients
        if "text/html" in (_request_header("Accept") or ""):
            if _request_header("Authorization"):
                _handle_failed_auth(client_ip)
            return redirect(url_for("pages.login_page"))
        _handle_failed_auth(client_ip)
        return jsonify({"error": "Authentication required", "success": False}), 401

    # For web routes
    if security_mod._is_authenticated():
        # Set username in g for logging if available
        with contextlib.suppress(Exception):
            username = _session_get("username")
            if isinstance(username, str) and username:
                g.username = username
        return None
    if _webui_auth_configured() and security_mod._webui_auth_ok():
        return None
    if request.path in {"/config", "/stats", "/history", "/", "/index.html"}:
        return redirect(url_for("pages.login_page"))

    return None


@app.after_request
def _set_security_headers(response: Any) -> Any:  # pyright: ignore[reportUnusedFunction]
    """Apply browser hardening headers that do not affect embedding or proxies."""
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if request.path.startswith("/api/"):
        # API responses can contain configuration secrets and upload output.
        response.headers.setdefault("Cache-Control", "no-store")
    return response


_VERSIONED_STATIC_MAX_AGE = 365 * 24 * 60 * 60
_STATIC_IMAGE_MAX_AGE = 24 * 60 * 60


@app.url_defaults
def _version_static_urls(endpoint: str, values: dict[str, Any]) -> None:  # pyright: ignore[reportUnusedFunction]
    """Tag template asset URLs with the file's mtime so changed files get new URLs."""
    filename = values.get("filename")
    if endpoint != "static" or "v" in values or not isinstance(filename, str) or not app.static_folder:
        return
    with suppress(OSError):
        values["v"] = (Path(app.static_folder) / filename).stat().st_mtime_ns


@app.after_request
def _set_static_cache_headers(response: Any) -> Any:  # pyright: ignore[reportUnusedFunction]
    """Let browsers reuse static assets instead of revalidating each one per page load.

    Versioned URLs change with the file, so they can be cached long-term. Images
    and fonts referenced by fixed paths (tracker icons, CSS) are cached for a day.
    """
    if request.endpoint != "static" or response.status_code not in {200, 304}:
        return response
    if request.args.get("v"):
        max_age = _VERSIONED_STATIC_MAX_AGE
        response.cache_control.immutable = True
    elif request.path.startswith(("/static/img/", "/static/fonts/")):
        max_age = _STATIC_IMAGE_MAX_AGE
    else:
        return response
    response.cache_control.no_cache = None
    response.cache_control.public = True
    response.cache_control.max_age = max_age
    return response


@app.after_request
def _maybe_log_api_access(response: object) -> object:
    """Log API access attempts according to configured level.

    By default only non-successful API attempts are logged (level: access_denied).
    When level=access all accesses are logged.
    When level=disabled no logging occurs.
    """
    with contextlib.suppress(Exception):
        if access_logger is None:
            return response

        path = request.path or ""
        if not path.startswith("/api/"):
            return response

        status = getattr(response, "status_code", 500)
        success = 200 <= int(status) < 300
        if not access_logger.should_log(success):
            return response

        # Determine username if available
        user: str | None = None
        try:
            # First try authenticated user
            user_value = getattr(g, "username", None) or _session_get("username")
            user = user_value if isinstance(user_value, str) else None

            # For failed auth attempts, try to extract attempted username
            if user is None and not success:
                # Check Basic auth
                if request.authorization is not None and request.authorization.username:
                    user = f"{request.authorization.username} (basic auth)"
                # Check form data (login attempts)
                elif request.method == "POST" and _request_form_text("username"):
                    user = f"{_request_form_text('username')} (login attempt)"
                # Check Bearer token (even if invalid, might give us a hint)
                elif _request_header("Authorization").startswith("Bearer "):
                    user = "bearer token attempt"
        except Exception:
            user = None

        # Minimal headers for context
        headers = dict(request.headers.items()) if request.headers else None

        remote_value = request.remote_addr or request.environ.get("REMOTE_ADDR")
        remote = remote_value if isinstance(remote_value, str) else None

        access_logger.log(
            endpoint=path,
            method=request.method,
            remote_addr=remote,
            username=user,
            success=success,
            status=int(status),
            headers=headers,
            details=None,
        )
    return response


@app.errorhandler(429)
def _rate_limit_exceeded(_e: Exception) -> Any:
    # API callers expect JSON; keep non-API responses lightweight as well.
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "Too many requests. Please wait before trying again."}), 429
    return Response("Too many requests", status=429, mimetype="text/plain")


@app.errorhandler(404)
def not_found(_e: Exception):
    return jsonify({"error": "Not found", "success": False}), 404


@app.errorhandler(500)
def internal_error(e: Exception):
    console.print(f"500 error: {e!s}", markup=False)
    console.print(traceback.format_exc(), markup=False)
    return jsonify({"error": "Internal server error", "success": False}), 500


for _blueprint in (
    routes_pages.bp,
    routes_account.bp,
    routes_system.bp,
    routes_history.bp,
    routes_config.bp,
    routes_trackers.bp,
    routes_browse.bp,
    routes_review.bp,
    routes_sessions.bp,
):
    app.register_blueprint(_blueprint)


# Startup notices: shared seedboxes expose group/world-readable credentials to
# other accounts, and a first-run WebUI needs the console-only setup code.
with contextlib.suppress(Exception):
    _exposed_secret_files = _readable_secret_files()
    if _exposed_secret_files:
        console.print(
            "Warning: these credential files are readable by other users on this system: "
            + ", ".join(str(path) for path in _exposed_secret_files)
            + ". Restrict them with 'chmod 600 <file>' (or 'chmod 700' on their directory).",
            markup=False,
        )
with contextlib.suppress(Exception):
    if _load_user_record() is None:
        _first_run_setup_code()


# Keep these helpers referenced so static analysis does not flag them as unused.
_ = _maybe_log_api_access
_ = _rate_limit_exceeded
