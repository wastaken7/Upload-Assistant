"""Shared, advisory tracker API-key expiry status for the CLI and WebUI."""

from __future__ import annotations

import hashlib
import math
import sqlite3
import threading
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from src.app_paths import STATE_DIR
from src.console import logger

WARNING_DAYS = 14
# LST documents that an omitted header on an authenticated JSON response means
# no expiry. Other trackers must explicitly report a date or JSON null.
_OMITTED_HEADER_MEANS_NO_EXPIRY = {"LST"}
_warned: set[str] = set()
_warning_lock = threading.Lock()


def _date(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
        return parsed.astimezone(UTC) if parsed.tzinfo is not None else None
    except ValueError, OverflowError:
        return None


def _identity(tracker: str, api_key: str, base_url: str) -> str:
    return hashlib.sha256("\0".join((tracker.upper(), base_url.rstrip("/"), api_key.strip())).encode()).hexdigest()


def _cache_path(state_dir: str | Path | None) -> Path:
    return Path(state_dir or STATE_DIR) / "data" / "api_key_expiry.sqlite3"


def _status(expires_at: str | None, checked_at: str | None, now: datetime | None = None) -> dict[str, Any]:
    status: dict[str, Any] = {"state": "unknown", "expires_at": None, "checked_at": checked_at, "days_remaining": None}
    if not checked_at:
        return status
    if expires_at is None:
        status["state"] = "no_expiry"
        return status
    expiry = _date(expires_at)
    if expiry is None:
        return status
    remaining = expiry - (now or datetime.now(UTC))
    status.update(
        state="expired" if remaining <= timedelta(0) else "expiring" if remaining <= timedelta(days=WARNING_DAYS) else "valid",
        expires_at=expiry.isoformat(),
        days_remaining=math.ceil(remaining.total_seconds() / 86400),
    )
    return status


def get_api_key_expiry(tracker: str, api_key: str, base_url: str, state_dir: str | Path | None = None, *, now: datetime | None = None) -> dict[str, Any]:
    """Read only the status of this exact key; never return the key or its hash."""
    unknown = _status(None, None)
    path = _cache_path(state_dir)
    if not api_key.strip() or not path.is_file():
        return unknown
    try:
        with closing(sqlite3.connect(path, timeout=2)) as db:
            row = db.execute("SELECT expires_at, checked_at FROM api_key_expiry WHERE identity = ?", (_identity(tracker, api_key, base_url),)).fetchone()
        return _status(*row, now=now) if row else unknown
    except sqlite3.Error, OSError:
        return unknown


def record_api_key_expiry(
    tracker: str,
    api_key: str,
    base_url: str,
    response: Any,
    state_dir: str | Path | None = None,
    *,
    payload: object = None,
) -> dict[str, Any] | None:
    """Observe successful authenticated responses without persisting secrets.

    Missing/invalid metadata and failed requests preserve the previous record.
    A JSON payload is supplied after parsing by the caller; HTML redirects must
    not turn an unknown or expired key into a non-expiring one.
    """
    if not api_key.strip() or not 200 <= response.status_code < 300:
        return None
    headers = {str(key).lower(): value for key, value in getattr(response, "headers", {}).items()}
    header = "x-api-key-expires-at"
    credential = payload.get("api_key") if isinstance(payload, dict) else None
    if header in headers:
        expiry = _date(headers[header])
        if expiry is None:
            return None
    elif isinstance(credential, dict) and "expires_at" in credential:
        raw = credential["expires_at"]
        expiry = _date(raw)
        if raw is not None and expiry is None:
            return None
    elif tracker.upper() in _OMITTED_HEADER_MEANS_NO_EXPIRY and isinstance(payload, dict):
        expiry = None
    else:
        return None

    checked_at = datetime.now(UTC).isoformat()
    expires_at = expiry.isoformat() if expiry else None
    status = _status(expires_at, checked_at)
    try:
        path = _cache_path(state_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path, timeout=2)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS api_key_expiry (identity TEXT PRIMARY KEY, expires_at TEXT, checked_at TEXT NOT NULL)")
            db.execute(
                "INSERT OR REPLACE INTO api_key_expiry VALUES (?, ?, ?)",
                (_identity(tracker, api_key, base_url), expires_at, checked_at),
            )
    except sqlite3.Error, OSError:
        # A full or read-only state directory must not prevent an upload. The
        # caller can still display this observation during the current run.
        pass
    return status


def observe_tracker_response(config: dict[str, Any], meta: Any, tracker: str, response: Any, payload: object = None) -> None:
    """Record shared tracker setup/metadata requests and warn selected trackers."""
    from src.trackersetup import tracker_class_map

    tracker_class = tracker_class_map.get(tracker)
    if not tracker_class or not 200 <= getattr(response, "status_code", 0) < 300:
        return
    if payload is None:
        try:
            payload = response.json()
        except ValueError:
            payload = None
    api_key = str(config.get("TRACKERS", {}).get(tracker, {}).get("api_key") or "").strip()
    base_url = getattr(tracker_class, "base_url", "")
    status = record_api_key_expiry(tracker, api_key, base_url, response, meta.base_dir, payload=payload)
    if status is not None and tracker in (meta.trackers or []):
        warn_api_key_expiry(tracker, api_key, base_url, meta.base_dir, status=status)


def reset_api_key_expiry_warnings() -> None:
    """Start a new upload run, including when the process is reused by WebUI."""
    with _warning_lock:
        _warned.clear()


def warn_api_key_expiry(
    tracker: str,
    api_key: str,
    base_url: str,
    state_dir: str | Path | None = None,
    *,
    status: dict[str, Any] | None = None,
) -> None:
    status = status if status is not None else get_api_key_expiry(tracker, api_key, base_url, state_dir)
    if status["state"] not in {"expiring", "expired"}:
        return
    identity = _identity(tracker, api_key, base_url)
    with _warning_lock:
        if identity in _warned:
            return
        _warned.add(identity)
    expiry = _date(status["expires_at"])
    if expiry is None:
        return
    date_label = expiry.strftime("%d %B %Y at %H:%M UTC")
    if status["state"] == "expired":
        message = f"API key expired on {date_label}."
    else:
        days = status["days_remaining"]
        remaining = "less than a day" if expiry - datetime.now(UTC) < timedelta(days=1) else f"{days} days"
        message = f"API key expires in {remaining} ({date_label})."
    logger.warning(f"{tracker}: {message} Replace it in your tracker configuration or credential source.", extra={"markup": False})
