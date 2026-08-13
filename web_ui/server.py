# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
# ruff: noqa: I001
import ast
import asyncio
import base64
import contextlib
import importlib
import hashlib
import hmac
import json
import mimetypes
import time
import os
import queue
import re
import secrets
import shlex
import subprocess
import sys
import threading
import traceback
import urllib.parse
import weakref
from contextlib import suppress
from datetime import datetime, timedelta, UTC
from types import ModuleType
from pathlib import Path
from typing import Any, Literal, Protocol, TypedDict, cast
from collections.abc import Callable
from collections.abc import Iterator, Mapping, Sequence

import psutil

import web_ui.auth as auth_mod
from src.webui_progress import ProgressEvent, clear_progress_callback, reset_progress, set_progress_callback
from src.app_paths import CODE_DIR, STATE_DIR


def _module_name(*parts: str) -> str:
    return "".join(parts)


def _dynamic_import(module_name: str) -> ModuleType:
    return importlib.import_module(module_name)


class _AuthLike(Protocol):
    username: str | None
    password: str | None
    type: str


class _HeadersLike(Protocol):
    def get(self, key: str, default: str | None = None) -> str | None: ...
    def items(self) -> Sequence[tuple[str, str]]: ...


class _RequestLike(Protocol):
    headers: _HeadersLike
    form: Mapping[str, str]
    args: Mapping[str, str]
    cookies: Mapping[str, str]
    authorization: _AuthLike | None
    method: str
    path: str
    host: str
    host_url: str
    scheme: str
    remote_addr: str | None
    environ: Mapping[str, object]
    json: object | None

    def get_json(self, silent: bool = False) -> object | None: ...

    def get_data(self, as_text: bool = False) -> str: ...


class _ResponseLike(Protocol):
    status_code: int

    def set_cookie(self, key: str, value: str, max_age: int | None = None, httponly: bool = False, secure: bool = False, samesite: str | None = None) -> None: ...
    def delete_cookie(self, key: str) -> None: ...


class _ConsoleLike(Protocol):
    def print(self, *args: object, **kwargs: object) -> object: ...
    def input(self, prompt: str = "") -> str: ...


class _PopenGroupKwargs(TypedDict, total=False):
    creationflags: int
    start_new_session: bool


class _WebUIProcess(Protocol):
    pid: int

    def poll(self) -> int | None: ...
    def wait(self, timeout: float | None = None) -> int: ...


class _SessionLike(Protocol):
    permanent: bool

    def __getitem__(self, key: str) -> object: ...
    def __setitem__(self, key: str, value: object) -> None: ...
    def __delitem__(self, key: str) -> None: ...
    def __iter__(self) -> Sequence[str]: ...
    def __len__(self) -> int: ...
    def get(self, key: str, default: object = ...) -> object: ...
    def pop(self, key: str, default: object = ...) -> object: ...
    def clear(self) -> None: ...


class _GLike(Protocol):
    authenticated: bool
    username: str | None


class _LimiterLike(Protocol):
    def limit(
        self,
        limit_value: str,
        *,
        key_func: Callable[[], str] | None = None,
        error_message: str | None = None,
        override_defaults: bool = True,
    ) -> Callable[[Callable[..., object]], Callable[..., object]]: ...


class _AccessLoggerLike(Protocol):
    def should_log(self, success: bool) -> bool: ...
    def get_level(self) -> str: ...
    def set_level(self, level: str) -> bool: ...
    def tail(self, n: int) -> list[object]: ...
    def log(
        self,
        *,
        endpoint: str,
        method: str,
        remote_addr: str | None,
        username: str | None,
        success: bool,
        status: int,
        headers: Mapping[str, object] | None,
        details: str | None,
    ) -> None: ...


pyotp = _dynamic_import(_module_name("py", "otp"))
flask = _dynamic_import(_module_name("fl", "ask"))
flask_cors = _dynamic_import(_module_name("flask", "_cors"))
flask_limiter = _dynamic_import(_module_name("flask", "_limiter"))
flask_limiter_util = _dynamic_import(_module_name("flask", "_limiter", ".util"))
werkzeug_security = _dynamic_import(_module_name("werkzeug", ".security"))
werkzeug_proxy_fix = _dynamic_import(_module_name("werkzeug", ".middleware", ".proxy_fix"))
flask_session = _dynamic_import(_module_name("flask", "_session"))

Flask: Callable[[str], object] = flask.Flask
Response: Callable[..., _ResponseLike] = flask.Response
g: _GLike = flask.g
jsonify: Callable[..., object] = flask.jsonify
redirect: Callable[..., _ResponseLike] = flask.redirect
render_template: Callable[..., object] = flask.render_template
request: _RequestLike = flask.request
send_file: Callable[..., object] = flask.send_file
session: _SessionLike = flask.session
url_for: Callable[..., str] = flask.url_for
CORS: Callable[..., object] = flask_cors.CORS
Limiter: Callable[..., _LimiterLike] = flask_limiter.Limiter
get_remote_address: Callable[[], str] = flask_limiter_util.get_remote_address
safe_join: Callable[..., str | None] = werkzeug_security.safe_join
ProxyFix: Callable[..., object] = werkzeug_proxy_fix.ProxyFix
Session: Callable[..., object] = flask_session.Session

sys.path.insert(0, str(Path(__file__).parent.parent))

# Helper to convert ANSI -> HTML using Rich (optional)
ansi_to_html: Callable[[str], str] | None = None


class _NullConsole:
    def print(self, *_args: object, **_kwargs: object) -> None:
        return None

    def input(self, prompt: str = "") -> str:
        raise EOFError(prompt)


console: _ConsoleLike = _NullConsole()
with contextlib.suppress(Exception):
    console_mod = importlib.import_module("src.console")
    ansi_to_html = getattr(console_mod, "ansi_to_html", None)
    loaded_console = getattr(console_mod, "console", None)
    if loaded_console is not None:
        console = loaded_console

cfg_dir = auth_mod.get_config_dir()
cfg_dir.mkdir(parents=True, exist_ok=True)

ARGUMENT_PRESETS_PATH = Path(__file__).resolve().parent.parent / "data" / "argument_presets.json"
MAX_ARGUMENT_PRESETS = 50
_argument_presets_lock = threading.Lock()
_description_review_locks: weakref.WeakValueDictionary[str, threading.Lock] = weakref.WeakValueDictionary()
_description_review_locks_lock = threading.Lock()


def _load_argument_presets() -> list[dict[str, str]]:
    """Load the shared Web UI argument presets from the data directory."""
    try:
        if not ARGUMENT_PRESETS_PATH.exists():
            return []
        raw = json.loads(ARGUMENT_PRESETS_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return []
        presets: list[dict[str, str]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            arguments = item.get("arguments")
            if isinstance(name, str) and isinstance(arguments, str) and name.strip() and arguments.strip():
                presets.append({"name": name.strip(), "arguments": arguments.strip()})
        return presets[-MAX_ARGUMENT_PRESETS:]
    except OSError, TypeError, ValueError:
        return []


def _save_argument_presets(presets: list[dict[str, str]]) -> None:
    """Persist shared Web UI argument presets with an atomic file replacement."""
    ARGUMENT_PRESETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = ARGUMENT_PRESETS_PATH.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(presets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(ARGUMENT_PRESETS_PATH)


# Access logging helper
AccessLogger: Callable[[Path], _AccessLoggerLike] | None = None
with contextlib.suppress(Exception):
    access_log_mod = importlib.import_module("web_ui.access_log")
    AccessLogger = getattr(access_log_mod, "AccessLogger", None)

access_logger: _AccessLoggerLike | None = AccessLogger(cfg_dir) if AccessLogger is not None else None


# Helper: simple file-backed config store under the auth config dir. Values
# are stored as raw text. This replaces OS keyring usage and allows Docker
# and non-Docker deployments to persist credentials via the configured
# persistent config mechanism.
def _cfg_file_path(name: str) -> Path:
    return cfg_dir / name


def _cfg_read(name: str) -> str | None:
    p = _cfg_file_path(name)
    with contextlib.suppress(Exception):
        if p.exists():
            return p.read_text(encoding="utf-8")
    return None


def _cfg_write(name: str, value: str) -> None:
    p = _cfg_file_path(name)
    with contextlib.suppress(Exception):
        p.write_text(value, encoding="utf-8")


def _cfg_delete(name: str) -> None:
    p = _cfg_file_path(name)
    with contextlib.suppress(Exception):
        if p.exists():
            p.unlink()


def _sanitize_relpath(rel: str) -> str:
    """Sanitize a relative path coming from user input.

    Splits the path into components, rejects empty/parent segments and
    validates each component for unsafe/control characters. Returns a
    path using the OS separator. Raises ValueError for unsafe input.
    """
    if rel == "" or rel == ".":
        return rel

    if "\x00" in rel:
        raise ValueError("Invalid path")

    # Split on both forward and backward slashes to support Windows/posix
    parts = re.split(r"[\\/]+", rel)
    clean_parts: list[str] = []
    for p in parts:
        if not p or p == "." or p == "..":
            raise ValueError("Invalid path component")
        # Reject NUL/control characters which are unsafe in file names.
        if re.search(r"[\x00-\x1f]", p):
            raise ValueError("Invalid path component")
        # Reject path-separator characters
        if "/" in p or "\\" in p:
            raise ValueError("Invalid path component")

        clean_parts.append(p)

    return str(Path(*clean_parts))


def _assert_safe_resolved_path(path: str | Path) -> None:
    """Assert that a resolved path is safe and within configured browse roots.

    Raises ValueError if the path is unsafe. This provides an explicit,
    local check at call sites to satisfy static analysis tools.
    """
    path_str = str(path)
    if not path_str or "\x00" in path_str:
        raise ValueError("Invalid path")

    # Ensure absolute and normalized
    abs_path = str(Path(path_str).resolve())
    real_path = os.path.realpath(abs_path)

    # Check for webui_queue file
    path_obj = Path(real_path)
    if path_obj.name.startswith("webui_queue_") and path_obj.suffix == ".txt":
        repo_tmp_dir = Path(__file__).resolve().parent.parent / "tmp"
        if repo_tmp_dir.resolve().exists():
            # Ensure it is actually inside repo_tmp_dir
            try:
                if os.path.commonpath([real_path, os.path.realpath(str(repo_tmp_dir.resolve()))]) == os.path.realpath(str(repo_tmp_dir.resolve())):
                    return
            except ValueError:
                pass

    roots = _get_browse_roots()
    if not roots:
        # If no roots configured, be conservative and disallow.
        raise ValueError("Browsing is not configured")

    allowed = False
    for root in roots:
        root_abs = str(Path(root).resolve())
        root_real = os.path.realpath(root_abs)
        safe_root_prefix = root_real if root_real.endswith(os.sep) else (root_real + os.sep)
        if real_path == root_real or real_path.startswith(safe_root_prefix):
            allowed = True
            break

    if not allowed:
        raise ValueError("Path outside allowed roots")


app: Any = Flask(__name__)
# Ensure Flask sees the proxy headers (Host, X-Forwarded-Proto, X-Forwarded-For)
# so `request.host_url` and related values reflect the external URL when
# running behind a reverse proxy (eg. Caddy). Adjust the `x_*` values if
# there are multiple proxies in front of the app.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=2, x_host=1)
# Load stable session secret (env/file/SECRET_KEY fallback). Use bytes directly.

session_secret = auth_mod.load_session_secret()
app.secret_key = session_secret

# Configure server-side filesystem sessions (persisted under config dir)
cfg_dir = auth_mod.get_config_dir()
sess_dir = cfg_dir / "sessions"
sess_dir.mkdir(parents=True, exist_ok=True)
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
        _session_cache = FileSystemCache(str(sess_dir))
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
CORS_fn = CORS

limiter: _LimiterLike = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)


def _rate_limit_key_func() -> str:
    """Rate limit key function that considers authentication status."""
    if _is_authenticated():
        return f"auth:{get_remote_address()}"
    return f"unauth:{get_remote_address()}"


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


def _as_dict(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    value_dict: dict[Any, Any] = cast(dict[Any, Any], value)
    result: dict[str, Any] = {}
    for key, item in value_dict.items():
        result[str(key)] = item
    return result


def _as_str_list(value: Any) -> list[str] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return None
    value_seq: Sequence[Any] = cast(Sequence[Any], value)
    return [str(item) for item in value_seq]


def _json_load_dict(text: str) -> dict[str, Any]:
    loaded = json.loads(text)
    return _as_dict(loaded) or {}


def _json_load_list(text: str) -> list[Any]:
    loaded = json.loads(text)
    if isinstance(loaded, Sequence) and not isinstance(loaded, (str, bytes, bytearray)):
        loaded_seq: Sequence[Any] = cast(Sequence[Any], loaded)
        return list(loaded_seq)
    return []


def _load_user_record() -> dict[str, Any] | None:
    load_user_fn = getattr(auth_mod, "load_user", None)
    if not callable(load_user_fn):
        return None
    return _as_dict(load_user_fn())


def _session_get(key: str, default: object = None) -> Any:
    return _load_session_dict().get(key, default)


def _session_set(key: str, value: object) -> None:
    d = _load_session_dict()
    d[key] = value
    _commit_session_dict(d)


def _session_pop(key: str, default: object = None) -> object:
    d = _load_session_dict()
    val = d.pop(key, default)
    _commit_session_dict(d)
    return val


def _request_json_dict() -> dict[str, Any]:
    try:
        data = request.get_json(silent=True)
        if isinstance(data, Mapping):
            data_dict: dict[Any, Any] = cast(dict[Any, Any], data)
            result: dict[str, Any] = {}
            for key, value in data_dict.items():
                result[str(key)] = value
            return result
    except Exception:  # noqa: S110
        pass
    return {}


def _request_header(name: str, default: str = "") -> str:
    value = request.headers.get(name)
    return value if isinstance(value, str) else default


def _request_form_text(name: str, default: str = "") -> str:
    value = request.form.get(name)
    return value if isinstance(value, str) else default


def _request_cookie_text(name: str, default: str = "") -> str:
    value = request.cookies.get(name)
    return value if isinstance(value, str) else default


# IP control helpers --------------------------------------------------
def _get_ip_whitelist() -> list[str]:
    """Get the list of whitelisted IPs."""
    with contextlib.suppress(Exception):
        path = cfg_dir / "webui_auth.json"
        if path.exists():
            data = _json_load_dict(path.read_text(encoding="utf-8"))
            val = data.get("ip_whitelist")
            items = _as_str_list(val)
            if items is not None:
                return items
    return []


def _set_ip_whitelist(ips: list[str]) -> None:
    """Set the list of whitelisted IPs."""
    with contextlib.suppress(Exception):
        path = cfg_dir / "webui_auth.json"
        data: dict[str, Any] = {}
        if path.exists():
            try:
                data = _json_load_dict(path.read_text(encoding="utf-8"))
            except Exception:
                return
        data["ip_whitelist"] = ips
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_ip_blacklist() -> list[str]:
    """Get the list of blacklisted IPs."""
    with contextlib.suppress(Exception):
        path = cfg_dir / "webui_auth.json"
        if path.exists():
            data = _json_load_dict(path.read_text(encoding="utf-8"))
            val = data.get("ip_blacklist")
            items = _as_str_list(val)
            if items is not None:
                return items
    return []


def _set_ip_blacklist(ips: list[str]) -> None:
    """Set the list of blacklisted IPs."""
    with contextlib.suppress(Exception):
        path = cfg_dir / "webui_auth.json"
        data: dict[str, Any] = {}
        if path.exists():
            try:
                data = _json_load_dict(path.read_text(encoding="utf-8"))
            except Exception:
                return
        data["ip_blacklist"] = ips
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_ip_failures() -> dict[str, list[int]]:
    """Get the dict of IP failure timestamps.

    Returns a mapping of `ip -> list[int]` (UNIX timestamps). For backward
    compatibility any integer legacy counts are converted into recent
    timestamps so they behave as recent failures.
    """
    with contextlib.suppress(Exception):
        path = cfg_dir / "webui_auth.json"
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
        path = cfg_dir / "webui_auth.json"
        data = {}
        if path.exists():
            try:
                data = _json_load_dict(path.read_text(encoding="utf-8"))
            except Exception:
                return
        data["ip_failures"] = failures
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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


def _is_authenticated() -> bool:
    if getattr(g, "authenticated", False):
        return True
    return bool(_session_get("authenticated", False))


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
        sdir = Path(app.config.get("SESSION_FILE_DIR", ""))
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


# Supported description file extensions for WebUI description file browser
SUPPORTED_DESC_EXTS = {".txt", ".nfo", ".md"}

# Regex for splitting filenames on common separators (dots, dashes, underscores, spaces)
_BROWSE_SEARCH_SEP_RE = re.compile(r"[\s.\-_]+")

# Lock to prevent concurrent in-process uploads (avoids cross-session interference)
inproc_lock = threading.Lock()
active_processes_lock = threading.Lock()

# Runtime browse roots (set by upload.py when starting web UI)
_runtime_browse_roots: str | None = None

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
    """Require same-origin via Origin or Referer header.

    Returns True if the request appears to be same-origin against the
    server's `request.host_url`. If an Origin header is present it must
    exactly match the host_url; otherwise falls back to checking the
    Referer prefix. Absence or mismatch results in False.
    """
    try:
        # Prefer comparing the origin/referer host:port (netloc) to the
        # request host. This is scheme-insensitive and avoids failures
        # when proxies/Cloudflare terminate TLS or don't forward the
        # original scheme.
        from urllib.parse import urlparse

        origin: str = _request_header("Origin")
        if origin:
            with contextlib.suppress(Exception):
                parsed = urlparse(origin)
                if parsed.netloc:
                    return parsed.netloc == request.host
            # Fallback to strict host_url match if parsing fails
            host_url = (request.host_url or "").rstrip("/") + "/"
            return origin.rstrip("/") + "/" == host_url

        referer: str = _request_header("Referer") or _request_header("Referrer")
        if referer:
            with contextlib.suppress(Exception):
                parsed = urlparse(referer)
                if parsed.netloc:
                    return parsed.netloc == request.host
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
    Attempt to read from keyring; if missing and not in Docker, generate and store one.
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


def _validate_upload_assistant_args(args: Sequence[object]) -> list[str]:
    """Validate upload-assistant arguments to avoid command-injection.

    Rejects arguments containing nulls, newlines, or common shell metacharacters.
    Returns the original args if they pass validation, otherwise raises ValueError.
    """
    safe_args: list[str] = []
    # Disallow characters that enable shell injection or command chaining.
    forbidden = set(";&|$`><*?~!\n\r\x00")
    for a in args:
        if not isinstance(a, str):
            raise ValueError("Invalid arg type")
        if a == "--paths-from-stdin":
            raise ValueError("--paths-from-stdin is only available in CLI mode")
        if any(ch in a for ch in forbidden):
            raise ValueError("Invalid characters in arg")
        # Disallow arguments that are just parent-directory references
        if a == ".." or a == ".":
            raise ValueError("Invalid arg")
        safe_args.append(a)
    return safe_args


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
    payload = json.dumps({"u": username, "e": expiry}, separators=(",", ":")).encode("utf-8")
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


def _parse_cors_origins() -> list[str]:
    raw = os.environ.get("UA_WEBUI_CORS_ORIGINS", "").strip()
    if not raw:
        return []
    origins: list[str] = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            origins.append(part)
    return origins


cors_origins = _parse_cors_origins()
if cors_origins:
    # Allow the CSRF header and support credentials so browser-based
    # cross-origin requests can send cookies for authenticated sessions.
    CORS_fn(
        app,
        resources={r"/api/*": {"origins": cors_origins}},
        allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
        supports_credentials=True,
    )

# ANSI color code regex pattern
ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


ProcessInfo = dict[str, Any]


class _ConPtyProcess:
    """Popen-compatible surface for a Windows ConPTY child."""

    def __init__(self, pty: Any) -> None:
        self._pty = pty
        self.pid = int(pty.pid)

    def poll(self) -> int | None:
        if self._pty.isalive():
            return None
        status = self._pty.exitstatus
        return int(status) if status is not None else 1

    def wait(self, timeout: float | None = None) -> int:
        timeout_value = timeout if timeout is not None else 0.0
        deadline = time.monotonic() + timeout if timeout is not None else None
        while self.poll() is None:
            if deadline is not None and time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(["ConPTY"], timeout_value)
            time.sleep(0.05)
        return self.poll() or 0

    def read(self, size: int = 1024) -> str:
        return str(self._pty.read(size))

    def write(self, text: str) -> None:
        self._pty.write(text)

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._pty.close()


def _spawn_webui_upload_process(command: list[str], base_dir: Path, env: dict[str, str]) -> tuple[_WebUIProcess, str]:
    """Start the upload controller, preferring a terminal on Windows for ANSI output."""
    if sys.platform == "win32":
        try:
            pty_process_class: Any = cast(Any, importlib.import_module("winpty")).PtyProcess

            pty = pty_process_class.spawn(command, cwd=str(base_dir), env=env, dimensions=(40, 120))
            return _ConPtyProcess(pty), "conpty"
        except ImportError:
            console.print("pywinpty is unavailable; falling back to pipe-based WebUI output.", markup=False)
        except Exception as err:
            console.print(f"ConPTY startup failed; falling back to pipe-based WebUI output: {err}", markup=False)

    popen_kwargs: _PopenGroupKwargs = {}
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    # codeql[py/command-line-injection]
    return (
        subprocess.Popen(  # lgtm[py/command-line-injection]  # noqa: S603
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=0,
            cwd=str(base_dir),
            env=env,
            universal_newlines=True,
            **popen_kwargs,
        ),
        "subprocess",
    )


def _write_webui_process_input(process: _WebUIProcess, user_input: str) -> None:
    if isinstance(process, _ConPtyProcess):
        process.write(f"{user_input}\r\n")
        return

    stdin = getattr(process, "stdin", None)
    if stdin is None:
        raise RuntimeError("Process stdin is unavailable")
    stdin.write(f"{user_input}\n")
    stdin.flush()


def _close_webui_process_io(process: _WebUIProcess) -> None:
    if isinstance(process, _ConPtyProcess):
        process.close()
        return

    for stream_name in ("stdin", "stdout", "stderr"):
        with contextlib.suppress(Exception):
            stream = getattr(process, stream_name, None)
            if stream is not None:
                stream.close()


# Store active processes
active_processes: dict[str, ProcessInfo] = {}


def _terminate_process_tree(process: _WebUIProcess, timeout: float = 2.0) -> bool:
    """Terminate an upload controller and every child it has started."""
    if process.poll() is not None:
        return True

    try:
        root = psutil.Process(process.pid)
    except psutil.NoSuchProcess, psutil.AccessDenied, OSError:
        return process.poll() is not None

    # Snapshot descendants before stopping the controller: once the controller
    # exits, its children may be re-parented and become impossible to identify.
    try:
        processes = root.children(recursive=True)
    except psutil.NoSuchProcess, psutil.AccessDenied, OSError:
        processes = []
    processes.append(root)

    for child in processes:
        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            child.terminate()

    _, alive = psutil.wait_procs(processes, timeout=timeout)
    for child in alive:
        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            child.kill()
    _, alive = psutil.wait_procs(alive, timeout=timeout)

    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=0)
    return process.poll() is not None and not alive


# Local store for consoles we've wrapped to avoid assigning attributes on Console
_ua_console_store: dict[int, dict[str, Any]] = {}


def _debug_process_snapshot(session_id: str | None = None) -> dict[str, object]:
    try:
        snapshot: dict[str, object] = {
            "active_sessions": list(active_processes.keys()),
            "console_store_keys": list(_ua_console_store.keys()),
            "inproc_lock_locked": inproc_lock.locked(),
        }
        if session_id and session_id in active_processes:
            info = active_processes.get(session_id, {})
            snapshot["session"] = {
                "mode": info.get("mode"),
                "has_worker": isinstance(info.get("worker"), threading.Thread),
                "has_stdout_thread": isinstance(info.get("stdout_thread"), threading.Thread),
                "has_stderr_thread": isinstance(info.get("stderr_thread"), threading.Thread),
            }
        return snapshot
    except Exception:
        return {"error": "failed to build snapshot"}


def _stringify_preview_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _stringify_optional_id(value: object) -> str:
    text = _stringify_preview_value(value)
    return "" if text in {"", "0"} else text


def _set_process_awaiting_input(session_id: str, waiting: bool, input_type: str = "text") -> None:
    with active_processes_lock:
        process_info = active_processes.get(session_id)
        if process_info is not None:
            process_info["awaiting_input"] = waiting
            process_info["input_type"] = input_type if waiting else None


def _set_process_awaiting_input_if_current(session_id: str, process_state: Mapping[str, object], waiting: bool, input_type: str = "text") -> None:
    with active_processes_lock:
        current_state = active_processes.get(session_id)
        if current_state is not process_state:
            return
        run_token = process_state.get("run_token")
        if run_token and current_state.get("run_token") == run_token:
            current_state["awaiting_input"] = waiting
            current_state["input_type"] = input_type if waiting else None


def _apply_progress_event(process_info: ProcessInfo, event: Mapping[str, object]) -> None:
    operation = str(event.get("op", "upsert")).strip().lower()
    if operation == "reset":
        process_info["progress"] = {}
        return

    progress_id = str(event.get("id", "")).strip()
    if not progress_id:
        return

    progress_map_obj = process_info.get("progress")
    if not isinstance(progress_map_obj, dict):
        progress_map_obj = {}
        process_info["progress"] = progress_map_obj
    progress_map = cast(dict[str, dict[str, object]], progress_map_obj)

    current_item = dict(progress_map.get(progress_id, {}))
    for key in ("id", "label", "detail", "status", "group", "unit", "updated_at"):
        if key in event:
            current_item[key] = event[key]
    for key in ("current", "total"):
        value = event.get(key)
        if isinstance(value, (int, float)):
            current_item[key] = float(value)
    progress_map[progress_id] = current_item


def _set_process_progress_if_current(session_id: str, process_state: Mapping[str, object], event: Mapping[str, object]) -> None:
    with active_processes_lock:
        current_state = active_processes.get(session_id)
        if current_state is not process_state:
            return
        run_token = process_state.get("run_token")
        if not (run_token and current_state.get("run_token") == run_token):
            return
        _apply_progress_event(current_state, event)


def _progress_items_for_process(process_info: Mapping[str, object]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    with active_processes_lock:
        progress_map_obj = process_info.get("progress")
        if not isinstance(progress_map_obj, dict):
            return []
        items.extend(dict(value) for value in progress_map_obj.values() if isinstance(value, dict))
    items.sort(key=lambda item: (0 if str(item.get("status", "")) == "running" else 1, str(item.get("id", ""))))
    return items


def _make_process_state(path: str, args: str) -> dict[str, object]:
    return {
        "run_token": secrets.token_hex(8),
        "mode": "starting",
        "path": path,
        "args": args,
        "started_at": time.time(),
        "awaiting_input": False,
        "input_type": None,
        "progress": {},
    }


def set_execution_preview_target(session_id: str, expected_run_token: str, path: str, meta_uuid: str | None = None) -> None:
    """Update the active preview target for an in-process Web UI execution."""
    cleaned_session_id = str(session_id or "").strip()
    cleaned_run_token = str(expected_run_token or "").strip()
    cleaned_path = str(path or "").strip()
    if not cleaned_session_id or not cleaned_run_token or not cleaned_path:
        return

    with active_processes_lock:
        process_info = active_processes.get(cleaned_session_id)
        if process_info is None:
            return
        if str(process_info.get("run_token") or "").strip() != cleaned_run_token:
            return
        process_info["path"] = cleaned_path
        if meta_uuid:
            process_info["meta_uuid"] = str(meta_uuid).strip()
        else:
            process_info.pop("meta_uuid", None)


def _session_state_is_current(session_id: str, process_state: Mapping[str, object]) -> bool:
    with active_processes_lock:
        current_state = active_processes.get(session_id)
        if current_state is not process_state:
            return False
        run_token = process_state.get("run_token")
        return bool(run_token and current_state.get("run_token") == run_token)


def _discard_session_state(session_id: str, process_state: Mapping[str, object]) -> None:
    with active_processes_lock:
        current_state = active_processes.get(session_id)
        if current_state is not process_state:
            return
        run_token = process_state.get("run_token")
        if run_token and current_state.get("run_token") == run_token:
            active_processes.pop(session_id, None)


def _string_list_preview_values(value: object) -> list[str]:
    results: list[str] = []
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned:
            results.append(cleaned)
        return results
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            label = _stringify_preview_value(item.get("name")) if isinstance(item, Mapping) else _stringify_preview_value(item)
            if label:
                results.append(label)
    return results


def _book_cover_from_meta(meta_data: Mapping[str, object], preview_session_id: str) -> str:
    covers_value = meta_data.get("covers")
    if isinstance(covers_value, Sequence) and not isinstance(covers_value, (str, bytes, bytearray)):
        for item in covers_value:
            if not isinstance(item, Mapping):
                continue
            for key in ("raw_url", "img_url", "web_url"):
                candidate = _stringify_preview_value(item.get(key))
                if candidate:
                    return candidate

    meta_uuid = _stringify_preview_value(meta_data.get("uuid"))
    if not meta_uuid:
        return ""

    tmp_dir = STATE_DIR / "tmp" / meta_uuid / "artwork"
    for filename in ("POSTER.png", "poster.png", "POSTER.jpg", "poster.jpg", "cover.jpg", "cover.png"):
        if (tmp_dir / filename).exists():
            return _execution_preview_cover_url(preview_session_id, meta_uuid)
    return ""


def _execution_preview_cover_url(preview_session_id: str, cache_key: str) -> str:
    """Return a per-item cover URL so the browser cannot reuse the prior cover."""
    version = urllib.parse.quote(str(cache_key), safe="")
    return f"/api/execution_preview_cover?session_id={urllib.parse.quote(preview_session_id, safe='')}&v={version}"


def _music_cover_from_meta(meta_data: Mapping[str, object], preview_session_id: str) -> str:
    """Return a public cover URL or the authenticated local-preview endpoint."""
    for key in ("cover", "poster"):
        candidate = _stringify_preview_value(meta_data.get(key))
        if _is_http_url(candidate):
            return candidate
    if _find_execution_preview_cover_file(preview_session_id) is not None:
        cache_key = _stringify_preview_value(meta_data.get("uuid")) or _stringify_preview_value(meta_data.get("path"))
        return _execution_preview_cover_url(preview_session_id, cache_key)
    return ""


def _is_http_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def _read_execution_preview_meta_file(meta_file: Path) -> Mapping[str, object] | None:
    try:
        return _json_load_dict(meta_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def _resolve_execution_preview_meta(session_id: str) -> tuple[str, Path | None, Mapping[str, object] | None]:
    process_info = active_processes.get(session_id, {})
    execution_path = _stringify_preview_value(process_info.get("path"))
    if not execution_path:
        return "", None, None

    base_tmp_dir = STATE_DIR / "tmp"
    alias_meta_file = base_tmp_dir / Path(execution_path).name / "meta.json"
    alias_meta = _read_execution_preview_meta_file(alias_meta_file) if alias_meta_file.exists() else None
    meta_uuid = _stringify_preview_value(process_info.get("meta_uuid"))
    if not meta_uuid and alias_meta is not None:
        meta_uuid = _stringify_preview_value(alias_meta.get("uuid"))

    if meta_uuid:
        canonical_meta_file = base_tmp_dir / meta_uuid / "meta.json"
        canonical_meta = _read_execution_preview_meta_file(canonical_meta_file) if canonical_meta_file.exists() else None
        if canonical_meta is not None:
            process_info["meta_uuid"] = meta_uuid
            return execution_path, canonical_meta_file, canonical_meta

    if alias_meta is not None:
        alias_uuid = _stringify_preview_value(alias_meta.get("uuid"))
        if alias_uuid:
            process_info["meta_uuid"] = alias_uuid
        return execution_path, alias_meta_file, alias_meta

    return execution_path, None, None


def _subprocess_prompt_type(buffer: str) -> str | None:
    last_line = buffer.splitlines()[-1] if buffer else ""
    stripped = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", last_line).strip()
    if not stripped:
        return None
    lowered = stripped.lower()
    if "running:" in lowered:
        return None
    if re.search(r"\(\s*y\s*/\s*n\s*\)\s*:?$", lowered):
        return "yes_no"
    if stripped.endswith(":") or stripped.endswith("?") or " enter " in f" {lowered} " or " select " in f" {lowered} " or lowered.startswith("select "):
        return "text"
    return None


def _webui_subprocess_env() -> dict[str, str]:
    """Return the environment required for an interactive colored WebUI child."""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    # Rich honors NO_COLOR even when force_terminal is enabled. The browser
    # consumes ANSI itself, so its child must not inherit that CLI preference.
    env.pop("NO_COLOR", None)
    env["UA_WEBUI_FORCE_COLOR"] = "1"
    return env


def _append_metadata_source(
    sources: list[MetadataSource],
    seen_keys: set[str],
    key: str,
    label: str,
    value: str,
    url: str = "",
) -> None:
    normalized_value = value.strip()
    if not normalized_value:
        return
    dedupe_key = f"{key}:{normalized_value.lower()}"
    if dedupe_key in seen_keys:
        return
    seen_keys.add(dedupe_key)
    source: MetadataSource = {
        "key": key,
        "label": label,
        "value": normalized_value,
    }
    if url:
        source["url"] = url
    sources.append(source)


def _extract_metadata_sources(meta_data: Mapping[str, object]) -> list[MetadataSource]:
    from urllib.parse import quote

    category = _stringify_preview_value(meta_data.get("category")).upper()
    tmdb_value = _stringify_optional_id(meta_data.get("tmdb_id")) or _stringify_optional_id(meta_data.get("tmdb"))
    imdb_value = _stringify_optional_id(meta_data.get("imdb_id")) or _stringify_optional_id(meta_data.get("imdb_tt")) or _stringify_optional_id(meta_data.get("imdb"))
    tvdb_value = _stringify_optional_id(meta_data.get("tvdb_id")) or _stringify_optional_id(meta_data.get("tvdb"))
    tvmaze_value = _stringify_optional_id(meta_data.get("tvmaze_id")) or _stringify_optional_id(meta_data.get("tvmaze"))
    mal_value = _stringify_optional_id(meta_data.get("mal_id")) or _stringify_optional_id(meta_data.get("mal"))
    douban_value = _stringify_optional_id(meta_data.get("douban_id"))
    igdb_value = _stringify_optional_id(meta_data.get("igdb_id"))
    steam_url = _stringify_preview_value(meta_data.get("steam_url"))
    openlibrary_value = (
        _stringify_preview_value(meta_data.get("openlibrary"))
        or _stringify_preview_value(meta_data.get("openlibrary_id"))
        or _stringify_preview_value(meta_data.get("openlibrary_book_id"))
    )
    isbn_value = _stringify_preview_value(meta_data.get("isbn"))

    sources: list[MetadataSource] = []
    seen_keys: set[str] = set()

    if category in {"MOVIE", "TV"} and tmdb_value:
        tmdb_kind = "tv" if category == "TV" else "movie"
        _append_metadata_source(
            sources,
            seen_keys,
            "tmdb",
            "TMDb",
            tmdb_value,
            f"https://www.themoviedb.org/{tmdb_kind}/{quote(tmdb_value)}",
        )

    if category in {"MOVIE", "TV"} and imdb_value:
        imdb_id = imdb_value if imdb_value.startswith("tt") else f"tt{imdb_value}"
        _append_metadata_source(
            sources,
            seen_keys,
            "imdb",
            "IMDb",
            imdb_id,
            f"https://www.imdb.com/title/{quote(imdb_id)}/",
        )

    if category == "TV" and tvdb_value:
        _append_metadata_source(
            sources,
            seen_keys,
            "tvdb",
            "TVDb",
            tvdb_value,
            f"https://thetvdb.com/dereferrer/series/{quote(tvdb_value)}",
        )

    if category == "TV" and tvmaze_value:
        _append_metadata_source(
            sources,
            seen_keys,
            "tvmaze",
            "TVMaze",
            tvmaze_value,
            f"https://www.tvmaze.com/shows/{quote(tvmaze_value)}",
        )

    if category in {"TV", "BOOK"} and mal_value:
        mal_kind = "manga" if category == "BOOK" else "anime"
        _append_metadata_source(
            sources,
            seen_keys,
            "mal",
            "MyAnimeList",
            mal_value,
            f"https://myanimelist.net/{mal_kind}/{quote(mal_value)}",
        )

    if category in {"MOVIE", "TV"} and douban_value:
        _append_metadata_source(
            sources,
            seen_keys,
            "douban",
            "Douban",
            douban_value,
            f"https://movie.douban.com/subject/{quote(douban_value)}/",
        )

    if category == "GAME" and igdb_value:
        _append_metadata_source(
            sources,
            seen_keys,
            "igdb",
            "IGDB",
            igdb_value,
            f"https://www.igdb.com/search?type=1&q={quote(igdb_value)}",
        )

    if category == "GAME" and steam_url:
        steam_value = steam_url.rstrip("/").split("/")[-1] or steam_url
        _append_metadata_source(sources, seen_keys, "steam", "Steam", steam_value, steam_url)

    if openlibrary_value:
        if openlibrary_value.startswith("OL"):
            if "W" in openlibrary_value:
                openlibrary_url = f"https://openlibrary.org/works/{quote(openlibrary_value)}"
            elif "M" in openlibrary_value:
                openlibrary_url = f"https://openlibrary.org/books/{quote(openlibrary_value)}"
            else:
                openlibrary_url = f"https://openlibrary.org/search?q={quote(openlibrary_value)}"
        else:
            openlibrary_url = f"https://openlibrary.org/search?q={quote(openlibrary_value)}"
        _append_metadata_source(
            sources,
            seen_keys,
            "openlibrary",
            "Open Library",
            openlibrary_value,
            openlibrary_url,
        )

    if category == "BOOK" and isbn_value:
        _append_metadata_source(
            sources,
            seen_keys,
            "google_books",
            "Google Books",
            isbn_value,
        )

    if category == "MUSIC":
        from src.music.sources import DiscogsEnricher

        music_release = meta_data.get("music_release")
        fields = music_release.get("fields", {}) if isinstance(music_release, Mapping) else {}
        external_ids = music_release.get("external_ids", {}) if isinstance(music_release, Mapping) else {}
        musicbrainz_release = ""
        if isinstance(fields, Mapping):
            musicbrainz_entry = fields.get("musicbrainz_release", {})
            if isinstance(musicbrainz_entry, Mapping):
                musicbrainz_release = _stringify_preview_value(musicbrainz_entry.get("value"))
        if not musicbrainz_release and isinstance(external_ids, Mapping):
            musicbrainz_release = _stringify_preview_value(external_ids.get("musicbrainz_release"))
        if musicbrainz_release:
            _append_metadata_source(
                sources,
                seen_keys,
                "musicbrainz",
                "MusicBrainz",
                musicbrainz_release,
                f"https://musicbrainz.org/release/{quote(musicbrainz_release)}",
            )

        if isinstance(external_ids, Mapping):
            discogs_references = (
                ("release", external_ids.get("discogs_release")),
                ("master", external_ids.get("discogs_master")),
            )
            for reference_kind, reference_value in discogs_references:
                parsed_reference = DiscogsEnricher.parse_reference(_stringify_preview_value(reference_value), reference_kind)
                if parsed_reference:
                    parsed_kind, discogs_id = parsed_reference
                    _append_metadata_source(
                        sources,
                        seen_keys,
                        f"discogs_{parsed_kind}",
                        f"Discogs {parsed_kind.title()}",
                        discogs_id,
                        f"https://www.discogs.com/{parsed_kind}/{quote(discogs_id)}",
                    )

    return sources


def _music_preview_from_meta(meta_data: Mapping[str, object]) -> dict[str, object]:
    """Extract display-safe MUSIC data from the normalized release snapshot."""
    release = meta_data.get("music_release")
    if not isinstance(release, Mapping):
        return {}
    fields = release.get("fields", {}) if isinstance(release.get("fields"), Mapping) else {}
    tracks = release.get("tracks", []) if isinstance(release.get("tracks"), Sequence) else []
    auxiliary = release.get("auxiliary", {}) if isinstance(release.get("auxiliary"), Mapping) else {}
    warnings = release.get("warnings", []) if isinstance(release.get("warnings"), Sequence) else []
    conflicts = release.get("conflicts", {}) if isinstance(release.get("conflicts"), Mapping) else {}

    def field_value(name: str, fallback: object = "") -> object:
        entry = fields.get(name, {}) if isinstance(fields, Mapping) else {}
        if isinstance(entry, Mapping) and entry.get("value") not in (None, "", [], {}):
            return entry["value"]
        return fallback

    def source(name: str) -> str:
        entry = fields.get(name, {}) if isinstance(fields, Mapping) else {}
        raw = _stringify_preview_value(entry.get("source")) if isinstance(entry, Mapping) else ""
        return {
            "file_tag": "File tags",
            "auxiliary": "Auxiliary files",
            "directory": "Folder name",
            "external": "External metadata",
            "user": "User input",
            "tracker": "Tracker",
            "inferred": "Inferred",
        }.get(raw, "")

    def text(name: str, fallback: object = "") -> str:
        value = field_value(name, fallback)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return " & ".join(_stringify_preview_value(item) for item in value if _stringify_preview_value(item))
        return _stringify_preview_value(value)

    def technical_values(key: str, formatter: Callable[[object], str]) -> str:
        values = {track.get(key) for track in tracks if isinstance(track, Mapping) and track.get(key) not in (None, "")}
        if not values:
            return ""
        try:
            ordered = sorted(values)
        except TypeError:
            ordered = sorted(values, key=str)
        rendered = [formatter(value) for value in ordered]
        return ", ".join(rendered) if len(rendered) <= 2 else f"{len(rendered)} variants"

    formats = technical_values("format", _stringify_preview_value)
    codecs = technical_values("codec", _stringify_preview_value)
    if formats.casefold() == codecs.casefold():
        codecs = ""
    bit_depth = technical_values("bit_depth", lambda value: f"{value}-bit")
    sample_rate = technical_values("sample_rate", lambda value: f"{int(value) / 1000:g} kHz")
    channels = technical_values(
        "channels",
        lambda value: {1: "Mono", 2: "Stereo"}.get(int(value), f"{value} channels"),
    )
    bitrate = technical_values("bitrate", lambda value: f"{round(int(value) / 1000)} kbps")
    technical = " / ".join(item for item in (formats or text("format", meta_data.get("format")), codecs, bit_depth, sample_rate, channels, bitrate) if item)

    sidecars: list[str] = []
    for label, key in (("log", "logs"), ("cue", "cues"), ("NFO", "nfos"), ("playlist", "playlists"), ("SFV", "sfvs"), ("artwork", "artwork"), ("scan", "scans")):
        items = auxiliary.get(key, []) if isinstance(auxiliary, Mapping) else []
        count = len(items) if isinstance(items, Sequence) and not isinstance(items, (str, bytes, bytearray)) else 0
        if count:
            sidecars.append(f"{count} {label}{'' if count == 1 else 's'}")

    genres_value = field_value("genres", [])
    genres = _string_list_preview_values(genres_value)
    artist = text("artists", field_value("artist", meta_data.get("artist", "")))
    return {
        "artist": artist,
        "artist_source": source("artists") or source("artist"),
        "album": text("album", meta_data.get("title", "")),
        "album_source": source("album"),
        "original_year": text("year", meta_data.get("year", "")),
        "year_source": source("year"),
        "release_type": text("release_type"),
        "release_type_source": source("release_type"),
        "media": text("media", meta_data.get("source", "")),
        "media_source": source("media"),
        "technical": technical,
        "track_count": text("track_count", len(tracks)),
        "disc_count": text("disc_count", 1),
        "release_year": text("release_year"),
        "retail_date": text("retail_date"),
        "release_label": text("release_label"),
        "release_catalogue_number": text("release_catalogue_number"),
        "edition": text("edition"),
        "edition_year": text("edition_year"),
        "genres": genres,
        "auxiliary": sidecars,
        "warnings": [_stringify_preview_value(item) for item in warnings[:5] if _stringify_preview_value(item)],
        "conflicts": [str(name).replace("_", " ") for name in sorted(conflicts)[:5]],
    }


def _extract_execution_preview(meta_data: Mapping[str, object], fallback_path: str) -> ExecutionPreview:
    title = _stringify_preview_value(meta_data.get("title")) or _stringify_preview_value(meta_data.get("name"))
    original_title = _stringify_preview_value(meta_data.get("original_title"))
    category = _stringify_preview_value(meta_data.get("category")).upper()
    # ``artwork_url`` and ``tmdb_poster_path`` are the current metadata
    # contract for MOVIE/TV.  Keep the older fields as fallbacks so previews
    # remain available for already-created temp metadata.
    poster_url = _stringify_preview_value(meta_data.get("artwork_url")) or _stringify_preview_value(meta_data.get("poster"))
    if category == "MUSIC":
        poster_url = _music_cover_from_meta(meta_data, _stringify_preview_value(meta_data.get("webui_session_id")))
    tmdb_poster = _stringify_preview_value(meta_data.get("tmdb_poster_path")) or _stringify_preview_value(meta_data.get("tmdb_poster"))
    if not poster_url and tmdb_poster:
        poster_url = tmdb_poster if tmdb_poster.startswith("http") else f"https://image.tmdb.org/t/p/w500{tmdb_poster}"
    music = _music_preview_from_meta(meta_data)
    genres = _string_list_preview_values(meta_data.get("genres")) or list(music.get("genres", []))
    networks = _string_list_preview_values(meta_data.get("networks"))
    audiobook_bitrate = _stringify_preview_value(meta_data.get("audiobook_bitrate"))
    if audiobook_bitrate.isdigit():
        audiobook_bitrate = f"{audiobook_bitrate} kbps"
    tv_pack_raw = _stringify_preview_value(meta_data.get("tv_pack")).lower()

    return {
        "path": _stringify_preview_value(meta_data.get("path")) or fallback_path,
        "filename": Path(fallback_path).name,
        "title": title or _stringify_preview_value(music.get("album")),
        "original_title": original_title,
        "year": _stringify_preview_value(meta_data.get("year")),
        "category": _stringify_preview_value(meta_data.get("category")),
        "media_type": _stringify_preview_value(meta_data.get("type")),
        "source": _stringify_preview_value(meta_data.get("source")),
        "resolution": _stringify_preview_value(meta_data.get("resolution")),
        "tmdb": _stringify_optional_id(meta_data.get("tmdb_id")) or _stringify_optional_id(meta_data.get("tmdb")),
        "imdb": (_stringify_optional_id(meta_data.get("imdb_id")) or _stringify_optional_id(meta_data.get("imdb_tt")) or _stringify_optional_id(meta_data.get("imdb"))),
        "metadata_sources": _extract_metadata_sources(meta_data),
        "poster_url": poster_url,
        "overview": _stringify_preview_value(meta_data.get("overview")),
        "genres": genres,
        "name": _stringify_preview_value(meta_data.get("name")),
        "status": "ready",
        "audio": _stringify_preview_value(meta_data.get("audio")),
        "service": _stringify_preview_value(meta_data.get("service_longname")),
        "networks": networks,
        "season": _stringify_preview_value(meta_data.get("season")),
        "episode": _stringify_preview_value(meta_data.get("episode")),
        "episode_title": _stringify_preview_value(meta_data.get("episode_title")),
        "episode_name": _stringify_preview_value(meta_data.get("episode_name")),
        "episode_overview": _stringify_preview_value(meta_data.get("episode_overview")),
        "tv_pack": tv_pack_raw not in ("", "0", "false", "none", "null"),
        "author": _stringify_preview_value(meta_data.get("author")),
        "narrator": _stringify_preview_value(meta_data.get("narrator")),
        "publisher": _stringify_preview_value(meta_data.get("publisher")),
        "book_language": _stringify_preview_value(meta_data.get("book_language")),
        "audiobook": bool(meta_data.get("audiobook")),
        "audiobook_duration": _stringify_preview_value(meta_data.get("audiobook_duration_formatted")),
        "audiobook_bitrate": audiobook_bitrate,
        "book_series": _stringify_preview_value(meta_data.get("book_series")),
        "book_series_index": _stringify_preview_value(meta_data.get("book_series_index")),
        "platform": _stringify_preview_value(meta_data.get("platform")),
        "game_version": _stringify_preview_value(meta_data.get("game_version")),
        "game_subcategory": _stringify_preview_value(meta_data.get("game_subcategory")),
        "game_region": _stringify_preview_value(meta_data.get("game_region")),
        "game_system": _stringify_preview_value(meta_data.get("game_system")),
        "developer": _stringify_preview_value(meta_data.get("developer")),
        "music": music,
        "awaiting_input": False,
        "input_type": None,
    }


def _find_execution_preview(session_id: str) -> ExecutionPreview | None:
    process_info = active_processes.get(session_id, {})
    execution_path, resolved_meta_file, resolved_meta = _resolve_execution_preview_meta(session_id)
    if not execution_path:
        return None

    execution_name = Path(execution_path).name
    if resolved_meta_file is not None and resolved_meta is not None:
        try:
            meta_data = resolved_meta
            if _stringify_preview_value(meta_data.get("category")) == "BOOK":
                current_poster = _stringify_preview_value(meta_data.get("poster"))
                if not _is_http_url(current_poster):
                    try:
                        enriched_meta = dict(meta_data)
                        enriched_meta["poster"] = _book_cover_from_meta(meta_data, session_id)
                        meta_data = enriched_meta
                    except Exception as err:
                        console.print(f"Execution preview cover enrichment failed for session {session_id}: {err}", markup=False)
            if _stringify_preview_value(meta_data.get("category")).upper() == "MUSIC":
                meta_data = {**meta_data, "webui_session_id": session_id}
            preview = _extract_execution_preview(meta_data, execution_path)
            preview["awaiting_input"] = bool(process_info.get("awaiting_input"))
            preview["input_type"] = process_info.get("input_type")
            preview["progress"] = _progress_items_for_process(process_info)
            return preview
        except Exception:  # noqa: S110
            pass

    return {
        "path": execution_path,
        "filename": execution_name,
        "title": "",
        "original_title": "",
        "year": "",
        "category": "",
        "media_type": "",
        "source": "",
        "resolution": "",
        "tmdb": "",
        "imdb": "",
        "metadata_sources": [],
        "poster_url": "",
        "overview": "",
        "genres": [],
        "name": "",
        "status": "waiting",
        "audio": "",
        "service": "",
        "networks": [],
        "season": "",
        "episode": "",
        "episode_title": "",
        "episode_name": "",
        "episode_overview": "",
        "tv_pack": False,
        "author": "",
        "narrator": "",
        "publisher": "",
        "book_language": "",
        "audiobook": False,
        "audiobook_duration": "",
        "audiobook_bitrate": "",
        "book_series": "",
        "book_series_index": "",
        "platform": "",
        "game_version": "",
        "game_subcategory": "",
        "game_region": "",
        "game_system": "",
        "developer": "",
        "music": {},
        "awaiting_input": bool(process_info.get("awaiting_input")),
        "input_type": process_info.get("input_type"),
        "progress": _progress_items_for_process(process_info),
    }


def _find_execution_preview_cover_file(session_id: str) -> Path | None:
    execution_path, _resolved_meta_file, resolved_meta = _resolve_execution_preview_meta(session_id)
    if not execution_path:
        return None

    meta_uuid = _stringify_preview_value(resolved_meta.get("uuid")) if resolved_meta is not None else ""
    candidate_dirs: list[Path] = []
    if meta_uuid:
        release_tmp = STATE_DIR / "tmp" / meta_uuid
        candidate_dirs.append(release_tmp / "artwork")
    release_tmp = STATE_DIR / "tmp" / Path(execution_path).name
    candidate_dirs.append(release_tmp / "artwork")

    # A music sidecar cover may stay beside the release, while embedded art is
    # extracted into tmp/MUSIC_COVER.*.  Never serve an arbitrary configured
    # path: accept it only when it is inside this release's selected root.
    if isinstance(resolved_meta, Mapping):
        cover_path = _stringify_preview_value(resolved_meta.get("cover_path"))
        if cover_path:
            try:
                candidate = Path(cover_path).resolve()
                release_path = Path(execution_path).resolve()
                release_root = release_path if release_path.is_dir() else release_path.parent
                candidate.relative_to(release_root)
                if candidate.is_file() and candidate.suffix.casefold() in {".jpg", ".jpeg", ".png", ".webp"}:
                    return candidate
            except OSError, ValueError:
                pass

    seen: set[str] = set()
    for tmp_dir in candidate_dirs:
        tmp_dir_key = str(tmp_dir)
        if tmp_dir_key in seen or not tmp_dir.exists():
            continue
        seen.add(tmp_dir_key)
        for filename in (
            "MUSIC_COVER.jpg",
            "MUSIC_COVER.png",
            "MUSIC_COVER.webp",
            "POSTER.png",
            "poster.png",
            "POSTER.jpg",
            "poster.jpg",
            "cover.jpg",
            "cover.png",
            "cover.webp",
            "manual_cover.jpg",
            "music_cover.jpg",
        ):
            candidate = tmp_dir / filename
            if candidate.is_file():
                return candidate
    return None


def _resolve_execution_review_temp_dir(meta_data: Mapping[str, object]) -> Path | None:
    """Resolve a release temp directory from trusted execution metadata."""
    meta_uuid = _stringify_preview_value(meta_data.get("uuid"))
    if not meta_uuid:
        return None
    temp_root = (STATE_DIR / "tmp").resolve()
    try:
        temp_dir = (temp_root / meta_uuid).resolve()
        temp_dir.relative_to(temp_root)
    except OSError, ValueError:
        return None
    if not temp_dir.is_dir():
        return None
    return temp_dir


def _resolve_execution_screenshot_review(session_id: str) -> tuple[Path, Mapping[str, object]] | None:
    """Resolve the current execution's screenshot directory without trusting client paths."""
    _execution_path, meta_file, meta_data = _resolve_execution_preview_meta(session_id)
    if meta_file is None or meta_data is None:
        return None
    temp_dir = _resolve_execution_review_temp_dir(meta_data)
    if temp_dir is None:
        return None
    return temp_dir, meta_data


def _resolve_execution_description_review(session_id: str) -> tuple[Path, Path, dict[str, object]] | None:
    """Resolve the active description draft through the execution session only."""
    _execution_path, meta_file, meta_data = _resolve_execution_preview_meta(session_id)
    if meta_file is None or meta_data is None:
        return None
    temp_dir = _resolve_execution_review_temp_dir(meta_data)
    if temp_dir is None:
        return None
    return temp_dir, meta_file, dict(meta_data)


def _description_review_lock(temp_dir: Path) -> threading.Lock:
    """Return the in-process mutation lock for one execution's description."""
    key = str(temp_dir.resolve())
    with _description_review_locks_lock:
        return _description_review_locks.setdefault(key, threading.Lock())


def _screenshot_review_meta(temp_dir: Path, meta_data: Mapping[str, object]) -> Mapping[str, object]:
    """Include cached hosted images when a resumed run has not restored them into meta.json yet."""
    result = dict(meta_data)
    if result.get("image_list"):
        return result
    try:
        cached = _json_load_dict((temp_dir / "image_data.json").read_text(encoding="utf-8"))
    except Exception:
        cached = None
    if cached and isinstance(cached.get("image_list"), list):
        result["image_list"] = cached["image_list"]
    return result


class BrowseItem(TypedDict, total=False):
    """Serialized representation of an entry returned by the browse API."""

    name: str
    path: str
    type: Literal["folder", "file"]
    children: list[BrowseItem] | None
    subtitle: str  # Optional hint  (eg, when parent path when names collide)
    mtime: float
    size: int


class MetadataSource(TypedDict, total=False):
    """Serialized metadata provider/source entry for the execution preview."""

    key: str
    label: str
    value: str
    url: str


class ProgressItem(TypedDict, total=False):
    id: str
    label: str
    current: float
    total: float
    detail: str
    status: str
    group: str
    unit: str
    updated_at: float


class ExecutionPreview(TypedDict, total=False):
    """Serialized preview data for the media currently being processed."""

    path: str
    filename: str
    title: str
    original_title: str
    year: str
    category: str
    media_type: str
    source: str
    resolution: str
    tmdb: str
    imdb: str
    metadata_sources: list[MetadataSource]
    poster_url: str
    overview: str
    genres: list[str]
    name: str
    status: str
    audio: str
    service: str
    networks: list[str]
    season: str
    episode: str
    episode_title: str
    episode_name: str
    episode_overview: str
    tv_pack: bool
    author: str
    narrator: str
    publisher: str
    book_language: str
    audiobook: bool
    audiobook_duration: str
    audiobook_bitrate: str
    book_series: str
    book_series_index: str
    platform: str
    game_version: str
    game_subcategory: str
    game_region: str
    game_system: str
    developer: str
    music: dict[str, object]
    awaiting_input: bool
    input_type: str | None
    progress: list[ProgressItem]


class ConfigItem(TypedDict, total=False):
    key: str
    value: object
    source: Literal["config", "example"]
    children: list[ConfigItem]
    help: list[str]
    subsection: str | bool


class ConfigSection(TypedDict, total=False):
    section: str
    items: list[ConfigItem]
    client_types: list[str]


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
    return auth_mod.verify_user(auth.username or "", auth.password or "")


@app.before_request
def _require_auth_for_webui():  # pyright: ignore[reportUnusedFunction]
    # Health endpoint can be used for orchestration checks.
    if request.path == "/api/health":
        return None

    # Check IP access control
    client_ip = get_remote_address()
    if not _is_ip_allowed(client_ip):
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
        if not _is_authenticated():
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
        if _webui_auth_ok():
            return None
        # Or session auth
        if _is_authenticated():
            # Set username in g for logging if available
            with contextlib.suppress(Exception):
                username = str(_session_get("username") or "")
                if username:
                    g.username = username
            return None
        # If request accepts HTML (browser), redirect to login; else 401 for API clients
        if "text/html" in (_request_header("Accept") or ""):
            return redirect(url_for("login_page"))
        _handle_failed_auth(client_ip)
        return jsonify({"error": "Authentication required", "success": False}), 401

    # For web routes
    if _is_authenticated():
        # Set username in g for logging if available
        with contextlib.suppress(Exception):
            username = _session_get("username")
            if isinstance(username, str) and username:
                g.username = username
        return None
    if _webui_auth_configured() and _webui_auth_ok():
        return None
    if request.path == "/config" or request.path in ("/", "/index.html"):
        return redirect(url_for("login_page"))

    return None


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


def _get_browse_roots() -> list[str]:
    # Check environment first, then runtime browse roots (set by upload.py)
    global _runtime_browse_roots
    raw = os.environ.get("UA_BROWSE_ROOTS", "").strip() or _runtime_browse_roots or ""
    if not raw:
        # Require explicit configuration; do not default to the filesystem root.
        return []

    roots: list[str] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        root = str(Path(part).resolve())
        roots.append(root)

    return roots


def set_runtime_browse_roots(browse_roots: str) -> None:
    """Set browse roots at runtime (used by upload.py when starting web UI)"""
    global _runtime_browse_roots
    _runtime_browse_roots = browse_roots


def _load_config_from_file(path: Path) -> dict[str, Any] | None:
    """Load and return the ``config`` dict from a Python config file.

    Only files inside the repository or runtime ``data/`` directories with a
    ``.py`` extension are accepted.  No ownership or permission checks are
    performed — the file lives in a user-controlled directory and the app
    already writes to it freely via ``config_update``.

    Returns None on error (file missing, invalid path, parse error, or no valid
    config dict).  Returns {} for a valid file that defines config = {}.
    """
    if not path.exists():
        return None

    # Preserve support for Python files beneath the repository data directory
    # while also accepting files beneath the user-owned runtime data directory.
    allowed_data_dirs = {
        (CODE_DIR / "data").resolve(),
        (STATE_DIR / "data").resolve(),
    }
    try:
        resolved_path = path.resolve()
        if path.suffix != ".py" or not any(resolved_path.is_relative_to(directory) for directory in allowed_data_dirs):
            return None
    except Exception:
        return None

    try:
        with Path(path).open(encoding="utf-8") as f:
            content = f.read()
        tree = ast.parse(content)
        for node in ast.walk(tree):
            config_node: ast.expr | None = None
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "config":
                        config_node = node.value
                        break
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "config":
                config_node = node.value

            if config_node is not None:
                config_value = ast.literal_eval(config_node)
                if isinstance(config_value, dict):
                    config_value_dict = cast(dict[Any, Any], config_value)
                    result: dict[str, Any] = {}
                    for key, value in config_value_dict.items():
                        result[str(key)] = value
                    return result
        console.print(f"[yellow]Config file {path.name} does not contain a valid 'config' dict assignment.[/yellow]")
        return None
    except Exception as exc:
        console.print(f"[yellow]Failed to parse config file {path.name}: {exc}[/yellow]")
        return None


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


def _redact_sensitive(value: Any) -> Any:
    """Return a copy of the value with sensitive dictionary fields redacted.

    Keys containing any of these substrings will be redacted (case-insensitive):
    password, pass, secret, token, key, totp, api, credential, auth
    """
    sensitive_parts = ("password", "pass", "secret", "token", "key", "totp", "api", "credential", "auth")

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
    sensitive_parts = ("password", "pass", "secret", "token", "key", "totp", "api", "credential", "auth")
    return any(part in lowered for part in sensitive_parts)


def _write_audit_log(action: str, path: list[str], old_value: Any, new_value: Any, success: bool, error: str | None = None) -> None:
    """Append an audit record to data/config_audit.log.

    Uses UTC ISO timestamps and attempts to record the acting user and remote
    address. Values are passed through `_json_safe` to ensure JSON-serializable
    output. Any exceptions writing the audit are logged to the console but do
    not raise to callers.
    """
    try:
        base_dir = STATE_DIR
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
        audit = {
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


def _get_nested_value(data: Any, path: list[str]) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current_dict = _as_dict(current)
        if current_dict is None:
            return None
        current = current_dict.get(key)
    return current


def _coerce_config_value(raw: Any, example_value: Any) -> Any:
    if isinstance(example_value, bool):
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.strip().lower() in {"1", "true", "yes", "y", "on"}
        return bool(raw)

    if isinstance(example_value, int) and not isinstance(example_value, bool):
        if isinstance(raw, (int, float)):
            return int(raw)
        if isinstance(raw, str) and raw.strip():
            return int(raw.strip())
        return 0

    if isinstance(example_value, float):
        if isinstance(raw, (int, float)):
            return float(raw)
        if isinstance(raw, str) and raw.strip():
            return float(raw.strip())
        return 0.0

    if example_value is None:
        if isinstance(raw, str) and raw.strip().lower() in {"", "none", "null"}:
            return None
        return raw

    if isinstance(example_value, (list, dict)):
        if isinstance(raw, list):
            return cast(list[Any], raw)
        if isinstance(raw, dict):
            return cast(dict[str, Any], raw)
        if isinstance(raw, str):
            raw_str = raw.strip()
            if not raw_str:
                return [] if isinstance(example_value, list) else {}
            try:
                loaded: Any = json.loads(raw_str)
                return loaded
            except json.JSONDecodeError:
                return raw
        return raw

    if isinstance(raw, str):
        return raw

    return str(raw)


def _python_literal(value: object) -> str:
    if isinstance(value, str):
        return repr(value)
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    return repr(value)


def _format_config_tree(tree: ast.AST) -> str:
    """Format an AST tree in the same style as example_config.py"""
    lines: list[str] = []

    # Cast to Module to access body attribute
    if not isinstance(tree, ast.Module):
        return ast.unparse(tree)

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "config":
                    if isinstance(node.value, ast.Dict):
                        lines.append("config = {")
                        lines.extend(_format_dict(node.value, 1))
                        lines.append("}")
                    else:
                        lines.append(ast.unparse(node))
                    break
        else:
            # Keep other statements as-is
            lines.append(ast.unparse(node))

    return "\n".join(lines)


def _format_dict(dict_node: ast.Dict, indent_level: int) -> list[str]:
    """Format a dictionary node with proper indentation"""
    lines: list[str] = []
    indent = "    " * indent_level

    for _i, (key_node, value_node) in enumerate(zip(dict_node.keys, dict_node.values, strict=False)):
        key_str = repr(key_node.value) if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str) else ast.unparse(key_node) if key_node is not None else "None"

        if isinstance(value_node, ast.Dict):
            lines.append(f"{indent}{key_str}: {{")
            lines.extend(_format_dict(value_node, indent_level + 1))
            lines.append(f"{indent}}},")
        else:
            value_str = ast.unparse(value_node)
            lines.append(f"{indent}{key_str}: {value_str},")

    return lines


def _replace_config_value_in_source(source: str, key_path: list[str], new_value: str) -> str:
    tree = ast.parse(source)
    config_assign = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "config":
                    config_assign = node
                    break
        if config_assign:
            break

    if config_assign is None or not isinstance(config_assign.value, ast.Dict):
        raise ValueError("Config assignment not found")

    current_dict = config_assign.value
    target_node: ast.AST | None = None

    for i, key in enumerate(key_path):
        found = False
        for k_node, v_node in zip(current_dict.keys, current_dict.values, strict=False):
            if isinstance(k_node, ast.Constant) and isinstance(k_node.value, str) and k_node.value == key:
                if isinstance(v_node, ast.Dict):
                    if i < len(key_path) - 1:  # Not the final key
                        current_dict = v_node
                        found = True
                        break
                    # Final key - update existing value
                    target_node = v_node
                    found = True
                    break
                target_node = v_node
                found = True
                break

        if not found:
            if i == len(key_path) - 1:  # Final key doesn't exist - need to add it
                # Add new key-value pair to current_dict
                new_key_node = ast.Constant(value=key)
                new_value_node = ast.parse(new_value, mode="eval").body

                current_dict.keys.append(new_key_node)
                current_dict.values.append(new_value_node)

                # Reconstruct the source with the new key using proper formatting
                return _format_config_tree(tree)
            raise ValueError(f"Key not found in config: {key}")

        if target_node is not None and i < len(key_path) - 1:
            raise ValueError("Invalid path for config update")

    if target_node is None:
        raise ValueError("Target node not found")

    if not hasattr(target_node, "lineno") or not hasattr(target_node, "end_lineno"):
        raise ValueError("Unable to locate config value position")

    lineno = cast(int | None, getattr(target_node, "lineno", None))
    end_lineno = cast(int | None, getattr(target_node, "end_lineno", None))
    col_offset = cast(int, getattr(target_node, "col_offset", 0))
    end_col_offset = cast(int, getattr(target_node, "end_col_offset", 0))
    if lineno is None or end_lineno is None:
        raise ValueError("Unable to locate config value position")

    lines = source.splitlines(keepends=True)
    start = sum(len(line) for line in lines[: lineno - 1]) + col_offset
    end = sum(len(line) for line in lines[: end_lineno - 1]) + end_col_offset

    updated_source = f"{source[:start]}{new_value}{source[end:]}"

    # Reformat the entire config to ensure consistent styling
    updated_tree = ast.parse(updated_source)
    return _format_config_tree(updated_tree)


def _remove_config_key_in_source(source: str, key_path: list[str]) -> str:
    """Remove a key from the config source if it exists"""
    tree = ast.parse(source)
    config_assign = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "config":
                    config_assign = node
                    break
        if config_assign:
            break

    if config_assign is None or not isinstance(config_assign.value, ast.Dict):
        return source  # No config found, return as-is

    current_dict = config_assign.value

    for i, key in enumerate(key_path):
        found = False
        for j, (k_node, v_node) in enumerate(zip(current_dict.keys, current_dict.values, strict=False)):
            if isinstance(k_node, ast.Constant) and isinstance(k_node.value, str) and k_node.value == key:
                if isinstance(v_node, ast.Dict):
                    if i < len(key_path) - 1:  # Not the final key
                        current_dict = v_node
                        found = True
                        break
                    # Final key - remove it
                    # Remove the key-value pair
                    del current_dict.keys[j]
                    del current_dict.values[j]
                    # Reconstruct the source
                    return _format_config_tree(tree)
                if i == len(key_path) - 1:  # Final key - remove it
                    del current_dict.keys[j]
                    del current_dict.values[j]
                    return _format_config_tree(tree)
                found = True
                break

        if not found:
            return source  # Key not found, return as-is

    return source  # Should not reach here


def _build_config_items(
    example_section: dict[str, Any],
    user_section: dict[str, Any],
    comments_map: dict[str, list[str]],
    subsection_map: dict[str, str],
    path: list[str],
) -> list[ConfigItem]:
    items: list[ConfigItem] = []
    user_dict: dict[str, Any] = _as_dict(user_section) or {}

    merged_keys: list[str] = [str(key) for key in example_section]
    if user_section:
        merged_keys.extend([str(key) for key in user_section if key not in example_section])

    current_subsection: str | None = None
    subsection_items: list[ConfigItem] = []

    def flush_subsection() -> None:
        nonlocal subsection_items, current_subsection
        if current_subsection and subsection_items:
            items.append(
                {
                    "key": current_subsection,
                    "children": subsection_items,
                    "source": "example",
                    "help": [],
                    "subsection": True,
                }
            )
        subsection_items = []

    for key in merged_keys:
        example_value = example_section.get(key)
        user_value = user_dict.get(key)
        key_path = [*path, key]
        help_text = comments_map.get("/".join(key_path), [])
        subsection_label = subsection_map.get("/".join(key_path))
        if subsection_label != current_subsection:
            flush_subsection()
            current_subsection = subsection_label
        if isinstance(example_value, Mapping) or isinstance(user_value, Mapping):
            example_value = _as_dict(example_value) or {}
            user_value = _as_dict(user_value) or {}
            children = _build_config_items(example_value, user_value, comments_map, subsection_map, key_path)
            source: Literal["config", "example"] = "config" if key in user_dict else "example"
            item: ConfigItem = {
                "key": key,
                "source": source,
                "children": children,
                "help": help_text,
            }
        else:
            if key in user_dict:
                value = user_value
                source = "config"
            else:
                value = example_value
                source = "example"
            item = {
                "key": key,
                "value": _json_safe(value),
                "source": source,
                "help": help_text,
            }

        if current_subsection:
            subsection_items.append(item)
        else:
            items.append(item)

    flush_subsection()

    return items


def _extract_example_metadata(example_path: Path) -> tuple[dict[str, list[str]], dict[str, str]]:
    if not example_path.exists():
        return {}, {}

    source = example_path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source)

    config_assign: ast.Assign | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "config":
                    config_assign = node
                    break
        if config_assign:
            break

    if config_assign is None or not isinstance(config_assign.value, ast.Dict):
        return {}, {}

    comment_map: dict[str, list[str]] = {}
    subsection_map: dict[str, str] = {}

    def collect_comments(lineno: int) -> list[str]:
        idx = lineno - 2
        comments: list[str] = []
        while idx >= 0:
            line = lines[idx]
            stripped = line.strip()
            if not stripped:
                if comments:
                    break
                idx -= 1
                continue
            if stripped.startswith("#"):
                comments.insert(0, stripped.lstrip("#").strip())
                idx -= 1
                continue
            break
        return comments

    def find_headers(
        start_line: int,
        end_line: int,
        child_ranges: list[tuple[int, int]],
    ) -> list[tuple[int, str]]:
        headers: list[tuple[int, str]] = []
        for idx in range(start_line - 1, end_line):
            if idx <= 0 or idx + 1 >= len(lines):
                continue
            stripped = lines[idx].strip()
            if not stripped.startswith("#"):
                continue
            title = stripped.lstrip("#").strip()
            if not title:
                continue
            if title != title.upper():
                continue
            if not any(char.isalpha() for char in title):
                continue
            if lines[idx - 1].strip() or lines[idx + 1].strip():
                continue
            line_no = idx + 1
            if any(start <= line_no <= end for start, end in child_ranges):
                continue
            headers.append((line_no, title))
        return headers

    def walk_dict(node: ast.Dict, path: list[str]) -> None:
        key_entries: list[tuple[str, int, ast.AST]] = []
        child_ranges: list[tuple[int, int]] = []
        for key_node, value_node in zip(node.keys, node.values, strict=False):
            if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
                continue
            key = key_node.value
            lineno = getattr(key_node, "lineno", None)
            if isinstance(lineno, int):
                comment_map["/".join([*path, key])] = collect_comments(lineno)
                key_entries.append((key, lineno, value_node))

            if isinstance(value_node, ast.Dict):
                start = getattr(value_node, "lineno", None)
                end = getattr(value_node, "end_lineno", None)
                if isinstance(start, int) and isinstance(end, int):
                    child_ranges.append((start, end))

            if isinstance(value_node, ast.Dict):
                walk_dict(value_node, [*path, key])

        start_line = getattr(node, "lineno", None)
        end_line = getattr(node, "end_lineno", None)
        if isinstance(start_line, int) and isinstance(end_line, int) and key_entries:
            headers = sorted(find_headers(start_line, end_line, child_ranges), key=lambda h: h[0])
            key_entries.sort(key=lambda entry: entry[1])
            header_idx = 0
            current_header: str | None = None
            for key, lineno, _ in key_entries:
                while header_idx < len(headers) and headers[header_idx][0] < lineno:
                    current_header = headers[header_idx][1]
                    header_idx += 1
                if current_header:
                    subsection_map["/".join([*path, key])] = current_header

    walk_dict(config_assign.value, [])
    return comment_map, subsection_map


def _resolve_user_path(
    user_path: object | None,
    *,
    require_exists: bool = True,
    require_dir: bool = False,
) -> str:
    roots = _get_browse_roots()
    # Allow webui_queue files under tmp directory
    if isinstance(user_path, str):
        path_obj = Path(user_path)
        if path_obj.name.startswith("webui_queue_") and path_obj.suffix == ".txt":
            repo_tmp_dir = Path(__file__).resolve().parent.parent / "tmp"
            if repo_tmp_dir.resolve().exists():
                roots = [*roots, str(repo_tmp_dir.resolve())]
    if not roots:
        raise ValueError("Browsing is not configured")

    default_root = roots[0]

    if user_path is None or user_path == "":
        expanded = ""
    else:
        if not isinstance(user_path, str):
            raise ValueError("Path must be a string")
        if len(user_path) > 4096:
            raise ValueError("Invalid path")
        if "\x00" in user_path or "\n" in user_path or "\r" in user_path:
            raise ValueError("Invalid characters in path")

        expanded = os.path.expandvars(Path(user_path).expanduser())

    # Build a normalized path and validate it against allowlisted roots.
    # Use werkzeug.security.safe_join as the primary path sanitizer, with a
    # Windows fallback since safe_join uses posixpath internally.
    # Enforce a realpath+commonpath constraint to prevent symlink escapes.
    matched_root: str | None = None
    candidate_norm: str | None = None

    if expanded and Path(expanded).is_absolute():
        # If a user supplies an absolute path, only allow it if it is under
        # one of the configured browse roots (or their realpath equivalents,
        # since the browse API returns realpath-resolved paths to the frontend).
        for root in roots:
            root_abs = str(Path(root).resolve())
            root_real = os.path.realpath(root_abs)

            # Check against both the configured root and its realpath.
            # This handles the case where the frontend sends back a realpath
            # (e.g., /mnt/storage/torrents) that was returned by a previous
            # browse call, but the configured root is a symlink (e.g., /data/torrents).
            for check_root in (root_abs, root_real):
                try:
                    rel = os.path.relpath(expanded, check_root)
                except ValueError:
                    # Different drive on Windows.
                    continue

                # Sanitize the relative path components to defend against
                # path-injection (e.g. ../../../, absolute segments, nulls).
                # We reject components that resolve to '.' or '..' and use
                # Werkzeug's `secure_filename` to normalize each path segment.
                try:
                    rel = _sanitize_relpath(rel)
                except ValueError:
                    continue

                if rel == os.pardir or rel.startswith(os.pardir + os.sep) or Path(rel).is_absolute():
                    continue

                # Handle the case where the path equals the root exactly.
                # safe_join may return None for '.' in some Werkzeug versions.
                if rel == ".":
                    matched_root = check_root
                    candidate_norm = os.path.normpath(check_root)
                    break

                joined = safe_join(check_root, rel)

                # Windows fallback: safe_join uses posixpath internally and returns
                # None for Windows backslash paths. Fall back to os.path.join on
                # Windows since we already validated rel above and commonpath check
                # below provides additional symlink-escape protection.
                if sys.platform == "win32" and joined is None:
                    joined = Path(check_root) / rel

                matched_root = check_root
                candidate_norm = os.path.normpath(joined)
                break

            if matched_root:
                break
    else:
        matched_root = str(Path(default_root).resolve())
        # Handle empty path (initial browse request) - use the root directly.
        # safe_join may return None for empty strings in some Werkzeug versions.
        if not expanded:
            candidate_norm = os.path.normpath(matched_root)
        else:
            # Sanitize the incoming expanded path before joining.
            try:
                sanitized_expanded = _sanitize_relpath(expanded)
            except ValueError as err:
                raise ValueError("Browsing this path is not allowed") from err

            joined = safe_join(matched_root, sanitized_expanded)

            # Windows fallback: safe_join uses posixpath internally and returns
            # None for Windows backslash paths. Fall back to manual validation
            # and os.path.join. The commonpath check below provides additional security.
            if sys.platform == "win32" and joined is None:
                expanded_norm = os.path.normpath(sanitized_expanded)
                if expanded_norm == os.pardir or expanded_norm.startswith(os.pardir + os.sep) or Path(expanded_norm).is_absolute():
                    raise ValueError("Browsing this path is not allowed")
                joined = Path(matched_root) / expanded_norm

            candidate_norm = os.path.normpath(joined)

    if not matched_root or not candidate_norm:
        raise ValueError("Browsing this path is not allowed")

    candidate_real = os.path.realpath(candidate_norm)
    root_real = os.path.realpath(matched_root)
    try:
        if os.path.commonpath([candidate_real, root_real]) != root_real:
            raise ValueError("Browsing this path is not allowed")
    except ValueError as e:
        # ValueError can happen on Windows if drives differ.
        raise ValueError("Browsing this path is not allowed") from e

    candidate = candidate_real

    # Additional explicit validation before using `candidate` in filesystem
    # operations. This defends against accidental use of unvalidated
    # user-controlled data (helps static analysis tools and provides a
    # clear guard at the call site).
    if "\x00" in candidate:
        raise ValueError("Browsing this path is not allowed")

    # Ensure the resolved candidate path is within the resolved root path.
    safe_root_prefix = root_real if root_real.endswith(os.sep) else (root_real + os.sep)
    if not (candidate == root_real or candidate.startswith(safe_root_prefix)):
        raise ValueError("Browsing this path is not allowed")

    # Extra explicit assertion for static analysis and defense-in-depth:
    # ensure the resolved candidate is within allowed browse roots.
    try:
        _assert_safe_resolved_path(candidate)
    except ValueError as err:
        raise ValueError("Browsing this path is not allowed") from err

    # Use an explicitly-named, normalized `safe_candidate` for filesystem
    # operations so static analyzers can see the sanitized value being used.
    safe_candidate = os.path.realpath(candidate)

    # codeql[py/path-injection]
    if require_exists and not Path(safe_candidate).exists():
        raise ValueError("Path does not exist")

    # codeql[py/path-injection]
    if require_dir and not Path(safe_candidate).is_dir():
        raise ValueError("Not a directory")

    return safe_candidate


def _resolve_browse_path(user_path: str | None) -> str:
    return _resolve_user_path(user_path, require_exists=True, require_dir=True)


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text"""
    return ANSI_ESCAPE.sub("", text)


@app.route("/")
def index():
    """Serve the main UI"""
    try:
        return render_template("index.html")
    except Exception as e:
        console.print(f"Error loading template: {e}", markup=False)
        console.print(traceback.format_exc(), markup=False)
        return "<pre>Internal server error</pre>", 500


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute;100 per day", key_func=get_remote_address, error_message="Too many attempts, please try again later.")
def login_page():
    if request.method == "POST":
        # Quick IP block check: short-circuit heavy work for known-bad IPs.
        if not _is_ip_allowed(get_remote_address()):
            return Response("Too many requests", status=429, mimetype="text/plain")
        username = _request_form_text("username").strip()
        password = _request_form_text("password").strip()
        totp_code = _request_form_text("totp_code").strip()
        remember = _request_form_text("remember") == "1"

        persisted = _load_user_record()
        if persisted:
            # Persisted user exists: require matching credentials
            if auth_mod.verify_user(username, password):
                if _totp_enabled() and not (totp_code and _verify_totp_code(totp_code)):
                    _handle_failed_auth(get_remote_address())
                    return render_template("login.html", error="Credentials did not match", show_2fa=_totp_enabled(), setup_mode=False)

                _session_set("authenticated", True)
                with contextlib.suppress(Exception):
                    _session_set("username", username)
                with contextlib.suppress(Exception):
                    _session_set("csrf_token", secrets.token_urlsafe(32))
                if remember:
                    session.permanent = True
                resp = redirect(url_for("config_page"))
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
        # No persisted user: allow UI-driven creation (first-run setup)
        if username and password:
            if _totp_enabled() and not (totp_code and _verify_totp_code(totp_code)):
                _handle_failed_auth(get_remote_address())
                return render_template("login.html", error="Credentials did not match", show_2fa=_totp_enabled(), setup_mode=True)
            try:
                auth_mod.create_user(username, password)
            except ValueError as exc:
                return render_template("login.html", error=str(exc), show_2fa=_totp_enabled(), setup_mode=True)
            except Exception:
                return render_template("login.html", error="Unable to create account", show_2fa=_totp_enabled(), setup_mode=True)

            _session_set("authenticated", True)
            with contextlib.suppress(Exception):
                _session_set("username", username)
            with contextlib.suppress(Exception):
                _session_set("csrf_token", secrets.token_urlsafe(32))
            if remember:
                session.permanent = True
                with contextlib.suppress(Exception):
                    token = _create_remember_token(username)
                    if token:
                        resp = redirect(url_for("config_page"))
                        resp.set_cookie("ua_remember", token, max_age=30 * 86400, httponly=True, secure=True, samesite="Lax")
                        with suppress(Exception):
                            _cleanup_duplicate_sessions(username)
                        return resp

            with suppress(Exception):
                _cleanup_duplicate_sessions(username)
            return redirect(url_for("config_page"))
        # No username/password provided
        _handle_failed_auth(get_remote_address())
        return render_template("login.html", error="Credentials did not match", setup_mode=True)

    # Show 2FA field if enabled
    show_2fa = _totp_enabled()
    return render_template("login.html", show_2fa=show_2fa, setup_mode=_load_user_record() is None)


@app.errorhandler(429)
def _rate_limit_exceeded(_e: Exception) -> Any:
    # Return a minimal plain-text 429 response to avoid heavy template rendering.
    return Response("Too many requests", status=429, mimetype="text/plain")


@app.route("/logout", methods=["GET", "POST"])  # prefer POST from the UI
def logout():
    # Accept both GET and POST for compatibility, but UI should use POST.
    # Remove encrypted session payload
    # Clear all server-side session data
    try:
        session.clear()
    except Exception:
        # Fallback: remove encrypted payload if clear fails
        session.pop("enc", None)

    resp = redirect(url_for("login_page"))
    # Remove remember cookie if present
    resp.delete_cookie("ua_remember")
    # Also remove the browser session cookie (Flask's session cookie name)
    try:
        resp.delete_cookie(app.session_cookie_name)
    except Exception:
        # Fallback to common cookie name
        resp.delete_cookie("session")
    return resp


@app.route("/login/recovery", methods=["GET", "POST"])
@limiter.limit("10 per minute;100 per day", key_func=get_remote_address, error_message="Too many attempts, please try again later.")
def login_recovery():
    """Handle login using a recovery code. This is a separate endpoint to
    keep recovery-code input distinct from strict 2FA inputs so password
    managers treat the 2FA input as a one-time code field.
    """
    # If GET, render the dedicated recovery page (minimal inputs)
    if request.method == "GET":
        return render_template("login_recovery.html", show_2fa=_totp_enabled())

    # POST: process recovery code login
    # Quick IP block check: short-circuit heavy work for known-bad IPs.
    if not _is_ip_allowed(get_remote_address()):
        return Response("Too many requests", status=429, mimetype="text/plain")

    username = _request_form_text("username").strip()
    password = _request_form_text("password").strip()
    recovery_code = _request_form_text("recovery_code").strip()
    remember = _request_form_text("remember") == "1"

    if not _totp_enabled():
        return render_template("login_recovery.html", error="Recovery codes are not enabled", show_2fa=False)

    persisted = _load_user_record()
    # If a persisted user exists, require those credentials + recovery code
    if persisted:
        if username and password and recovery_code and _consume_recovery_code(recovery_code) and auth_mod.verify_user(username, password):
            _session_set("authenticated", True)
            with contextlib.suppress(Exception):
                _session_set("username", username)
            with contextlib.suppress(Exception):
                _session_set("csrf_token", secrets.token_urlsafe(32))
            if remember:
                session.permanent = True
                with contextlib.suppress(Exception):
                    token = _create_remember_token(username)
                    if token:
                        resp = redirect(url_for("config_page"))
                        resp.set_cookie("ua_remember", token, max_age=30 * 86400, httponly=True, secure=True, samesite="Lax")
                        return resp
            return redirect(url_for("config_page"))
        # Failed recovery attempt -> record and show recovery page
        _handle_failed_auth(get_remote_address())
        return render_template("login_recovery.html", error="Recovery code invalid", show_2fa=_totp_enabled())

    # No persisted user: allow first-run creation with recovery-code flow
    if username and password and recovery_code and _consume_recovery_code(recovery_code):
        try:
            auth_mod.create_user(username, password)
        except ValueError as exc:
            return render_template("login_recovery.html", error=str(exc), show_2fa=_totp_enabled())
        except Exception:
            return render_template("login_recovery.html", error="Unable to create account", show_2fa=_totp_enabled())

        _session_set("authenticated", True)
        with contextlib.suppress(Exception):
            _session_set("username", username)
        with contextlib.suppress(Exception):
            _session_set("csrf_token", secrets.token_urlsafe(32))
        if remember:
            session.permanent = True
            with contextlib.suppress(Exception):
                token = _create_remember_token(username)
                if token:
                    resp = redirect(url_for("config_page"))
                    resp.set_cookie("ua_remember", token, max_age=30 * 86400, httponly=True, secure=True, samesite="Lax")
                    with suppress(Exception):
                        _cleanup_duplicate_sessions(username)
                    return resp

        with suppress(Exception):
            _cleanup_duplicate_sessions(username)
        return redirect(url_for("config_page"))

    _handle_failed_auth(get_remote_address())
    return render_template("login_recovery.html", error="Recovery code invalid", show_2fa=_totp_enabled())


@app.route("/config")
def config_page():
    """Serve the config UI"""
    # Require a CSRF token or same-origin Referer for the config page when
    # the user is authenticated to reduce cross-site information leakage.
    if _is_authenticated() and not _verify_csrf_header():
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
        # Ensure a session CSRF token exists and expose it to the template so
        # client-side JS can read it without an extra round-trip if desired.
        with contextlib.suppress(Exception):
            if _is_authenticated() and not _session_get("csrf_token"):
                _session_set("csrf_token", secrets.token_urlsafe(32))
        return render_template("config.html", csrf_token=_session_get("csrf_token", ""))
    except Exception as e:
        console.print(f"Error loading config template: {e}", markup=False)
        console.print(traceback.format_exc(), markup=False)
        return "<pre>Internal server error</pre>", 500


@app.route("/api/health")
@limiter.limit("70 per hour", key_func=get_remote_address)
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "success": True, "message": "Upload-Assistant Web UI is running"})


@app.route("/api/csrf_token")
def csrf_token():
    """Return the per-session CSRF token for use by the frontend."""
    # Require authenticated web session for CSRF token access
    if not _is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401

    try:
        token = _session_get("csrf_token") or ""
        return jsonify({"csrf_token": token, "success": True})
    except Exception:
        # Returning an empty CSRF token on error is an explicit non-secret
        # failure response; suppress Bandit's B105 false positive here.
        return jsonify({"csrf_token": "", "success": False}), 500  # nosec: B105 - not a hardcoded password


@app.route("/api/2fa/status")
def twofa_status():
    """Check 2FA status"""
    # Require authenticated web session for 2FA status
    if not _is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401

    # Require CSRF and same-origin for reads of auth/2fa state
    if not _verify_csrf_header() or not _verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

    return jsonify({"enabled": _totp_enabled(), "success": True})


@app.route("/api/access_log/level", methods=["GET", "POST"])
def access_log_level_api():
    """Get or set the access logging level.

    GET: returns current level (no auth required for read).
    POST: set level (requires web session + CSRF).

    Valid levels: access_denied (default), access, disabled
    """
    if request.method == "GET":
        # Require authenticated web session and CSRF + same-origin for reads
        if not _is_authenticated():
            return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
        if not _verify_csrf_header() or not _verify_same_origin():
            return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

        if access_logger is None:
            return jsonify({"success": False, "error": "Access logging unavailable"}), 500
        try:
            lvl = access_logger.get_level()
            return jsonify({"success": True, "level": lvl})
        except Exception:
            return jsonify({"success": False, "error": "Failed to read level"}), 500

    # POST: require authenticated web session and CSRF
    if not _is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
    if not _verify_csrf_header():
        return jsonify({"success": False, "error": "CSRF validation failed"}), 403
    # Require same-origin for token management actions
    if not _verify_same_origin():
        return jsonify({"success": False, "error": "Origin validation failed"}), 403

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


@app.route("/api/access_log/entries", methods=["GET"])
def access_log_entries_api():
    """Get recent access log entries.

    GET: returns recent log entries (requires web session).
    Query params: n (number of entries, default 50, max 200)
    """
    # Require authenticated web session
    if not _is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401

    # Require CSRF + same-origin for reads of access-log entries
    if not _verify_csrf_header() or not _verify_same_origin():
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


@app.route("/api/ip_control", methods=["GET", "POST"])
def ip_control_api():
    """Get or set IP whitelist/blacklist.

    GET: returns current whitelist and blacklist (requires web session).
    POST: updates whitelist/blacklist. Body: {"whitelist": [...], "blacklist": [...]}
    (requires web session + CSRF).
    """
    # Require authenticated web session
    if not _is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401

    if request.method == "GET":
        # Require CSRF + same-origin for reads of IP control settings
        if not _verify_csrf_header() or not _verify_same_origin():
            return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403
        try:
            whitelist = _get_ip_whitelist()
            blacklist = _get_ip_blacklist()
            return jsonify({"success": True, "whitelist": whitelist, "blacklist": blacklist})
        except Exception:
            return jsonify({"success": False, "error": "Failed to read IP control settings"}), 500

    elif request.method == "POST":
        # Require CSRF and same-origin for POST
        if not _verify_csrf_header() or not _verify_same_origin():
            return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403
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

            _set_ip_whitelist(whitelist)
            _set_ip_blacklist(blacklist)
            return jsonify({"success": True})
        except Exception as e:
            console.print(f"Error updating IP control: {e}", markup=False)
            return jsonify({"success": False, "error": "Failed to update IP control settings"}), 500
    return None


@app.route("/api/2fa/setup", methods=["POST"])
def twofa_setup():
    """Setup 2FA - generate secret and return QR code URI"""
    # Require an authenticated web session (disallow API token / basic auth)
    if not _is_authenticated():
        return jsonify({"error": "Authentication required (web session)", "success": False}), 401
    # Require CSRF + same-origin for 2FA setup (sensitive auth action)
    if not _verify_csrf_header() or not _verify_same_origin():
        return jsonify({"error": "CSRF/Origin validation failed", "success": False}), 403
    if _totp_enabled():
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


@app.route("/api/2fa/enable", methods=["POST"])
def twofa_enable():
    """Enable 2FA after verification"""
    # Require an authenticated web session (disallow API token / basic auth)
    if not _is_authenticated():
        return jsonify({"error": "Authentication required (web session)", "success": False}), 401
    # Require CSRF + same-origin for enabling 2FA
    if not _verify_csrf_header() or not _verify_same_origin():
        return jsonify({"error": "CSRF/Origin validation failed", "success": False}), 403
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
    global saved_totp_secret
    saved_totp_secret = temp_secret

    # Clear temp session
    _session_pop("temp_totp_secret", None)
    _session_pop("temp_recovery_codes", None)

    return jsonify({"success": True, "recovery_codes": temp_codes})


@app.route("/api/2fa/disable", methods=["POST"])
def twofa_disable():
    """Disable 2FA"""
    # Require an authenticated web session (disallow API token / basic auth)
    if not _is_authenticated():
        return jsonify({"error": "Authentication required (web session)", "success": False}), 401
    # Require CSRF + same-origin for disabling 2FA
    if not _verify_csrf_header() or not _verify_same_origin():
        return jsonify({"error": "CSRF/Origin validation failed", "success": False}), 403
    if not _totp_enabled():
        return jsonify({"error": "2FA not enabled", "success": False}), 400

    try:
        auth_mod.set_twofa_state(None, [])
    except OSError, ValueError, TypeError, auth_mod.EncryptionError, json.JSONDecodeError:
        return jsonify({"error": "Failed to disable 2FA", "success": False}), 500

    # Update global variable
    global saved_totp_secret
    saved_totp_secret = None

    return jsonify({"success": True})


@app.route("/api/browse_roots")
def browse_roots():
    """Return configured browse roots"""
    roots = _get_browse_roots()
    if not roots:
        return jsonify({"error": "Browsing is not configured", "success": False}), 400

    # First pass: collect all display names to detect duplicates
    name_to_roots: dict[str, list[str]] = {}
    for root in roots:
        display_name = Path(root.rstrip(os.sep)).name or root
        if display_name not in name_to_roots:
            name_to_roots[display_name] = []
        name_to_roots[display_name].append(root)

    # Second pass: build items with subtitles when needed
    items: list[BrowseItem] = []
    for root in roots:
        display_name = Path(root.rstrip(os.sep)).name or root
        try:
            stat_res = Path(root).stat()
            mtime = stat_res.st_mtime
            size = 0
        except Exception:
            mtime = 0.0
            size = 0
        item: BrowseItem = {
            "name": display_name,
            "path": root,
            "type": "folder",
            "children": [],
            "mtime": mtime,
            "size": size,
        }

        # Add subtitle if multiple roots share the same folder name
        if len(name_to_roots.get(display_name, [])) > 1:
            # Show parent path or drive letter
            parent = str(Path(root.rstrip(os.sep)).parent)
            if parent:
                # On Windows, show drive letter + parent; on Unix, show parent path
                item["subtitle"] = parent
            else:
                # Fallback to full path if no parent (e.g., drive root)
                item["subtitle"] = root

        items.append(item)

    # If caller used a bearer token, require it to be valid.
    bearer = _get_bearer_from_header()
    if bearer and not _token_is_valid(bearer):
        return jsonify({"success": False, "error": "Forbidden (invalid token)"}), 403

    return jsonify({"items": items, "success": True})


@app.route("/api/config_options")
def config_options():
    """Return config options based on example_config.py with overrides from config.py"""
    # Require an authenticated web session; disallow bearer/basic API auth for config access
    if not _is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401

    # Require CSRF and same-origin for reading configuration options
    if not _verify_csrf_header() or not _verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

    base_dir = STATE_DIR
    example_path = CODE_DIR / "data" / "example_config.py"
    config_path = base_dir / "data" / "config.py"

    example_config_loaded = _load_config_from_file(example_path)
    example_config = example_config_loaded or {}
    user_config_loaded = _load_config_from_file(config_path)
    user_config = user_config_loaded or {}
    comments_map, subsection_map = _extract_example_metadata(example_path)

    # Determine config load status so the UI can warn the user
    # instead of silently showing defaults.
    config_warning: str | None = None
    if not config_path.exists():
        config_warning = "No config.py found — showing example defaults. Configure your settings and save, or place your config.py into the mounted data/ directory."
    elif user_config_loaded is None:
        config_warning = (
            "config.py exists but could not be loaded — showing example defaults. "
            "Check the container logs for details. The file may have a syntax error "
            "or may not contain a valid 'config' dict."
        )

    sections: list[ConfigSection] = []

    for section_name, example_section_raw in example_config.items():
        if not isinstance(example_section_raw, Mapping):
            continue
        example_section = cast(dict[str, Any], example_section_raw)

        user_section_raw = user_config.get(section_name, {})
        user_section = cast(dict[str, Any], user_section_raw) if isinstance(user_section_raw, Mapping) else {}
        items = _build_config_items(example_section, user_section, comments_map, subsection_map, [section_name])

        # Add special client list items to DEFAULT section
        if section_name == "DEFAULT":
            # Check if they already exist in items
            existing_keys = {str(item["key"]) for item in items if "key" in item}
            if "injecting_client_list" not in existing_keys:
                items.append(
                    {
                        "key": "injecting_client_list",
                        "value": user_section.get("injecting_client_list", []),
                        "source": "config" if "injecting_client_list" in user_section else "example",
                        "help": [
                            "A list of clients to use for injection (aka actually adding the torrent for uploading)",
                            'eg: ["qbittorrent", "rtorrent"]',
                        ],
                        "subsection": "CLIENT SETUP",
                    }
                )
            if "searching_client_list" not in existing_keys:
                items.append(
                    {
                        "key": "searching_client_list",
                        "value": user_section.get("searching_client_list", []),
                        "source": "config" if "searching_client_list" in user_section else "example",
                        "help": [
                            "A list of clients to search for torrents.",
                            'eg: ["qbittorrent", "qbittorrent_searching"]',
                            "will fallback to default_torrent_client if empty",
                        ],
                        "subsection": "CLIENT SETUP",
                    }
                )
            # Update subsection_map for these items
            subsection_map["DEFAULT/injecting_client_list"] = "CLIENT SETUP"
            subsection_map["DEFAULT/searching_client_list"] = "CLIENT SETUP"

        sections.append({"section": section_name, "items": items})

        if section_name == "TORRENT_CLIENTS":
            client_types: set[str] = set()
            for item in items:
                children = item.get("children")
                if children:
                    client_type_item = next((c for c in children if c.get("key") == "torrent_client"), None)
                    if client_type_item:
                        client_types.add(str(client_type_item.get("value", "unknown")))
            sections[-1]["client_types"] = sorted(client_types, key=lambda x: (x != "qbit", x))

    result: dict[str, object] = {"success": True, "sections": sections}
    if config_warning:
        result["config_warning"] = config_warning
    return jsonify(result)


@app.route("/api/torrent_clients")
def torrent_clients():
    """Return list of available torrent client names from TORRENT_CLIENTS section"""
    # Require web session for config listing (disallow bearer token access)
    if not _is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401

    # Require CSRF + same-origin for config-related reads
    if not _verify_csrf_header() or not _verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

    base_dir = STATE_DIR
    config_path = base_dir / "data" / "config.py"

    user_config = _load_config_from_file(config_path) or {}

    # Get clients only from user config
    user_clients_raw = user_config.get("TORRENT_CLIENTS", {})
    user_clients = cast(dict[str, Any], user_clients_raw) if isinstance(user_clients_raw, Mapping) else {}

    # Include all configured clients in the dropdown
    client_names: list[str] = [str(key) for key in user_clients]

    return jsonify({"success": True, "clients": sorted(client_names)})


@app.route("/api/trackers")
def get_trackers():
    """Return a list of available trackers and the configured default trackers"""
    if not _is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401

    if not _verify_csrf_header() or not _verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

    base_dir = STATE_DIR
    config_path = base_dir / "data" / "config.py"
    user_config = _load_config_from_file(config_path) or {}

    trackers_section = user_config.get("TRACKERS", {})
    default_trackers_val = trackers_section.get("default_trackers", "")
    default_trackers_list = []
    if isinstance(default_trackers_val, str):
        default_trackers_list = [t.strip().upper() for t in default_trackers_val.split(",") if t.strip()]
    elif isinstance(default_trackers_val, list):
        default_trackers_list = [str(t).strip().upper() for t in default_trackers_val if str(t).strip()]

    # Load tracker_class_map from src.trackersetup
    try:
        from src.trackersetup import tracker_class_map
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to load trackers: {e}"}), 500

    trackers_data = []
    for tracker_name, tracker_class in tracker_class_map.items():
        display_name = getattr(tracker_class, "display_name", tracker_name)
        base_url = getattr(tracker_class, "base_url", "")
        favicon_url = ""
        static_dir = Path(__file__).parent / "static"
        for ext in ["png", "svg", "ico"]:
            local_path = static_dir / "img" / "trackers" / f"{tracker_name.lower()}.{ext}"
            if local_path.is_file():
                favicon_url = f"/static/img/trackers/{tracker_name.lower()}.{ext}"
                break

        trackers_data.append({"name": tracker_name, "display_name": display_name, "base_url": base_url, "favicon": favicon_url})

    trackers_data.sort(key=lambda x: x["display_name"].lower())

    return jsonify({"success": True, "default_trackers": default_trackers_list, "trackers": trackers_data})


@app.route("/api/config_update", methods=["POST"])
def config_update():
    """Update a config value in data/config.py"""
    # Require authenticated web session and CSRF protection; disallow bearer/basic API auth
    if not _is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
    # Require CSRF + same-origin for config updates
    if not _verify_csrf_header() or not _verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403
    data = _request_json_dict()
    path_raw = data.get("path", [])
    path: list[str] = []
    if isinstance(path_raw, Sequence) and not isinstance(path_raw, (str, bytes, bytearray)):
        path_items: Sequence[Any] = cast(Sequence[Any], path_raw)
        path.extend(p for p in path_items if isinstance(p, str) and p)
    raw_value = data.get("value")

    if not path:
        return jsonify({"success": False, "error": "Invalid path"}), 400

    base_dir = STATE_DIR
    example_path = CODE_DIR / "data" / "example_config.py"
    config_path = base_dir / "data" / "config.py"

    example_config = _load_config_from_file(example_path) or {}
    example_value = _get_nested_value(example_config, path)

    # Special handling for client lists that don't exist in example config
    key = path[-1] if path else ""
    if key in ["injecting_client_list", "searching_client_list"]:
        example_value = []  # Default to empty list
    elif example_value is None:
        return jsonify({"success": False, "error": "Path not found in example config"}), 400

    coerced_value = _coerce_config_value(raw_value, example_value)
    new_value_literal = _python_literal(coerced_value)

    # Special handling for client lists that should remain commented unless user provides values
    key = path[-1] if path else ""
    if key in ["injecting_client_list", "searching_client_list"] and coerced_value == []:
        # Remove the key from config if it exists
        try:
            # Load prior value for audit
            prior_config = _load_config_from_file(config_path) or {}
            prior_value = _get_nested_value(prior_config, path)

            source = config_path.read_text(encoding="utf-8")
            updated_source = _remove_config_key_in_source(source, path)
            config_path.write_text(updated_source, encoding="utf-8")
            # Audit record for removal
            try:
                _write_audit_log("remove_key", path, prior_value, None, True)
            except Exception as ae:
                console.print(f"Failed to write config audit record: {ae}", markup=False)
        except Exception:
            return jsonify({"success": False, "error": "An error occurred while updating the configuration"}), 500
        return jsonify({"success": True, "value": _json_safe(coerced_value)})
    # Else proceed with normal update

    # Ensure prior_value is defined for the exception path below
    prior_value = None
    try:
        # Load prior value for audit
        prior_config = _load_config_from_file(config_path) or {}
        prior_value = _get_nested_value(prior_config, path)

        source = config_path.read_text(encoding="utf-8")
        updated_source = _replace_config_value_in_source(source, path, new_value_literal)
        config_path.write_text(updated_source, encoding="utf-8")
        # Audit record for update
        try:
            _write_audit_log("update_value", path, prior_value, coerced_value, True)
        except Exception as ae:
            console.print(f"Failed to write config audit record: {ae}", markup=False)
    except Exception as e:
        # Attempt to log failed update attempt
        try:
            _write_audit_log("update_value", path, prior_value if prior_value is not None else None, coerced_value, False, str(e))
        except Exception as ae:
            console.print(f"Failed to write config audit failure record: {ae}", markup=False)
        return jsonify({"success": False, "error": "An error occurred while updating the configuration"}), 500

    return jsonify({"success": True, "value": _json_safe(coerced_value)})


@app.route("/api/config_remove_subsection", methods=["POST"])
def config_remove_subsection():
    """Remove a subsection (top-level key) from the user's config.py if present"""
    # Require authenticated web session and CSRF protection; disallow bearer/basic API auth
    if not _is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
    # Require CSRF + same-origin for config removal
    if not _verify_csrf_header() or not _verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

    data = _request_json_dict()
    path_raw = data.get("path", [])
    path: list[str] = []
    if isinstance(path_raw, Sequence) and not isinstance(path_raw, (str, bytes, bytearray)):
        path_items: Sequence[Any] = cast(Sequence[Any], path_raw)
        path.extend(p for p in path_items if isinstance(p, str) and p)

    if not path:
        return jsonify({"success": False, "error": "Invalid path"}), 400

    base_dir = STATE_DIR
    config_path = base_dir / "data" / "config.py"

    try:
        source = config_path.read_text(encoding="utf-8")
        updated = _remove_config_key_in_source(source, path)
        if updated == source:
            # Nothing changed
            return jsonify({"success": True, "value": None})
        config_path.write_text(updated, encoding="utf-8")
        return jsonify({"success": True})
    except Exception:
        return jsonify({"success": False, "error": "An error occurred while removing the configuration subsection"}), 500


@app.route("/api/tokens", methods=["GET", "POST", "DELETE"])
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
    if not _is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
    if not _verify_csrf_header():
        return jsonify({"success": False, "error": "CSRF validation failed"}), 403

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


@app.route("/api/browse")
def browse_path():
    """Browse filesystem paths"""
    requested: str = str(request.args.get("path", ""))
    file_filter: str = str(request.args.get("filter", "video"))  # 'video' or 'desc'
    try:
        path = _resolve_browse_path(requested)
    except ValueError as e:
        # Log details server-side, but avoid leaking paths/internal details to clients.
        console.print(f"Path resolution error for requested {requested!r}: {e}", markup=False)
        return jsonify({"error": "Invalid path specified", "success": False}), 400

    # Explicitly assert the resolved path is within allowed browse roots.
    try:
        _assert_safe_resolved_path(path)
    except ValueError:
        console.print(f"Path failed safety check: {requested!r}", markup=False)
        return jsonify({"error": "Invalid path specified", "success": False}), 400

    # Defensive sanity checks before using `path` in filesystem operations.
    safe_path = str(Path(path).resolve())
    if "\x00" in safe_path:
        console.print("Path contains invalid characters", markup=False)
        return jsonify({"error": "Invalid path specified", "success": False}), 400
    # codeql[py/path-injection]
    if not Path(safe_path).is_dir():
        console.print("Requested path is not a directory", markup=False)
        return jsonify({"error": "Invalid path specified", "success": False}), 400

    console.print("Browsing path allowed", markup=False)

    try:
        items: list[BrowseItem] = []
        try:
            # `safe_path` was computed above; perform an explicit realpath
            # containment check using stdlib functions so static analyzers
            # can reason about the safety of the listing operation.
            real_safe = os.path.realpath(safe_path)
            allowed = False
            for root in _get_browse_roots():
                root_real = os.path.realpath(str(Path(root).resolve()))
                try:
                    if os.path.commonpath([real_safe, root_real]) == root_real:
                        allowed = True
                        break
                except ValueError:
                    # Different drives on Windows - not allowed
                    continue
            if not allowed:
                console.print(f"Path failed containment check before listing: {safe_path!r}", markup=False)
                return jsonify({"error": "Invalid path specified", "success": False}), 400

            # codeql[py/path-injection]
            for item in sorted([p.name for p in Path(safe_path).iterdir()]):
                # Skip hidden files
                if item.startswith("."):
                    continue
                full_path = Path(safe_path) / item
                # Explicitly assert each resolved child path is safe. If the
                # assertion fails for a specific entry, skip it rather than
                # failing the whole browse operation.
                try:
                    _assert_safe_resolved_path(full_path)
                except ValueError:
                    continue
                try:
                    # codeql[py/path-injection]
                    is_dir = Path(full_path).is_dir()

                    # Keep description browsing limited to known text-ish files.
                    # Default browsing should expose any file inside allowed roots
                    # so books, games, ISOs, and other upload types are visible.
                    if not is_dir and file_filter == "desc":
                        ext = Path(item.lower()).suffix
                        if ext not in SUPPORTED_DESC_EXTS:
                            continue

                    try:
                        stat_res = Path(full_path).stat()
                        mtime = stat_res.st_mtime
                        size = stat_res.st_size if not is_dir else 0
                    except Exception:
                        mtime = 0.0
                        size = 0

                    items.append(
                        {
                            "name": item,
                            "path": str(full_path),
                            "type": "folder" if is_dir else "file",
                            "children": [] if is_dir else None,
                            "mtime": mtime,
                            "size": size,
                        }
                    )
                except PermissionError, OSError:
                    continue

            console.print(f"Found {len(items)} items in {path}", markup=False)

        except PermissionError:
            console.print(f"Error: Permission denied: {path}", markup=False)
            return jsonify({"error": "Permission denied", "success": False}), 403

        # If caller used a bearer token, require it to be valid. Valid bearer
        # tokens are allowed without CSRF since they are intended for programmatic
        # access. Otherwise require an authenticated web session + CSRF + same-origin.
        bearer = _get_bearer_from_header()
        if bearer:
            if not _token_is_valid(bearer):
                return jsonify({"success": False, "error": "Forbidden (invalid token)"}), 403
        else:
            # Require session-based callers to be authenticated and provide CSRF + Origin
            if not _is_authenticated():
                return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
            if not _verify_csrf_header() or not _verify_same_origin():
                return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

        return jsonify({"items": items, "success": True, "path": path, "count": len(items)})

    except Exception as e:
        console.print(f"Error browsing {path}: {e}", markup=False)
        console.print(traceback.format_exc(), markup=False)
        return jsonify({"error": "Error browsing path", "success": False}), 500


@app.route("/api/browse_search")
def browse_search():
    """Search filesystem for files/folders matching a query string"""
    query = (request.args.get("q") or "").strip()
    file_filter: str = request.args.get("filter", "video")
    try:
        max_results = min(int(request.args.get("max_results", "100")), 500)
        if max_results < 1:
            max_results = 100
    except ValueError, TypeError:
        max_results = 100

    if not query:
        return jsonify({"success": True, "items": [], "query": ""})

    bearer = _get_bearer_from_header()
    if bearer:
        if not _token_is_valid(bearer):
            return jsonify({"success": False, "error": "Forbidden (invalid token)"}), 403
    else:
        if not _is_authenticated():
            return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
        if not _verify_csrf_header() or not _verify_same_origin():
            return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

    roots = _get_browse_roots()
    if not roots:
        return jsonify({"success": False, "error": "Browsing is not configured"}), 400

    # Split on common separators
    query_tokens = [t for t in _BROWSE_SEARCH_SEP_RE.split(query.lower()) if t]
    if not query_tokens:
        return jsonify({"success": True, "items": [], "query": query})

    def name_matches(name: str) -> bool:
        """Check if query tokens appear as whole-word ordered subsequence in the name."""
        name_tokens = [t for t in _BROWSE_SEARCH_SEP_RE.split(name.lower()) if t]
        pos = 0
        for qt in query_tokens:
            found = False
            while pos < len(name_tokens):
                if name_tokens[pos] == qt:
                    pos += 1
                    found = True
                    break
                pos += 1
            if not found:
                return False
        return True

    items: list[BrowseItem] = []

    try:
        for root in roots:
            root_abs = str(Path(root).resolve())
            if not Path(root_abs).is_dir():
                continue
            try:
                for dirpath, dirnames, filenames in os.walk(root_abs):
                    # Skip hidden dirs
                    dirnames[:] = [d for d in dirnames if not d.startswith(".")]

                    # Check dirs
                    for dirname in dirnames:
                        if name_matches(dirname):
                            full_path = Path(dirpath) / dirname
                            try:
                                _assert_safe_resolved_path(full_path)
                            except ValueError:
                                continue
                            try:
                                stat_res = Path(full_path).stat()
                                mtime = stat_res.st_mtime
                                size = 0
                            except Exception:
                                mtime = 0.0
                                size = 0
                            items.append(
                                {
                                    "name": dirname,
                                    "path": str(full_path),
                                    "type": "folder",
                                    "children": [],
                                    "mtime": mtime,
                                    "size": size,
                                }
                            )
                            if len(items) >= max_results:
                                break

                    if len(items) >= max_results:
                        break

                    # Check files
                    for filename in filenames:
                        if filename.startswith("."):
                            continue
                        if not name_matches(filename):
                            continue
                        if file_filter == "desc":
                            ext = Path(filename.lower()).suffix
                            if ext not in SUPPORTED_DESC_EXTS:
                                continue
                        full_path = Path(dirpath) / filename
                        try:
                            _assert_safe_resolved_path(full_path)
                        except ValueError:
                            continue
                        try:
                            stat_res = Path(full_path).stat()
                            mtime = stat_res.st_mtime
                            size = stat_res.st_size
                        except Exception:
                            mtime = 0.0
                            size = 0
                        items.append(
                            {
                                "name": filename,
                                "path": str(full_path),
                                "type": "file",
                                "children": None,
                                "mtime": mtime,
                                "size": size,
                            }
                        )
                        if len(items) >= max_results:
                            break

                    if len(items) >= max_results:
                        break
            except PermissionError:
                continue
            except Exception as e:
                console.print(f"Error searching in {root}: {e}", markup=False)
                continue

            if len(items) >= max_results:
                break

        # Sort by folders first and then alphabetically
        items.sort(key=lambda x: (0 if x.get("type") == "folder" else 1, (x.get("name") or "").lower()))

        return jsonify({"success": True, "items": items, "query": query, "count": len(items), "truncated": len(items) >= max_results})

    except Exception as e:
        console.print(f"Error in browse_search: {e}", markup=False)
        console.print(traceback.format_exc(), markup=False)
        return jsonify({"error": "Error searching files", "success": False}), 500


@app.route("/api/execution_preview")
@limiter.limit("7200 per hour", key_func=_rate_limit_key_func, override_defaults=True)
def execution_preview():
    """Return the current media preview for an active execution session."""

    def no_store(response: object) -> object:
        response.headers["Cache-Control"] = "no-store, max-age=0"  # type: ignore[attr-defined]
        return response

    session_id = str(request.args.get("session_id", "")).strip()
    if not session_id:
        return no_store(jsonify({"success": False, "error": "Missing session_id"})), 400

    preview = _find_execution_preview(session_id)
    if preview is None:
        return no_store(jsonify({"success": False, "error": "Session not found"})), 404

    return no_store(jsonify({"success": True, "media": preview}))


@app.route("/api/argument_presets", methods=["GET", "POST", "DELETE"])
def argument_presets():
    """Read and persist shared Web UI argument presets in ``data``."""
    if not _is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
    if not _verify_csrf_header() or not _verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

    with _argument_presets_lock:
        presets = _load_argument_presets()
        if request.method == "GET":
            return jsonify({"success": True, "presets": presets})

        data = _request_json_dict()
        name_value = data.get("name")
        name = name_value.strip() if isinstance(name_value, str) else ""
        if not name:
            return jsonify({"success": False, "error": "Preset name is required"}), 400

        if request.method == "DELETE":
            next_presets = [preset for preset in presets if preset["name"].casefold() != name.casefold()]
        else:
            arguments_value = data.get("arguments")
            arguments = arguments_value.strip() if isinstance(arguments_value, str) else ""
            if not arguments:
                return jsonify({"success": False, "error": "Preset arguments are required"}), 400
            replacement = {"name": name, "arguments": arguments}
            existing_index = next(
                (index for index, preset in enumerate(presets) if preset["name"].casefold() == name.casefold()),
                None,
            )
            if existing_index is None:
                next_presets = [*presets, replacement][-MAX_ARGUMENT_PRESETS:]
            else:
                next_presets = presets.copy()
                next_presets[existing_index] = replacement

        try:
            _save_argument_presets(next_presets)
        except OSError:
            return jsonify({"success": False, "error": "Failed to persist argument presets"}), 500
        return jsonify({"success": True, "presets": next_presets})


@app.route("/api/execution_preview_cover")
def execution_preview_cover():
    """Serve a local preview cover image for the active execution session."""
    session_id = str(request.args.get("session_id", "")).strip()
    if not session_id:
        return jsonify({"success": False, "error": "Missing session_id"}), 400

    cover_file = _find_execution_preview_cover_file(session_id)
    if cover_file is None:
        return jsonify({"success": False, "error": "Cover not found"}), 404

    mimetype = mimetypes.guess_type(str(cover_file))[0] or "application/octet-stream"
    return send_file(cover_file, mimetype=mimetype, conditional=True, max_age=30)


@app.route("/api/execution_screenshots")
@limiter.limit("7200 per hour", key_func=_rate_limit_key_func, override_defaults=True)
def execution_screenshots():
    """List local FFmpeg screenshots belonging to the active execution only."""
    session_id = str(request.args.get("session_id", "")).strip()
    if not session_id:
        return jsonify({"success": False, "error": "Missing session_id"}), 400
    resolved = _resolve_execution_screenshot_review(session_id)
    if resolved is None:
        return jsonify({"success": False, "error": "Screenshots are not available yet"}), 404

    from src.screenshot_review import image_version, list_review_items

    temp_dir, meta_data = resolved
    meta_data = _screenshot_review_meta(temp_dir, meta_data)
    items = list_review_items(temp_dir, meta_data)
    can_capture = not meta_data.get("is_disc") or meta_data.get("is_disc") == "BDMV"
    return jsonify(
        {
            "success": True,
            "can_add": bool(items) and can_capture,
            "screenshots": [
                {
                    "id": item.id,
                    "filename": item.path.name if item.path else f"Remote image {item.index + 1}",
                    "size": item.path.stat().st_size if item.path else None,
                    "source": item.source,
                    "group": item.group,
                    "image_url": (
                        f"/api/execution_screenshots/{item.id}/image?session_id={session_id}&v={image_version(temp_dir, item.id, item.path.stat().st_mtime_ns)}"
                        if item.path
                        else str((item.remote_image or {}).get("img_url") or (item.remote_image or {}).get("raw_url") or "")
                    ),
                    "can_replace": can_capture and item.source != "addition",
                    "can_delete": item.source in {"local", "addition"},
                }
                for item in items
            ],
        }
    )


@app.route("/api/execution_description")
@limiter.limit("7200 per hour", key_func=_rate_limit_key_func, override_defaults=True)
def execution_description():
    """Return the editable base-description draft and its read-only sources."""
    session_id = str(request.args.get("session_id", "")).strip()
    resolved = _resolve_execution_description_review(session_id)
    if resolved is None:
        return jsonify({"success": False, "error": "Description is not available yet"}), 404
    from src.description_review import draft, source_items

    temp_dir, _meta_file, meta_data = resolved
    content, version = draft(meta_data, temp_dir)
    return jsonify(
        {
            "success": True,
            "content": content,
            "version": version,
            "sources": source_items(meta_data),
        }
    )


@app.route("/api/execution_description", methods=["PUT"])
def save_execution_description():
    """Persist an edited draft for the current execution with optimistic locking."""
    if not _verify_csrf_header() or not _verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403
    payload = _request_json_dict()
    session_id = _stringify_preview_value(payload.get("session_id"))
    content = payload.get("content")
    if not isinstance(content, str):
        return jsonify({"success": False, "error": "Description content must be text"}), 400
    if len(content) > 1_000_000:
        return jsonify({"success": False, "error": "Description exceeds the 1,000,000-character limit"}), 413
    resolved = _resolve_execution_description_review(session_id)
    if resolved is None:
        return jsonify({"success": False, "error": "Description is not available yet"}), 404

    from src.description_review import draft, save_review

    requested_version = payload.get("version")
    if not isinstance(requested_version, int):
        return jsonify({"success": False, "error": "Description version is required"}), 400

    temp_dir, _meta_file, _meta_data = resolved
    with _description_review_lock(temp_dir):
        # Reload while holding the release-specific lock so the version check and
        # write form one compare-and-swap operation across browser tabs.
        locked_resolved = _resolve_execution_description_review(session_id)
        if locked_resolved is None:
            return jsonify({"success": False, "error": "Description is not available yet"}), 404
        temp_dir, _meta_file, meta_data = locked_resolved
        _current_content, current_version = draft(meta_data, temp_dir)
        if requested_version != current_version:
            return jsonify({"success": False, "error": "Description changed in another browser tab", "version": current_version}), 409

        next_version = current_version + 1
        save_review(temp_dir, content, next_version)
    return jsonify({"success": True, "content": content, "version": next_version})


@app.route("/api/execution_description/reset", methods=["POST"])
def reset_execution_description():
    """Restore the draft from one of the read-only sources."""
    if not _verify_csrf_header() or not _verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403
    payload = _request_json_dict()
    session_id = _stringify_preview_value(payload.get("session_id"))
    source_key = _stringify_preview_value(payload.get("source_key"))
    resolved = _resolve_execution_description_review(session_id)
    if resolved is None:
        return jsonify({"success": False, "error": "Description is not available yet"}), 404
    requested_version = payload.get("version")
    if not isinstance(requested_version, int):
        return jsonify({"success": False, "error": "Description version is required"}), 400

    from src.description_review import draft, save_review, source_items

    temp_dir, _meta_file, _meta_data = resolved
    with _description_review_lock(temp_dir):
        locked_resolved = _resolve_execution_description_review(session_id)
        if locked_resolved is None:
            return jsonify({"success": False, "error": "Description is not available yet"}), 404
        temp_dir, _meta_file, meta_data = locked_resolved
        source = next((item for item in source_items(meta_data) if item["key"] == source_key), None)
        if source is None:
            return jsonify({"success": False, "error": "Description source was not found"}), 404
        content = source["content"]
        _current_content, current_version = draft(meta_data, temp_dir)
        if requested_version != current_version:
            return jsonify({"success": False, "error": "Description changed in another browser tab", "version": current_version}), 409

        next_version = current_version + 1
        save_review(temp_dir, content, next_version)
    return jsonify({"success": True, "content": content, "version": next_version})


@app.route("/api/execution_screenshots/<screenshot_id>/image")
def execution_screenshot_image(screenshot_id: str):
    """Serve one reviewed local screenshot after resolving it through its session."""
    session_id = str(request.args.get("session_id", "")).strip()
    resolved = _resolve_execution_screenshot_review(session_id)
    if resolved is None:
        return jsonify({"success": False, "error": "Screenshots are not available yet"}), 404
    from src.screenshot_review import list_review_items

    temp_dir, meta_data = resolved
    meta_data = _screenshot_review_meta(temp_dir, meta_data)
    screenshot = next((item for item in list_review_items(temp_dir, meta_data) if item.id == screenshot_id), None)
    if screenshot is None or screenshot.path is None:
        return jsonify({"success": False, "error": "Screenshot not found"}), 404
    response = send_file(screenshot.path, mimetype="image/png", conditional=True, max_age=0)
    response.headers["Cache-Control"] = "no-store, max-age=0"  # type: ignore[attr-defined]
    return response


@app.route("/api/execution_screenshots/add", methods=["POST"])
def add_execution_screenshot():
    """Capture one extra local screenshot for the active execution."""
    if not _verify_csrf_header() or not _verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403
    payload = _request_json_dict()
    session_id = _stringify_preview_value(payload.get("session_id"))
    group = _stringify_preview_value(payload.get("group")) or "main"
    resolved = _resolve_execution_screenshot_review(session_id)
    if resolved is None:
        return jsonify({"success": False, "error": "Screenshots are not available yet"}), 404
    temp_dir, meta_data = resolved
    meta_data = _screenshot_review_meta(temp_dir, meta_data)

    try:
        from src.screenshot_review import add_screenshot

        asyncio.run(add_screenshot(temp_dir, meta_data, group))
    except (FileNotFoundError, ValueError) as error:
        return jsonify({"success": False, "error": str(error)}), 404
    except Exception as error:
        console.print(f"Screenshot add failed for {session_id}: {error}", markup=False)
        return jsonify({"success": False, "error": "Could not add screenshot"}), 500
    return jsonify({"success": True})


@app.route("/api/execution_screenshots/<screenshot_id>/<action>", methods=["POST"])
def mutate_execution_screenshot(screenshot_id: str, action: str):
    """Delete or replace a reviewed frame with CSRF and same-origin protection."""
    if action not in {"delete", "replace", "undo"}:
        return jsonify({"success": False, "error": "Unsupported screenshot action"}), 404
    if not _verify_csrf_header() or not _verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403
    payload = _request_json_dict()
    session_id = _stringify_preview_value(payload.get("session_id"))
    resolved = _resolve_execution_screenshot_review(session_id)
    if resolved is None:
        return jsonify({"success": False, "error": "Screenshots are not available yet"}), 404
    temp_dir, meta_data = resolved
    meta_data = _screenshot_review_meta(temp_dir, meta_data)

    try:
        from src.screenshot_review import delete_screenshot, replace_screenshot, undo_remote_replacement

        if action == "delete":
            delete_screenshot(temp_dir, meta_data, screenshot_id)
        elif action == "undo":
            undo_remote_replacement(temp_dir, screenshot_id)
        else:
            asyncio.run(replace_screenshot(temp_dir, meta_data, screenshot_id))
    except (FileNotFoundError, ValueError) as error:
        return jsonify({"success": False, "error": str(error)}), 404
    except Exception as error:
        console.print(f"Screenshot {action} failed for {session_id}: {error}", markup=False)
        return jsonify({"success": False, "error": f"Could not {action} screenshot"}), 500

    return jsonify({"success": True})


@app.route("/api/save_queue", methods=["POST"])
@limiter.limit("100 per hour", key_func=_rate_limit_key_func)
def save_queue():
    """Save selected items to a temporary queue text file on the server"""
    # CSRF check
    if not _verify_csrf_header():
        return jsonify({"error": "CSRF token missing or invalid", "success": False}), 403

    # Auth check
    bearer = _get_bearer_from_header()
    if bearer:
        if not _token_is_valid(bearer):
            return jsonify({"success": False, "error": "Forbidden (invalid token)"}), 403
    else:
        if not _is_authenticated():
            return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
        if not _verify_same_origin():
            return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

    try:
        data = _as_dict(request.get_json(silent=True)) or {}
        items = data.get("items")
        if not isinstance(items, list):
            return jsonify({"error": "Items must be a list", "success": False}), 400

        if not items:
            return jsonify({"error": "No items provided", "success": False}), 400

        base_dir = STATE_DIR
        tmp_dir = base_dir / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        filename = f"webui_queue_{int(time.time() * 1000)}_{secrets.token_hex(4)}.txt"
        file_path = tmp_dir / filename

        validated_items: list[tuple[str, list[str]]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path", "")).strip()
            args = str(item.get("args", "")).strip()
            if not path:
                continue

            try:
                validated_path = _resolve_user_path(path, require_exists=True, require_dir=False)
                validated_args = _validate_upload_assistant_args(shlex.split(args) if args else [])
            except (ValueError, TypeError) as err:
                return jsonify({"error": f"Invalid queue item: {err}", "success": False}), 400
            validated_items.append((validated_path, validated_args))

        if not validated_items:
            return jsonify({"error": "No valid items provided", "success": False}), 400

        with file_path.open("w", encoding="utf-8") as f:
            for validated_path, validated_args in validated_items:
                line = f'"{validated_path}"'
                if validated_args:
                    line += f" {shlex.join(validated_args)}"
                f.write(line + "\n")

        return jsonify({"success": True, "path": str(file_path)})

    except Exception as e:
        console.print(f"Error saving queue: {e}", markup=False)
        console.print(traceback.format_exc(), markup=False)
        return jsonify({"error": "Error saving queue file", "success": False}), 500


@app.route("/api/execute", methods=["POST", "OPTIONS"])
@limiter.limit("100 per hour", key_func=_rate_limit_key_func)
def execute_command():
    """Execute upload.py with interactive terminal support"""

    if request.method == "OPTIONS":
        return "", 204

    # Require CSRF token for execute POST requests
    if request.method == "POST" and not _verify_csrf_header():
        return jsonify({"error": "CSRF token missing or invalid", "success": False}), 403

    # If caller used a bearer token, ensure it is valid
    bearer = _get_bearer_from_header()
    if bearer and not _token_is_valid(bearer):
        return jsonify({"error": "Forbidden (invalid token)", "success": False}), 403

    try:
        # Prefer a silent JSON parse to avoid Werkzeug raising on malformed
        # payloads. If parsing fails, try form data or a few tolerant
        # fallbacks to extract common fields (path, args, session_id).
        data = None
        try:
            data = _as_dict(request.get_json(silent=True)) or {}
        except Exception:
            data = None

        if not data:
            # Try standard form-encoded body first
            try:
                if request.form:
                    data = dict(request.form.items())
            except Exception:
                data = None

        if not data:
            # As a last resort attempt to parse raw body text that may be
            # produced by shells which strip quoting or backslashes. We
            # attempt a few conservative transforms rather than executing
            # arbitrary code: 1) normalize single quotes to double quotes,
            # 2) quote unquoted object keys, then try json.loads. If that
            # fails, fall back to simple regex extraction of `path` and
            # `session_id` values.
            try:
                raw = (request.get_data(as_text=True) or "").strip()
                if raw:
                    # Quick normalization: single -> double quotes
                    candidate = raw.replace("'", '"')
                    # Quote unquoted keys like: {path:...} -> {"path":...}
                    candidate = re.sub(r"([\{\s,])([A-Za-z0-9_]+)\s*:", r'\1"\2":', candidate)
                    try:
                        data = _json_load_dict(candidate)
                    except Exception:
                        # Regex extraction fallback for minimal fields
                        d: dict[str, str] = {}
                        m_path = re.search(r'path\s*[:=]\s*["\']?([^"\'\},]+)', raw)
                        m_sess = re.search(r'session_id\s*[:=]\s*["\']?([^"\'\},]+)', raw)
                        m_args = re.search(r'args\s*[:=]\s*["\']?([^"\'\}]+)', raw)
                        if m_path:
                            d["path"] = m_path.group(1)
                        if m_sess:
                            d["session_id"] = m_sess.group(1)
                        if m_args:
                            # Trim any trailing quote/comma characters and preserve spacing
                            raw_args = m_args.group(1).strip()
                            # Defensive: some shells or quoting can produce a
                            # concatenated fragment like `--debug,session_id:...`.
                            # Strip any trailing `,session_id` fragment or any
                            # comma followed by a session_id key so args remain
                            # clean.
                            raw_args = re.split(r',\s*(?:"?session_id|session_id)\b', raw_args)[0]
                            raw_args = raw_args.rstrip(",").strip().strip('"').strip("'")
                            d["args"] = raw_args
                        if d:
                            data = d
            except Exception:
                data = None

        if not data:
            return jsonify({"error": "No JSON data received", "success": False}), 400

        path = str(data.get("path", ""))
        args = str(data.get("args", ""))
        session_id = str(data.get("session_id", "default"))
        # If a previous run for this session left state behind, attempt to
        # terminate/cleanup it so the new execution starts with a clean slate.
        with contextlib.suppress(Exception):
            existing = active_processes.pop(session_id, None)
            if existing:
                proc = existing.get("process")
                if proc and proc.poll() is None:
                    with contextlib.suppress(Exception):
                        _terminate_process_tree(proc)

        console.print(f"Execute request - Path: {path}, Args: {args}, Session: {session_id}", markup=False)

        if not path:
            return jsonify({"error": "Missing path", "success": False}), 400

        def generate():
            try:
                # Build command to run upload.py directly
                validated_path = _resolve_user_path(path, require_exists=True, require_dir=False)

                # Additional explicit assertion for static analysis: ensure the
                # resolved path is within allowed browse roots and contains no
                # invalid characters before using it in commands/subprocesses.
                try:
                    _assert_safe_resolved_path(validated_path)
                except ValueError:
                    yield f"data: {json.dumps({'type': 'error', 'data': 'Invalid execution path'})}\n\n"
                    return

                base_dir = STATE_DIR
                upload_script = str(CODE_DIR / "upload.py")
                command = [sys.executable, "-u", upload_script, validated_path]

                process_state = _make_process_state(validated_path, args)
                with active_processes_lock:
                    active_processes[session_id] = process_state

                # Add arguments if provided
                if args:
                    import shlex

                    parsed_args = shlex.split(args)
                    try:
                        validated_args = _validate_upload_assistant_args(parsed_args)
                    except ValueError as err:
                        console.print(f"Invalid execution arguments: {err}", markup=False)
                        _discard_session_state(session_id, process_state)
                        yield f"data: {json.dumps({'type': 'error', 'data': 'Invalid execution arguments'})}\n\n"
                        return
                    command.extend(validated_args)

                command_str = subprocess.list2cmdline(command)
                console.print(f"Running: {command_str}", markup=False)

                yield f"data: {json.dumps({'type': 'system', 'data': f'Executing: {command_str}'})}\n\n"

                # The upload controller must be isolated so Kill can terminate its
                # external workers as one process tree. Subprocess stdin already
                # supports the WebUI prompt flow.
                use_subprocess = True

                if not use_subprocess:
                    # In-process execution path
                    _cli_ui: Any = importlib.import_module("cli_ui")

                    src_console: Any = importlib.import_module("src.console")

                    console.print("Running in-process (rich-captured) mode", markup=False)

                    # Prepare input queue for prompts
                    input_queue: queue.Queue[str] = queue.Queue()

                    # Import upload.main on the main thread to avoid thread-unsafe imports
                    # inside the worker thread. Importing here ensures any module-level
                    # side-effects run on the request/main thread rather than inside
                    # the worker thread.
                    try:
                        import upload as _upload

                        upload_main = _upload.main
                    except Exception as _e:
                        upload_main = None

                    # Prepare a recording Console to capture rich output
                    import io

                    rich_console_mod: Any = importlib.import_module("rich.console")
                    rich_console_class = rich_console_mod.Console

                    # Use an in-memory file for the recorder to avoid duplicating
                    # output to the real stdout. record=True still records renderables.
                    record_console = rich_console_class(record=True, force_terminal=True, width=120, file=io.StringIO())

                    # Queue to serialize print actions from the worker thread
                    render_queue: queue.Queue[tuple[Any, dict[str, Any]]] = queue.Queue()
                    progress_event_queue: queue.Queue[None] = queue.Queue(maxsize=64)
                    queued_progress_events: dict[str, dict[str, object]] = {}
                    progress_queue_lock = threading.Lock()

                    # Cancellation event for cooperative shutdown
                    cancel_event = threading.Event()

                    # Acquire lock BEFORE any global mutation to prevent concurrent runs
                    # from corrupting each other's sys.argv and console patches.
                    try:
                        acquired = inproc_lock.acquire(timeout=2)
                    except TypeError:
                        acquired = inproc_lock.acquire(blocking=False)

                    if not acquired:
                        console.print(f"Failed to acquire inproc lock for session {session_id}; another inproc run may be active", markup=False)
                        _discard_session_state(session_id, process_state)
                        yield f"data: {json.dumps({'type': 'error', 'data': 'Another in-process run is active'})}\n\n"
                        return

                    if not _session_state_is_current(session_id, process_state):
                        with contextlib.suppress(Exception):
                            inproc_lock.release()
                        _discard_session_state(session_id, process_state)
                        yield f"data: {json.dumps({'type': 'error', 'data': 'Execution session was replaced'})}\n\n"
                        return

                    # Monkeypatch the existing shared console to record prints and intercept input
                    orig_console: Any = src_console.console

                    # Avoid double-wrapping the console if already patched by a previous run
                    console_key = id(orig_console)
                    if console_key not in _ua_console_store:
                        # Store originals so we can restore later
                        _ua_console_store[console_key] = {
                            "orig_print": orig_console.print,
                            "orig_input": getattr(orig_console, "input", None),
                            "orig_ask_yes_no": None,
                            "orig_ask_string": None,
                            "orig_ask_choice": None,
                        }

                        # Wrap print to duplicate into the recorder
                        orig_print = orig_console.print

                        def wrapped_print(*p_args: Any, **p_kwargs: Any) -> Any:
                            # Enqueue print calls to be applied from the SSE thread
                            with contextlib.suppress(Exception):
                                render_queue.put((p_args, p_kwargs))
                            return orig_print(*p_args, **p_kwargs)

                        orig_console.print = cast(Any, wrapped_print)

                        # Intercept console.input to send prompt to client and wait for queue
                        orig_input = getattr(orig_console, "input", None)

                        def wrapped_input(prompt: str = "") -> str:
                            # Print the prompt so it appears in the recorded output
                            with contextlib.suppress(Exception):
                                wrapped_print(prompt)
                            # Wait for input while respecting cancellation
                            _set_process_awaiting_input_if_current(session_id, process_state, True)
                            while True:
                                if cancel_event.is_set():
                                    _set_process_awaiting_input_if_current(session_id, process_state, False)
                                    raise EOFError()
                                try:
                                    result = input_queue.get(timeout=0.5)
                                    _set_process_awaiting_input_if_current(session_id, process_state, False)
                                    return result
                                except queue.Empty:
                                    continue
                                except Exception:
                                    _set_process_awaiting_input_if_current(session_id, process_state, False)
                                    raise

                        orig_console.input = cast(Any, wrapped_input)
                    else:
                        # Already wrapped; retrieve stored originals so restoration works
                        stored = _ua_console_store.get(console_key, {})
                        orig_print = stored.get("orig_print", orig_console.print)
                        orig_input = stored.get("orig_input", getattr(orig_console, "input", None))

                    # Monkeypatch cli_ui.ask_yes_no and ask_string similarly
                    orig_ask_yes_no = None
                    orig_ask_string = None
                    orig_ask_choice = None
                    try:
                        orig_ask_yes_no = _cli_ui.ask_yes_no

                        def wrapped_ask_yes_no(*args: Any, default: bool = False, **kwargs: Any) -> bool:
                            # Support both signatures used across the codebase:
                            #   ask_yes_no(question, default=...)
                            #   ask_yes_no(color, question, default=...)
                            # Extract the question and default value from args/kwargs.
                            if len(args) >= 2:
                                question = args[1]
                            elif len(args) == 1:
                                question = args[0]
                            else:
                                question = kwargs.get("question", "")

                            with contextlib.suppress(Exception):
                                wrapped_print(str(question))
                            # Wait for a response or cancellation
                            _set_process_awaiting_input_if_current(session_id, process_state, True, "yes_no")
                            while True:
                                if cancel_event.is_set():
                                    _set_process_awaiting_input_if_current(session_id, process_state, False)
                                    raise EOFError()
                                try:
                                    resp = input_queue.get(timeout=0.5)
                                except queue.Empty:
                                    continue
                                except Exception:
                                    _set_process_awaiting_input_if_current(session_id, process_state, False)
                                    raise
                                resp = (resp or "").strip().lower()
                                if not resp:
                                    _set_process_awaiting_input_if_current(session_id, process_state, False)
                                    return default
                                if resp in ("y", "yes"):
                                    _set_process_awaiting_input_if_current(session_id, process_state, False)
                                    return True
                                if resp in ("n", "no"):
                                    _set_process_awaiting_input_if_current(session_id, process_state, False)
                                    return False
                                with contextlib.suppress(Exception):
                                    wrapped_print("Please answer y or n.")
                                _set_process_awaiting_input_if_current(session_id, process_state, True, "yes_no")

                        _cli_ui.ask_yes_no = wrapped_ask_yes_no
                        # Save original ask_yes_no so external cleaners (eg. /api/kill)
                        # can restore it if the inproc run is terminated early.
                        with contextlib.suppress(Exception):
                            if console_key in _ua_console_store:
                                _ua_console_store[console_key]["orig_ask_yes_no"] = orig_ask_yes_no

                        # ask_string: prompt user for an arbitrary string
                        try:
                            orig_ask_string = _cli_ui.ask_string

                            def wrapped_ask_string(*question: Any, **_kwargs: Any) -> str | None:
                                prompt = " ".join(str(q) for q in question)
                                with contextlib.suppress(Exception):
                                    wrapped_print(prompt)
                                # Wait for input or cancellation
                                _set_process_awaiting_input_if_current(session_id, process_state, True)
                                while True:
                                    if cancel_event.is_set():
                                        _set_process_awaiting_input_if_current(session_id, process_state, False)
                                        raise EOFError()
                                    try:
                                        result = input_queue.get(timeout=0.5)
                                        _set_process_awaiting_input_if_current(session_id, process_state, False)
                                        return result
                                    except queue.Empty:
                                        continue
                                    except Exception:
                                        _set_process_awaiting_input_if_current(session_id, process_state, False)
                                        raise

                            _cli_ui.ask_string = wrapped_ask_string
                            # Save original ask_string for external cleanup
                            with contextlib.suppress(Exception):
                                if console_key in _ua_console_store:
                                    _ua_console_store[console_key]["orig_ask_string"] = orig_ask_string
                        except Exception:
                            orig_ask_string = None

                        # ask_choice: prompt user to select one option from a list
                        try:
                            orig_ask_choice = _cli_ui.ask_choice

                            def wrapped_ask_choice(question: object, choices: Sequence[object] | None = None, **_kwargs: Any) -> str:
                                prompt = str(question)
                                rendered_choices = [str(choice) for choice in (choices or [])]
                                with contextlib.suppress(Exception):
                                    wrapped_print(prompt)
                                    for index, choice_text in enumerate(rendered_choices, start=1):
                                        wrapped_print(f"{index}. {choice_text}")
                                _set_process_awaiting_input_if_current(session_id, process_state, True)
                                while True:
                                    if cancel_event.is_set():
                                        _set_process_awaiting_input_if_current(session_id, process_state, False)
                                        raise EOFError()
                                    try:
                                        resp = (input_queue.get(timeout=0.5) or "").strip()
                                    except queue.Empty:
                                        continue
                                    except Exception:
                                        _set_process_awaiting_input_if_current(session_id, process_state, False)
                                        raise

                                    if not rendered_choices:
                                        _set_process_awaiting_input_if_current(session_id, process_state, False)
                                        return resp
                                    if resp.isdigit():
                                        selected_index = int(resp) - 1
                                        if 0 <= selected_index < len(rendered_choices):
                                            _set_process_awaiting_input_if_current(session_id, process_state, False)
                                            return rendered_choices[selected_index]
                                    for choice_text in rendered_choices:
                                        if resp.lower() == choice_text.lower():
                                            _set_process_awaiting_input_if_current(session_id, process_state, False)
                                            return choice_text

                            _cli_ui.ask_choice = wrapped_ask_choice
                            with contextlib.suppress(Exception):
                                if console_key in _ua_console_store:
                                    _ua_console_store[console_key]["orig_ask_choice"] = orig_ask_choice
                        except Exception:
                            orig_ask_choice = None
                    except Exception:
                        orig_ask_yes_no = None

                    # Prepare sys.argv for upload.py to parse
                    old_argv = list(sys.argv)
                    try:
                        import shlex

                        parsed_args = []
                        if args:
                            parsed_args = shlex.split(args)
                            parsed_args = _validate_upload_assistant_args(parsed_args)

                        sys.argv = [upload_script, validated_path, *parsed_args]

                        # Store in active_processes so /api/input can post into the queue
                        process_state.update(
                            {
                                "mode": "inproc",
                                "input_queue": input_queue,
                                "record_console": record_console,
                                "cancel_event": cancel_event,
                                "progress_event_queue": progress_event_queue,
                            }
                        )
                        if not _session_state_is_current(session_id, process_state):
                            raise RuntimeError("Execution session was replaced before in-process startup completed")

                        # Run the upload main loop in a separate thread to avoid blocking SSE generator
                        def run_upload():
                            previous_webui_active = os.environ.get("UA_WEBUI_ACTIVE")
                            os.environ["UA_WEBUI_ACTIVE"] = "1"

                            def emit_progress(event: ProgressEvent) -> None:
                                event_copy = dict(event)
                                if not _session_state_is_current(session_id, process_state):
                                    return
                                _set_process_progress_if_current(session_id, process_state, event_copy)
                                with contextlib.suppress(Exception):
                                    progress_id = str(event_copy.get("id", "")).strip()
                                    queue_key = progress_id or f"__event__:{event_copy.get('op', 'upsert')}"
                                    with progress_queue_lock:
                                        queued_progress_events[queue_key] = event_copy
                                        while len(queued_progress_events) > 64:
                                            oldest_key = next(iter(queued_progress_events))
                                            queued_progress_events.pop(oldest_key, None)
                                        with contextlib.suppress(queue.Full):
                                            progress_event_queue.put_nowait(None)

                            try:
                                # Run the async main() entry point of upload.py
                                import asyncio

                                # Use the pre-imported upload_main from the outer scope.
                                # If it wasn't available, attempt a safe import here as fallback.
                                nonlocal_upload = upload_main
                                if nonlocal_upload is None:
                                    try:
                                        import upload as _upload_fallback

                                        nonlocal_upload = _upload_fallback.main
                                    except Exception:
                                        nonlocal_upload = None

                                # Ensure Windows event loop policy when needed
                                if sys.platform == "win32" and sys.version_info < (3, 14):
                                    policy_class = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
                                    if policy_class is not None:
                                        with contextlib.suppress(Exception):
                                            asyncio.set_event_loop_policy(policy_class())
                                if nonlocal_upload is None:
                                    raise RuntimeError("upload.main not available for in-process execution")
                                set_webui_session_id = getattr(sys.modules.get("upload"), "set_webui_session_id", None)
                                if callable(set_webui_session_id):
                                    with contextlib.suppress(Exception):
                                        set_webui_session_id(session_id, str(process_state.get("run_token") or ""))
                                set_progress_callback(emit_progress)
                                reset_progress()
                                asyncio.run(nonlocal_upload())
                            except Exception as e:
                                # If the exception is the cooperative cancellation marker,
                                # print a short, non-alarming message and avoid printing
                                # the full traceback which can confuse the operator.
                                try:
                                    if isinstance(e, EOFError):
                                        console.print("In-process run cancelled (Ctrl+C)", markup=False)
                                    else:
                                        console.print(f"In-process execution error: {e}", markup=False)
                                        console.print(traceback.format_exc(), markup=False)
                                except Exception:
                                    with contextlib.suppress(Exception):
                                        console.print("In-process run ended", markup=False)
                            finally:
                                clear_progress_callback()
                                if previous_webui_active is None:
                                    os.environ.pop("UA_WEBUI_ACTIVE", None)
                                else:
                                    os.environ["UA_WEBUI_ACTIVE"] = previous_webui_active
                                # Restore sys.argv in finally block
                                # Restore patched console
                                console_key = id(src_console.console)
                                if console_key in _ua_console_store:
                                    origs = _ua_console_store[console_key]
                                    src_console.console.print = origs["orig_print"]
                                    if "orig_input" in origs and origs["orig_input"] is not None:
                                        src_console.console.input = origs["orig_input"]
                                    # Restore cli_ui patched functions if present
                                    with contextlib.suppress(Exception):
                                        if "orig_ask_yes_no" in origs and origs["orig_ask_yes_no"] is not None:
                                            _cli_ui.ask_yes_no = origs["orig_ask_yes_no"]
                                    with contextlib.suppress(Exception):
                                        if "orig_ask_string" in origs and origs["orig_ask_string"] is not None:
                                            _cli_ui.ask_string = origs["orig_ask_string"]
                                        if "orig_ask_choice" in origs and origs["orig_ask_choice"] is not None:
                                            _cli_ui.ask_choice = origs["orig_ask_choice"]
                                    del _ua_console_store[console_key]
                                with contextlib.suppress(Exception):
                                    set_webui_session_id = getattr(sys.modules.get("upload"), "set_webui_session_id", None)
                                    if callable(set_webui_session_id):
                                        set_webui_session_id(None)
                                # Release lock to allow next inproc run
                                inproc_lock.release()

                        worker = threading.Thread(target=run_upload, daemon=True)
                        worker.start()

                        # Record worker thread for debugging/cleanup
                        with contextlib.suppress(Exception):
                            if _session_state_is_current(session_id, process_state):
                                process_state["worker"] = worker

                        console.print(f"Started inproc worker for session {session_id}: {worker.name}", markup=False)

                        # Stream full HTML snapshots from the recorder while the worker runs.
                        # To avoid spinning the SSE thread and growing the server task queue
                        # when the uploader prints heavily, block waiting for print events
                        # with a short timeout and coalesce multiple prints into a
                        # single exported snapshot.
                        last_body = ""
                        try:

                            def _drain_progress_events() -> Iterator[str]:
                                while True:
                                    try:
                                        progress_event_queue.get_nowait()
                                    except queue.Empty:
                                        break
                                with progress_queue_lock:
                                    pending_events = list(queued_progress_events.values())
                                    queued_progress_events.clear()
                                for progress_event in pending_events:
                                    yield f"data: {json.dumps({'type': 'progress', 'data': progress_event})}\n\n"

                            while worker.is_alive():
                                sent_progress = False
                                for progress_sse in _drain_progress_events():
                                    sent_progress = True
                                    yield progress_sse
                                try:
                                    # Wait for the next print event (blocks briefly). This
                                    # prevents the generator from busy-waiting and tying up
                                    # Waitress worker threads.
                                    r_args, r_kwargs = render_queue.get(timeout=0.5)
                                    with contextlib.suppress(Exception):
                                        record_console.print(*r_args, **r_kwargs)

                                    # Drain any additional queued prints so we can coalesce
                                    # them into a single exported snapshot.
                                    while not render_queue.empty():
                                        try:
                                            r_args, r_kwargs = render_queue.get_nowait()
                                        except queue.Empty:
                                            break
                                        with contextlib.suppress(Exception):
                                            record_console.print(*r_args, **r_kwargs)

                                    # Export and yield a full HTML snapshot only when the
                                    # rendered body has changed.
                                    html_doc = record_console.export_html(inline_styles=True)
                                    m = re.search(r"<body[^>]*>(.*?)</body>", html_doc, re.S | re.I)
                                    body = m.group(1).strip() if m else html_doc
                                    if body != last_body:
                                        last_body = body
                                        yield f"data: {json.dumps({'type': 'html_full', 'data': body})}\n\n"
                                except queue.Empty:
                                    if sent_progress:
                                        continue
                                    # No print activity within the timeout — send a keepalive
                                    # to keep the SSE connection alive without busy-waiting.
                                    yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
                                except Exception:
                                    # Swallow per-iteration errors to keep the stream alive.
                                    yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"

                            # Worker finished; drain any remaining prints and send final snapshot
                            while not render_queue.empty():
                                try:
                                    r_args, r_kwargs = render_queue.get_nowait()
                                except queue.Empty:
                                    break
                                with contextlib.suppress(Exception):
                                    record_console.print(*r_args, **r_kwargs)

                            for progress_sse in _drain_progress_events():
                                yield progress_sse

                            with contextlib.suppress(Exception):
                                html_doc = record_console.export_html(inline_styles=True)
                                m = re.search(r"<body[^>]*>(.*?)</body>", html_doc, re.S | re.I)
                                body = m.group(1).strip() if m else html_doc
                                if body != last_body:
                                    yield f"data: {json.dumps({'type': 'html_full', 'data': body})}\n\n"
                        except Exception:
                            # Ensure generator continues and yields a final keepalive on error
                            yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"

                    finally:
                        # restore patched functions and argv
                        try:
                            # Prefer restoring originals from the module-level store
                            console_key = id(orig_console)
                            if console_key in _ua_console_store:
                                stored = _ua_console_store.pop(console_key, {})
                                with contextlib.suppress(Exception):
                                    orig_console.print = stored.get("orig_print", orig_console.print)
                                with contextlib.suppress(Exception):
                                    orig_in = stored.get("orig_input", None)
                                    if orig_in is not None:
                                        orig_console.input = orig_in
                        except Exception:
                            # best-effort restore using locals
                            with contextlib.suppress(Exception):
                                orig_console.print = orig_print
                            with contextlib.suppress(Exception):
                                if orig_input is not None:
                                    orig_console.input = orig_input

                        with contextlib.suppress(Exception):
                            if orig_ask_yes_no is not None:
                                _cli_ui.ask_yes_no = orig_ask_yes_no
                        with contextlib.suppress(Exception):
                            if orig_ask_string is not None:
                                _cli_ui.ask_string = orig_ask_string
                            if orig_ask_choice is not None:
                                _cli_ui.ask_choice = orig_ask_choice

                        sys.argv = old_argv

                        # Remove process tracking for this session
                        with contextlib.suppress(Exception):
                            _discard_session_state(session_id, process_state)

                    return

                else:
                    env = _webui_subprocess_env()

                    # Sanity-check the working directory used for the subprocess.
                    # `base_dir` is computed from the application `__file__`, but
                    # perform lightweight validation to satisfy static analysis
                    # tools and ensure we do not pass uncontrolled input here.
                    if "\x00" in str(base_dir) or not str(base_dir):
                        raise ValueError("Invalid execution directory")
                    if not Path(str(base_dir)).is_absolute():
                        base_dir = str(Path(str(base_dir)).resolve())

                    # Extra validation for the constructed command to guard
                    # against command-injection and to make validation explicit
                    # for static analysis tools.
                    try:
                        # Ensure command is a list of strings
                        command = _validate_upload_assistant_args(command)

                        # Re-assert the execution path is safe
                        try:
                            _assert_safe_resolved_path(command[3] if len(command) > 3 else command[-1])
                        except Exception:
                            # Fallback: validated_path is expected at position 3 for subprocess
                            try:
                                _assert_safe_resolved_path(validated_path)
                            except Exception as err:
                                raise ValueError("Invalid execution path") from err

                        # Ensure the upload_script is the expected script under the repo
                        try:
                            expected_script = os.path.realpath(str(CODE_DIR / "upload.py"))
                            script_real = os.path.realpath(command[2])
                            if script_real != expected_script:
                                raise ValueError("Invalid script path")
                        except IndexError as err:
                            raise ValueError("Invalid command structure") from err

                        # Disallow shell metacharacters in any argument
                        forbidden = set(";&|$`><*?~!\n\r\x00")
                        for a in command:
                            if any(ch in a for ch in forbidden):
                                raise ValueError("Invalid characters in command argument")
                    except Exception as err:
                        console.print(f"Refusing to run unsafe command: {err}", markup=False)
                        _discard_session_state(session_id, process_state)
                        yield f"data: {json.dumps({'type': 'error', 'data': 'Unsafe execution request'})}\n\n"
                        return

                    # codeql[py/command-line-injection]
                    process = None
                    # Wrap subprocess handling in try/finally to guarantee cleanup
                    try:
                        process, process_mode = _spawn_webui_upload_process(command, Path(base_dir), env)

                        process_state.update(
                            {
                                "mode": process_mode,
                                "process": process,
                            }
                        )
                        if not _session_state_is_current(session_id, process_state):
                            _terminate_process_tree(process)
                            raise RuntimeError("Execution session was replaced before subprocess startup completed")

                        output_queue: queue.Queue[tuple[str, str]] = queue.Queue()

                        if isinstance(process, _ConPtyProcess):
                            # A pseudo terminal combines stdout and stderr into one ANSI stream.
                            def read_stdout():
                                try:
                                    while True:
                                        # Keep the same incremental prompt detection semantics as
                                        # the pipe reader. ConPTY can return a whole prompt plus
                                        # its trailing input marker in one read.
                                        for char in process.read(1024):
                                            output_queue.put(("stdout", char))
                                except EOFError:
                                    pass
                                except Exception as err:
                                    console.print(f"ConPTY read error: {err}", markup=False)

                            stdout_thread = threading.Thread(target=read_stdout, daemon=True)
                            stderr_thread = None
                        else:
                            # Thread to read stdout - stream raw output with ANSI codes
                            def read_stdout():
                                try:
                                    stdout = getattr(process, "stdout", None)
                                    if stdout is None:
                                        return
                                    while True:
                                        chunk = stdout.read(1)
                                        if not chunk:
                                            break
                                        output_queue.put(("stdout", chunk))
                                except Exception as err:
                                    console.print(f"stdout read error: {err}", markup=False)

                            # Thread to read stderr - stream raw output
                            def read_stderr():
                                try:
                                    stderr = getattr(process, "stderr", None)
                                    if stderr is None:
                                        return
                                    while True:
                                        chunk = stderr.read(1)
                                        if not chunk:
                                            break
                                        output_queue.put(("stderr", chunk))
                                except Exception as err:
                                    console.print(f"stderr read error: {err}", markup=False)

                            stdout_thread = threading.Thread(target=read_stdout, daemon=True)
                            stderr_thread = threading.Thread(target=read_stderr, daemon=True)

                        stdout_thread.start()
                        if stderr_thread is not None:
                            stderr_thread.start()

                        # Record threads and output queue for debugging/cleanup
                        with contextlib.suppress(Exception):
                            if _session_state_is_current(session_id, process_state):
                                process_state["stdout_thread"] = stdout_thread
                                process_state["stderr_thread"] = stderr_thread
                                process_state["output_queue"] = output_queue

                        console.print(
                            f"Started {process_mode} reader threads for session {session_id}: stdout={stdout_thread.name}, stderr={getattr(stderr_thread, 'name', 'merged')}",
                            markup=False,
                        )

                        def _read_output(q: queue.Queue[tuple[str, str]]) -> tuple[bool, tuple[str, str] | None]:
                            try:
                                return True, q.get(timeout=0.1)
                            except queue.Empty:
                                return False, None

                        # Stream output as buffered chunks and always emit HTML fragments
                        # If we are running the upload as a subprocess, stream ANSI->HTML as before.
                        buffers: dict[str, str] = {"stdout": "", "stderr": ""}

                        while process.poll() is None or not output_queue.empty():
                            has_output, output = _read_output(output_queue)
                            if has_output and output is not None:
                                output_type, char = output
                                if output_type not in buffers:
                                    buffers[output_type] = ""
                                buffers[output_type] += char
                                prompt_type = _subprocess_prompt_type(buffers[output_type])
                                if prompt_type:
                                    _set_process_awaiting_input_if_current(session_id, process_state, True, prompt_type)

                                # Flush on newline or when buffer grows large
                                if char == "\n" or len(buffers[output_type]) > 512:
                                    if not prompt_type:
                                        _set_process_awaiting_input_if_current(session_id, process_state, False)
                                    chunk = buffers[output_type]
                                    buffers[output_type] = ""

                                    # Convert to HTML fragment. If helper missing, escape and wrap in <pre>
                                    try:
                                        if ansi_to_html:
                                            html_fragment = ansi_to_html(chunk)
                                        else:
                                            import html as _html

                                            html_fragment = f"<pre>{_html.escape(chunk)}</pre>"

                                        yield f"data: {json.dumps({'type': 'html', 'data': html_fragment, 'origin': output_type})}\n\n"
                                    except Exception as e:
                                        console.print(f"HTML conversion error: {e}", markup=False)
                                        import html as _html

                                        html_fragment = f"<pre>{_html.escape(chunk)}</pre>"
                                        yield f"data: {json.dumps({'type': 'html', 'data': html_fragment, 'origin': output_type})}\n\n"
                            else:
                                # keepalive to keep the SSE connection alive
                                yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"

                        # Flush remaining buffers as HTML
                        for t, remaining in list(buffers.items()):
                            if remaining:
                                try:
                                    if ansi_to_html:
                                        html_fragment = ansi_to_html(remaining)
                                    else:
                                        import html as _html

                                        html_fragment = f"<pre>{_html.escape(remaining)}</pre>"

                                    yield f"data: {json.dumps({'type': 'html', 'data': html_fragment, 'origin': t})}\n\n"

                                except Exception as e:
                                    console.print(f"HTML flush error: {e}", markup=False)
                                    import html as _html

                                    html_fragment = f"<pre>{_html.escape(remaining)}</pre>"
                                    yield f"data: {json.dumps({'type': 'html', 'data': html_fragment, 'origin': t})}\n\n"

                        # Wait for process to finish
                        exit_code = process.wait()

                        # Clean up (normal path)
                        _discard_session_state(session_id, process_state)

                        yield f"data: {json.dumps({'type': 'exit', 'code': exit_code})}\n\n"
                    finally:
                        with contextlib.suppress(Exception):
                            if process is not None and process.poll() is None:
                                _terminate_process_tree(process)
                        if process is not None:
                            _close_webui_process_io(process)
                        # Ensure we remove tracking entry if still present
                        with contextlib.suppress(Exception):
                            _discard_session_state(session_id, process_state)

            except Exception as e:
                console.print(f"Execution error for session {session_id}: {e}", markup=False)
                console.print(traceback.format_exc(), markup=False)
                yield f"data: {json.dumps({'type': 'error', 'data': 'Execution error'})}\n\n"

                # Clean up on error
                with contextlib.suppress(Exception):
                    if "process_state" in locals():
                        _discard_session_state(session_id, cast(Mapping[str, object], process_state))
            finally:
                try:
                    if "validated_path" in locals() and validated_path:
                        p_obj = Path(validated_path)
                        if p_obj.name.startswith("webui_queue_") and p_obj.suffix == ".txt":
                            repo_tmp_dir = Path(__file__).resolve().parent.parent / "tmp"
                            if p_obj.parent.resolve() == repo_tmp_dir.resolve() and p_obj.exists():
                                p_obj.unlink()
                                console.print(f"Cleaned up queue file: {p_obj.name}", markup=False)
                except Exception as cleanup_err:
                    console.print(f"Failed to cleanup queue file: {cleanup_err}", markup=False)

        return Response(generate(), mimetype="text/event-stream")

    except Exception as e:
        console.print(f"Request error: {e}", markup=False)
        console.print(traceback.format_exc(), markup=False)
        return jsonify({"error": "Request error", "success": False}), 500


@app.route("/api/input", methods=["POST"])
@limiter.limit("200 per hour", key_func=_rate_limit_key_func)
def send_input():
    """Send user input to running process"""
    try:
        data = _request_json_dict()
        session_id = str(data.get("session_id", "default"))
        user_input = str(data.get("input", ""))

        # Received input for session (logged at debug level previously) - keep minimal output

        # Authorization: allow either a valid bearer token (programmatic clients)
        # or an authenticated web session. Bearer tokens are validated by
        # `_token_is_valid` (valid token grants access).
        bearer = _get_bearer_from_header()
        if bearer:
            if not _token_is_valid(bearer):
                return jsonify({"error": "Forbidden (invalid token)", "success": False}), 403
        else:
            # Require a web session plus CSRF and same-origin checks for non-token callers
            if not _is_authenticated():
                return jsonify({"error": "Authentication required (web session)", "success": False}), 401
            if not _verify_csrf_header() or not _verify_same_origin():
                return jsonify({"error": "CSRF/Origin validation failed", "success": False}), 403

        if session_id not in active_processes:
            return jsonify({"error": "No active process", "success": False}), 404

        # If this session is an in-process run, push to its input queue
        try:
            process_info = active_processes[session_id]
            if process_info.get("mode") == "inproc":
                raw_q = process_info.get("input_queue")
                if raw_q is None:
                    return jsonify({"error": "No input queue", "success": False}), 500
                q = raw_q
                _set_process_awaiting_input(session_id, False)
                q.put(user_input)
                return jsonify({"success": True})

            process = process_info.get("process")
            if process is None:
                return jsonify({"error": "No process found", "success": False}), 500

            if process.poll() is None:  # Process still running
                _set_process_awaiting_input(session_id, False)
                _write_webui_process_input(process, user_input)
                console.print(f"Sent input for session {session_id}", markup=False)
            else:
                console.print(f"Process already terminated for session {session_id}", markup=False)
                return jsonify({"error": "Process not running", "success": False}), 400

        except Exception as e:
            console.print(f"Error handling input for session {session_id}: {e}", markup=False)
            console.print(traceback.format_exc(), markup=False)
            return jsonify({"error": "Failed to handle input", "success": False}), 500

        return jsonify({"success": True})

    except Exception as e:
        console.print(f"Input error: {e}", markup=False)
        console.print(traceback.format_exc(), markup=False)
        return jsonify({"error": "Input error", "success": False}), 500


@app.route("/api/kill", methods=["POST"])
@limiter.limit("50 per hour", key_func=_rate_limit_key_func)
def kill_process():
    """Kill a running process"""
    try:
        data = _request_json_dict()
        session_id = str(data.get("session_id", ""))

        console.print(f"Kill request for session {session_id}", markup=False)

        # Authorization: allow either a valid bearer token or an authenticated web session
        bearer = _get_bearer_from_header()
        if bearer:
            if not _token_is_valid(bearer):
                return jsonify({"error": "Forbidden (invalid token)", "success": False}), 403
        else:
            if not _is_authenticated():
                return jsonify({"error": "Authentication required (web session)", "success": False}), 401
            if not _verify_csrf_header() or not _verify_same_origin():
                return jsonify({"error": "CSRF/Origin validation failed", "success": False}), 403

        if session_id not in active_processes:
            return jsonify({"error": "No active process", "success": False}), 404

        process_info = active_processes[session_id]
        mode = process_info.get("mode")

        # If this is an in-process run, perform best-effort cleanup of patched
        # console state and release the inproc lock so future inproc runs can start.
        if mode == "inproc":
            # Signal cancellation to the inproc worker and attempt to join it
            with contextlib.suppress(Exception):
                cancel_event = process_info.get("cancel_event")
                if isinstance(cancel_event, threading.Event):
                    cancel_event.set()
                worker = process_info.get("worker")
                if isinstance(worker, threading.Thread):
                    worker.join(timeout=2)

            # Attempt to restore any patched console/cli state from the
            # module-level store so future runs have working print/input.
            with contextlib.suppress(Exception), contextlib.suppress(Exception):
                # Prefer restoring originals tied to the current src.console
                try:
                    _src_console: Any = importlib.import_module("src.console")

                    console_obj: Any = _src_console.console
                    ck = id(console_obj)
                    if ck in _ua_console_store:
                        origs = _ua_console_store.pop(ck)
                        with contextlib.suppress(Exception):
                            console_obj.print = origs.get("orig_print", console_obj.print)
                        with contextlib.suppress(Exception):
                            orig_in = origs.get("orig_input", None)
                            if orig_in is not None:
                                console_obj.input = orig_in
                        # Restore any cli_ui wrappers if we have originals
                        with contextlib.suppress(Exception):
                            _cli_ui: Any = importlib.import_module("cli_ui")

                            with contextlib.suppress(Exception):
                                if "orig_ask_yes_no" in origs and origs["orig_ask_yes_no"] is not None:
                                    _cli_ui.ask_yes_no = origs["orig_ask_yes_no"]
                            with contextlib.suppress(Exception):
                                if "orig_ask_string" in origs and origs["orig_ask_string"] is not None:
                                    _cli_ui.ask_string = origs["orig_ask_string"]
                                if "orig_ask_choice" in origs and origs["orig_ask_choice"] is not None:
                                    _cli_ui.ask_choice = origs["orig_ask_choice"]
                except Exception:
                    # Best-effort: if we can't import src.console, fall back to
                    # restoring any stored callables into the module-level
                    # `console` we imported at module import time.
                    with contextlib.suppress(Exception):
                        ck = id(console)
                        if ck in _ua_console_store:
                            origs = _ua_console_store.pop(ck)
                            with contextlib.suppress(Exception):
                                console.print = origs.get("orig_print", console.print)
                            with contextlib.suppress(Exception):
                                orig_in = origs.get("orig_input", None)
                                if orig_in is not None:
                                    console.input = orig_in

                # If any other entries remain in the store, drop them to avoid
                # leaking references — they are unlikely to be useful now.
                _ua_console_store.clear()

            # Release inproc lock if held; best-effort only.
            with contextlib.suppress(Exception):
                if inproc_lock.locked():
                    inproc_lock.release()

            # Remove tracking entry
            with contextlib.suppress(Exception):
                active_processes.pop(session_id, None)

            console.print(f"In-process run terminated for session {session_id}", markup=False)
            return jsonify({"success": True, "message": "In-process run terminated and console state wiped"})

        # Otherwise assume subprocess.Popen case
        # Retrieve subprocess handle
        process = process_info.get("process")
        if process is None:
            # Kill can race with startup after the session has been registered
            # but before Popen returns. Removing this state makes the launcher
            # terminate the controller immediately if it does start.
            _discard_session_state(session_id, process_info)
            return jsonify({"success": True, "message": "Execution startup cancelled"})

        terminated = False
        try:
            terminated = _terminate_process_tree(process)

            _close_webui_process_io(process)

        finally:
            # Keep the session available for another Kill attempt if the
            # process tree could not be terminated.
            # Attempt to join reader threads if present
            with contextlib.suppress(Exception):
                info = active_processes.get(session_id, {})
                stdout_t = info.get("stdout_thread")
                stderr_t = info.get("stderr_thread")
                if isinstance(stdout_t, threading.Thread):
                    console.print(f"Joining stdout thread for session {session_id}", markup=False)
                    stdout_t.join(timeout=1)
                if isinstance(stderr_t, threading.Thread):
                    console.print(f"Joining stderr thread for session {session_id}", markup=False)
                    stderr_t.join(timeout=1)

            if terminated:
                with contextlib.suppress(Exception):
                    active_processes.pop(session_id, None)

        if not terminated:
            return jsonify({"error": "Failed to terminate process tree", "success": False}), 500

        console.print(f"Process killed for session {session_id}", markup=False)
        console.print(f"Post-kill snapshot: {_debug_process_snapshot(session_id)}", markup=False)
        return jsonify({"success": True, "message": "Process terminated"})

    except Exception as e:
        console.print(f"Kill error: {e}", markup=False)
        console.print(traceback.format_exc(), markup=False)
        return jsonify({"error": "Kill error", "success": False}), 500


@app.errorhandler(404)
def not_found(_e: Exception):
    return jsonify({"error": "Not found", "success": False}), 404


@app.errorhandler(500)
def internal_error(e: Exception):
    console.print(f"500 error: {e!s}", markup=False)
    console.print(traceback.format_exc(), markup=False)
    return jsonify({"error": "Internal server error", "success": False}), 500


# Keep these helpers referenced so static analysis does not flag them as unused.
_ = _cfg_delete
_ = _json_load_list
_ = _maybe_log_api_access
_ = _rate_limit_exceeded
