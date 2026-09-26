"""Privacy-preserving aggregate usage statistics for Upload Assistant."""

from __future__ import annotations

import asyncio
import os
import re
import sqlite3
import threading
from collections import defaultdict
from collections.abc import Iterable, Mapping
from contextlib import closing
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from src.app_paths import DATA_DIR

_SCHEMA_VERSION = "1"
_DIMENSION_RE = re.compile(r"[^A-Za-z0-9_.:-]+")
_mode: ContextVar[str] = ContextVar("ua_stats_mode", default="real")
_category: ContextVar[str] = ContextVar("ua_stats_category", default="")
_enabled = False
_configuration_lock = threading.Lock()
_record_lock = threading.Lock()
_schema_lock = threading.Lock()
_initialized_paths: set[Path] = set()


def stats_collection_enabled(config: Mapping[str, Any] | None) -> bool:
    """Return whether aggregate collection is explicitly enabled."""
    if not isinstance(config, Mapping):
        return False
    default_value = config.get("DEFAULT")
    if not isinstance(default_value, Mapping):
        return False
    default = cast(Mapping[str, Any], default_value)
    return default.get("stats_enabled") is True


def configure_stats(config: Mapping[str, Any] | None) -> None:
    """Apply the current run configuration without retaining the config itself."""
    global _enabled
    with _configuration_lock:
        _enabled = stats_collection_enabled(config)


def set_stats_context(*, debug: bool | None = None, category: str | None = None) -> None:
    if debug is not None:
        _mode.set("debug" if debug else "real")
    if category is not None:
        _category.set(_dimension(category))


def completed_item_outcome(statuses: Iterable[Mapping[str, Any]]) -> str:
    """Classify a completed item from definitive per-destination results."""
    results = list(statuses)
    if any(status.get("upload_success") is True for status in results):
        return "success"
    if any(status.get("upload_success") is False for status in results):
        return "error"
    return "no_upload"


def _dimension(value: object, *, default: str = "") -> str:
    cleaned = _DIMENSION_RE.sub("_", str(value or "").strip())[:80].strip("_")
    return cleaned or default


def _database_path(state_dir: str | Path | None = None) -> Path:
    return Path(state_dir) / "data" / "stats.sqlite3" if state_dir is not None else DATA_DIR / "stats.sqlite3"


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5)
    db.execute("PRAGMA busy_timeout = 5000")
    with _schema_lock:
        if path not in _initialized_paths:
            db.execute("PRAGMA journal_mode = WAL")
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS stats_daily (
                    day TEXT NOT NULL,
                    family TEXT NOT NULL,
                    service TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    category TEXT NOT NULL,
                    source TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    duration_ms INTEGER NOT NULL DEFAULT 0,
                    bytes INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (day, family, service, operation, outcome, category, source, mode)
                )
                """
            )
            db.execute("CREATE TABLE IF NOT EXISTS stats_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("INSERT OR IGNORE INTO stats_meta VALUES ('schema_version', ?)", (_SCHEMA_VERSION,))
            db.commit()
            _initialized_paths.add(path)
    return db


def record_event(
    family: str,
    *,
    service: str = "",
    operation: str = "",
    outcome: str = "success",
    category: str | None = None,
    source: str | None = None,
    mode: str | None = None,
    count: int = 1,
    duration_ms: int | float = 0,
    bytes_count: int = 0,
    state_dir: str | Path | None = None,
) -> None:
    """Record one aggregate event. Statistics must never break the main flow."""
    if not _enabled or count <= 0:
        return
    dimensions = (
        datetime.now(UTC).date().isoformat(),
        _dimension(family, default="unknown"),
        _dimension(service),
        _dimension(operation),
        _dimension(outcome, default="unknown"),
        _dimension(category) if category is not None else _category.get(),
        _dimension(source or os.environ.get("UA_STATS_SOURCE", "cli"), default="cli"),
        "debug" if (mode or _mode.get()).lower() == "debug" else "real",
    )
    try:
        with _record_lock, closing(_connect(_database_path(state_dir))) as db, db:
            db.execute(
                """
                INSERT INTO stats_daily
                    (day, family, service, operation, outcome, category, source, mode, count, duration_ms, bytes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (day, family, service, operation, outcome, category, source, mode)
                DO UPDATE SET
                    count = count + excluded.count,
                    duration_ms = duration_ms + excluded.duration_ms,
                    bytes = bytes + excluded.bytes
                """,
                (*dimensions, int(count), max(0, round(duration_ms)), max(0, int(bytes_count))),
            )
    except OSError, sqlite3.Error, ValueError, TypeError:
        return


async def record_event_async(family: str, **kwargs: Any) -> None:
    """Record an aggregate event without blocking the event loop."""
    if not _enabled:
        return
    await asyncio.to_thread(record_event, family, **kwargs)


def _range_start(period: str, today: datetime) -> str | None:
    days = {"7d": 7, "30d": 30, "90d": 90}.get(period)
    return (today.date() - timedelta(days=days - 1)).isoformat() if days else None


def _empty_payload(period: str, mode: str, generated_at: str) -> dict[str, Any]:
    return {
        "success": True,
        "range": period,
        "mode": mode,
        "generated_at": generated_at,
        "period": {"from": None, "to": generated_at[:10]},
        "overview": {
            "items_completed": 0,
            "uploads": 0,
            "upload_attempts": 0,
            "upload_success_rate": 0.0,
            "torrents_created": 0,
            "nzbs_created": 0,
            "api_operations": 0,
            "cache_hit_rate": 0.0,
        },
        "timeline": [],
        "items": {"success": 0, "no_upload": 0, "error": 0},
        "uploads": {"by_destination": [], "by_category": []},
        "artifacts": [],
        "cache": {"hits": 0, "misses": 0, "writes": 0, "bypasses": 0, "bytes_written": 0, "hit_rate": 0.0, "by_provider": []},
        "api": {"total": 0, "requests": 0, "successes": 0, "errors": 0, "by_service": []},
        "sources": [],
    }


def get_empty_stats(period: str = "30d", mode: str = "real") -> dict[str, Any]:
    """Return the stable response shape without reading stored aggregates."""
    if period not in {"7d", "30d", "90d", "all"}:
        raise ValueError("range must be one of: 7d, 30d, 90d, all")
    if mode not in {"real", "debug"}:
        raise ValueError("mode must be one of: real, debug")
    now = datetime.now(UTC)
    payload = _empty_payload(period, mode, now.isoformat())
    payload["period"]["from"] = _range_start(period, now)
    return payload


def get_stats(period: str = "30d", mode: str = "real", state_dir: str | Path | None = None) -> dict[str, Any]:
    payload = get_empty_stats(period, mode)
    now = datetime.fromisoformat(str(payload["generated_at"]))
    start = payload["period"]["from"]
    path = _database_path(state_dir)
    if not path.is_file():
        return payload
    try:
        with closing(_connect(path)) as db:
            query = "SELECT day, family, service, operation, outcome, category, source, count, duration_ms, bytes FROM stats_daily WHERE mode = ?"
            parameters: list[object] = [mode]
            if start:
                query += " AND day >= ?"
                parameters.append(start)
            rows = db.execute(query, parameters).fetchall()
    except OSError, sqlite3.Error:
        return payload

    if not rows:
        return payload
    payload["period"]["from"] = start or min(row[0] for row in rows)

    timeline: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    destinations: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    categories: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    artifacts: dict[tuple[str, str, str], int] = defaultdict(int)
    cache_services: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    api_services: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    sources: dict[str, int] = defaultdict(int)
    overview = payload["overview"]

    for day, family, service, operation, outcome, category, source, count, duration_ms, bytes_count in rows:
        count = int(count)
        if family == "item":
            if operation == "completed":
                overview["items_completed"] += count
                if outcome in payload["items"]:
                    payload["items"][outcome] += count
                timeline[day]["items"] += count
                sources[source] += count
        elif family == "upload":
            bucket = destinations[(service, operation)]
            normalized_outcome = "skipped" if outcome.startswith("skipped:") else outcome
            bucket[normalized_outcome] += count
            if outcome.startswith("skipped:"):
                bucket[f"reason:{outcome.partition(':')[2] or 'rule'}"] += count
            bucket["duration_ms"] += int(duration_ms)
            if outcome in {"success", "error"}:
                bucket["attempts"] += count
                overview["upload_attempts"] += count
            if outcome == "success":
                overview["uploads"] += count
                timeline[day]["uploads"] += count
            if category:
                categories[category][normalized_outcome] += count
        elif family == "artifact":
            artifacts[(service, operation, category)] += count
            if service == "torrent" and operation == "created" and outcome == "success":
                overview["torrents_created"] += count
            if service == "nzb" and operation == "created" and outcome == "success":
                overview["nzbs_created"] += count
        elif family == "cache":
            cache_services[service][outcome] += count
            cache_services[service]["bytes"] += int(bytes_count)
            timeline[day][f"cache_{outcome}"] += count
        elif family == "api":
            api_services[(service, operation)][outcome] += count
            api_services[(service, operation)]["duration_ms"] += int(duration_ms)
            api_services[(service, operation)]["bytes"] += int(bytes_count)
            overview["api_operations"] += count
            timeline[day]["api"] += count

    overview["upload_success_rate"] = round(100 * overview["uploads"] / overview["upload_attempts"], 1) if overview["upload_attempts"] else 0.0
    cache_totals: defaultdict[str, int] = defaultdict(int)
    for values in cache_services.values():
        for key, value in values.items():
            cache_totals[key] += value
    cache_reads = cache_totals["hit"] + cache_totals["miss"]
    cache_hit_rate = round(100 * cache_totals["hit"] / cache_reads, 1) if cache_reads else 0.0
    overview["cache_hit_rate"] = cache_hit_rate
    payload["cache"].update(
        hits=cache_totals["hit"],
        misses=cache_totals["miss"],
        writes=cache_totals["write"],
        bypasses=cache_totals["bypass"],
        bytes_written=cache_totals["bytes"],
        hit_rate=cache_hit_rate,
        by_provider=[
            {
                "provider": name,
                "hits": values["hit"],
                "misses": values["miss"],
                "writes": values["write"],
                "bypasses": values["bypass"],
                "bytes_written": values["bytes"],
                "hit_rate": round(100 * values["hit"] / (values["hit"] + values["miss"]), 1) if values["hit"] + values["miss"] else 0.0,
            }
            for name, values in sorted(cache_services.items(), key=lambda item: -(item[1]["hit"] + item[1]["miss"]))
        ],
    )
    payload["uploads"]["by_destination"] = [
        {
            "destination": service,
            "type": destination_type,
            "attempts": values["attempts"],
            "successes": values["success"],
            "errors": values["error"],
            "skipped": values["skipped"],
            "success_rate": round(100 * values["success"] / values["attempts"], 1) if values["attempts"] else 0.0,
            "average_duration_ms": round(values["duration_ms"] / values["attempts"]) if values["attempts"] else 0,
            "skip_reasons": {key.removeprefix("reason:"): value for key, value in values.items() if key.startswith("reason:")},
        }
        for (service, destination_type), values in sorted(destinations.items(), key=lambda item: -item[1]["success"])
    ]
    payload["uploads"]["by_category"] = [
        {"category": name, "successes": values["success"], "errors": values["error"], "skipped": values["skipped"]}
        for name, values in sorted(categories.items(), key=lambda item: -item[1]["success"])
    ]
    payload["artifacts"] = [
        {"type": artifact_type, "operation": operation, "variant": variant, "count": count} for (artifact_type, operation, variant), count in sorted(artifacts.items())
    ]
    api_successes = sum(values["success"] for values in api_services.values())
    api_errors = sum(values["error"] for values in api_services.values())
    api_requests = sum(values["request"] or (values["success"] + values["error"]) for values in api_services.values())
    overview["api_operations"] = api_requests
    payload["api"].update(
        total=overview["api_operations"],
        requests=api_requests,
        successes=api_successes,
        errors=api_errors,
        by_service=[
            {
                "service": service,
                "operation": operation,
                "requests": values["request"] or (values["success"] + values["error"]),
                "successes": values["success"],
                "errors": values["error"],
                "average_duration_ms": round(values["duration_ms"] / (values["success"] + values["error"])) if values["success"] + values["error"] else 0,
                "bytes": values["bytes"],
            }
            for (service, operation), values in sorted(
                api_services.items(),
                key=lambda item: -(item[1]["request"] or (item[1]["success"] + item[1]["error"])),
            )
        ],
    )
    first_day = datetime.fromisoformat(str(payload["period"]["from"])).date()
    timeline_rows: list[dict[str, Any]] = []
    cursor = first_day
    while cursor <= now.date():
        values = timeline[cursor.isoformat()]
        timeline_rows.append(
            {
                "date": cursor.isoformat(),
                "items": values["items"],
                "uploads": values["uploads"],
                "api": values["api"],
                "cache_hit": values["cache_hit"],
                "cache_miss": values["cache_miss"],
            }
        )
        cursor += timedelta(days=1)
    payload["timeline"] = timeline_rows
    payload["sources"] = [{"source": source, "count": count} for source, count in sorted(sources.items())]
    return payload


def reset_stats(state_dir: str | Path | None = None) -> str:
    """Clear all aggregate buckets and record the reset boundary."""
    reset_at = datetime.now(UTC).isoformat()
    path = _database_path(state_dir)
    with _record_lock, closing(_connect(path)) as db, db:
        db.execute("DELETE FROM stats_daily")
        db.execute("INSERT OR REPLACE INTO stats_meta VALUES ('reset_at', ?)", (reset_at,))
    return reset_at
