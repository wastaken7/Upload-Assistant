"""Privacy-preserving aggregate usage statistics for Upload Assistant."""

from __future__ import annotations

import asyncio
import os
import re
import sqlite3
import threading
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping
from contextlib import closing
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from src.app_paths import DATA_DIR

_SCHEMA_VERSION = "1"
_PERIOD_DAYS = {"7d": 7, "30d": 30, "90d": 90, "1y": 365}
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


def media_profile_dimensions(meta: Any) -> list[tuple[str, str]]:
    """Return low-cardinality, privacy-safe media dimensions for one item."""
    category = str(getattr(meta, "category", "") or "").upper()
    dimensions: list[tuple[str, str]] = []

    def add(name: str, value: object) -> None:
        normalized = _dimension(value)
        if normalized:
            dimensions.append((name, normalized))

    if category in {"MOVIE", "TV", "FANRES", "XXX", "SPORTS"}:
        add("resolution", getattr(meta, "resolution", ""))
        add("release_type", getattr(meta, "type", ""))
        add("video_codec", _video_codec_bucket(getattr(meta, "video_codec", "") or getattr(meta, "video", "")))
        add("audio_codec", _audio_codec_bucket(getattr(meta, "audio", "")))
        add("hdr", _hdr_bucket(getattr(meta, "hdr", "") or getattr(meta, "HDR", "")))
    elif category == "MUSIC":
        add("release_type", getattr(meta, "music_release_type", ""))
        add("media", getattr(meta, "music_media", "") or getattr(meta, "source", ""))
        add("audio_codec", _audio_codec_bucket(getattr(meta, "audio", "") or getattr(meta, "type", "")))
    elif category == "BOOK":
        kind = (
            "audiobook"
            if getattr(meta, "audiobook", False)
            else "comic"
            if getattr(meta, "comic", False)
            else "manga"
            if getattr(meta, "manga", False)
            else "magazine"
            if getattr(meta, "magazine", False)
            else "newspaper"
            if getattr(meta, "newspaper", False)
            else "ebook"
        )
        add("book_type", kind)
        add("format", getattr(meta, "type", "") or getattr(meta, "format", ""))
        if kind == "audiobook":
            add("audio_codec", _audio_codec_bucket(getattr(meta, "audio", "") or getattr(meta, "type", "")))
    elif category == "GAME":
        add("platform", getattr(meta, "platform", ""))
        add("release_type", getattr(meta, "game_release_type", "") or getattr(meta, "game_subcategory", ""))
    return dimensions


def _video_codec_bucket(value: object) -> str:
    text = str(value or "").upper()
    if "AV1" in text:
        return "AV1"
    if "HEVC" in text or "H.265" in text or "X265" in text:
        return "HEVC"
    if "AVC" in text or "H.264" in text or "X264" in text:
        return "AVC"
    if "MPEG-2" in text or "MPEG2" in text:
        return "MPEG-2"
    return str(value or "")


def _audio_codec_bucket(value: object) -> str:
    text = str(value or "").upper()
    for marker, label in (
        ("ATMOS", "Dolby Atmos"),
        ("TRUEHD", "TrueHD"),
        ("DTS-HD MA", "DTS-HD MA"),
        ("DTS:X", "DTS:X"),
        ("FLAC", "FLAC"),
        ("E-AC-3", "Dolby Digital Plus"),
        ("DD+", "Dolby Digital Plus"),
        ("AC-3", "Dolby Digital"),
        ("AAC", "AAC"),
        ("OPUS", "Opus"),
        ("MP3", "MP3"),
    ):
        if marker in text:
            return label
    return str(value or "")


def _hdr_bucket(value: object) -> str:
    text = str(value or "").upper()
    if "DOLBY VISION" in text or re.search(r"(^|\W)DV($|\W)", text):
        return "Dolby Vision"
    if "HDR10+" in text or "HDR10PLUS" in text:
        return "HDR10+"
    if "HDR" in text:
        return "HDR10"
    return "SDR"


async def record_media_profile_async(meta: Any) -> None:
    """Record one item's category-appropriate technical profile."""
    category = str(getattr(meta, "category", "") or "")
    size = max(0, int(getattr(meta, "source_size", 0) or 0))
    for dimension, value in media_profile_dimensions(meta):
        await record_event_async("media", service=dimension, operation=value, category=category, bytes_count=size)


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
    for attempt in range(4):
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
            return
        except sqlite3.OperationalError as exc:
            if attempt == 3 or not any(reason in str(exc).lower() for reason in ("busy", "locked")):
                return
            time.sleep(0.05 * (attempt + 1))
        except OSError, sqlite3.Error, ValueError, TypeError:
            return


async def record_event_async(family: str, **kwargs: Any) -> None:
    """Record an aggregate event without blocking the event loop."""
    if not _enabled:
        return
    await asyncio.to_thread(record_event, family, **kwargs)


def _range_start(period: str, today: datetime) -> str | None:
    days = _PERIOD_DAYS.get(period)
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
            "uploaded_bytes": 0,
            "processed_bytes": 0,
            "average_item_bytes": 0,
            "duplicate_preventions": 0,
            "pioneering_rate": 0.0,
            "hashing_bytes_avoided": 0,
        },
        "timeline": [],
        "heatmap": [],
        "comparison": {"items_completed_pct": None, "uploads_pct": None, "cache_hit_rate_delta": None},
        "items": {"success": 0, "no_upload": 0, "error": 0},
        "uploads": {"by_destination": [], "by_category": []},
        "media": {"categories": [], "dimensions": []},
        "artifacts": [],
        "cache": {"hits": 0, "misses": 0, "writes": 0, "bypasses": 0, "bytes_written": 0, "hit_rate": 0.0, "by_provider": []},
        "api": {"total": 0, "requests": 0, "successes": 0, "errors": 0, "by_service": []},
        "sources": [],
    }


def get_empty_stats(period: str = "30d", mode: str = "real") -> dict[str, Any]:
    """Return the stable response shape without reading stored aggregates."""
    if period not in {*_PERIOD_DAYS, "all"}:
        raise ValueError("range must be one of: 7d, 30d, 90d, 1y, all")
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
            heatmap_start = (now.date() - timedelta(days=364)).isoformat()
            heatmap_rows = db.execute(
                """
                SELECT day, SUM(count) FROM stats_daily
                WHERE mode = ? AND family = 'item' AND operation = 'completed' AND day >= ?
                GROUP BY day ORDER BY day
                """,
                (mode, heatmap_start),
            ).fetchall()
            prior_rows: list[tuple[str, str, str, int]] = []
            days = _PERIOD_DAYS.get(period)
            if days:
                current_start = now.date() - timedelta(days=days - 1)
                prior_end = current_start - timedelta(days=1)
                prior_start = prior_end - timedelta(days=days - 1)
                prior_rows = db.execute(
                    """
                    SELECT family, operation, outcome, SUM(count) FROM stats_daily
                    WHERE mode = ? AND day >= ? AND day <= ?
                    GROUP BY family, operation, outcome
                    """,
                    (mode, prior_start.isoformat(), prior_end.isoformat()),
                ).fetchall()
    except OSError, sqlite3.Error:
        return payload

    payload["heatmap"] = [{"date": day, "count": int(count)} for day, count in heatmap_rows]
    if not rows:
        return payload
    payload["period"]["from"] = start or min(row[0] for row in rows)

    timeline: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    destinations: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    categories: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    artifacts: dict[tuple[str, str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    cache_services: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    api_services: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    media_dimensions: dict[tuple[str, str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
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
                timeline[day]["processed_bytes"] += int(bytes_count)
                overview["processed_bytes"] += int(bytes_count)
                sources[source] += count
        elif family == "upload":
            bucket = destinations[(service, operation)]
            normalized_outcome = "skipped" if outcome.startswith("skipped:") else outcome
            bucket[normalized_outcome] += count
            if outcome.startswith("skipped:"):
                bucket[f"reason:{outcome.partition(':')[2] or 'rule'}"] += count
            bucket["duration_ms"] += int(duration_ms)
            bucket["bytes"] += int(bytes_count)
            if outcome in {"success", "error"}:
                bucket["attempts"] += count
                overview["upload_attempts"] += count
            if outcome == "success":
                overview["uploads"] += count
                timeline[day]["uploads"] += count
                timeline[day]["uploaded_bytes"] += int(bytes_count)
                overview["uploaded_bytes"] += int(bytes_count)
            elif outcome == "error":
                timeline[day]["upload_errors"] += count
            if category:
                categories[category][normalized_outcome] += count
                categories[category]["bytes"] += int(bytes_count)
        elif family == "artifact":
            bucket = artifacts[(service, operation, category)]
            bucket["count"] += count
            bucket["bytes"] += int(bytes_count)
            if service == "torrent" and operation == "created" and outcome == "success":
                overview["torrents_created"] += count
            if service == "nzb" and operation == "created" and outcome == "success":
                overview["nzbs_created"] += count
            if service == "torrent" and operation == "reused" and outcome == "success":
                overview["hashing_bytes_avoided"] += int(bytes_count)
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
        elif family == "media":
            bucket = media_dimensions[(category, service, operation)]
            bucket["count"] += count
            bucket["bytes"] += int(bytes_count)

    overview["upload_success_rate"] = round(100 * overview["uploads"] / overview["upload_attempts"], 1) if overview["upload_attempts"] else 0.0
    overview["average_item_bytes"] = round(overview["processed_bytes"] / overview["items_completed"]) if overview["items_completed"] else 0
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
            "bytes": values["bytes"],
            "skip_reasons": {key.removeprefix("reason:"): value for key, value in values.items() if key.startswith("reason:")},
        }
        for (service, destination_type), values in sorted(destinations.items(), key=lambda item: -item[1]["success"])
    ]
    payload["uploads"]["by_category"] = [
        {"category": name, "successes": values["success"], "errors": values["error"], "skipped": values["skipped"], "bytes": values["bytes"]}
        for name, values in sorted(categories.items(), key=lambda item: -item[1]["success"])
    ]
    payload["artifacts"] = [
        {"type": artifact_type, "operation": operation, "variant": variant, "count": values["count"], "bytes": values["bytes"]}
        for (artifact_type, operation, variant), values in sorted(artifacts.items())
    ]
    duplicate_preventions = sum(values["reason:dupe"] for values in destinations.values())
    pioneering_total = overview["uploads"] + duplicate_preventions
    overview["duplicate_preventions"] = duplicate_preventions
    overview["pioneering_rate"] = round(100 * overview["uploads"] / pioneering_total, 1) if pioneering_total else 0.0
    payload["media"]["categories"] = sorted({category for category, _dimension_name, _value in media_dimensions if category})
    payload["media"]["dimensions"] = [
        {"category": category, "dimension": dimension, "value": value, "count": totals["count"], "bytes": totals["bytes"]}
        for (category, dimension, value), totals in sorted(media_dimensions.items())
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
                "upload_errors": values["upload_errors"],
                "uploaded_bytes": values["uploaded_bytes"],
                "processed_bytes": values["processed_bytes"],
            }
        )
        cursor += timedelta(days=1)
    payload["timeline"] = timeline_rows
    payload["sources"] = [{"source": source, "count": count} for source, count in sorted(sources.items())]
    if prior_rows:
        prior: defaultdict[tuple[str, str, str], int] = defaultdict(int)
        for family, operation, outcome, count in prior_rows:
            prior[(family, operation, outcome)] += int(count)
        prior_items = sum(value for (family, operation, _outcome), value in prior.items() if family == "item" and operation == "completed")
        prior_uploads = sum(value for (family, _operation, outcome), value in prior.items() if family == "upload" and outcome == "success")
        prior_cache_hits = sum(value for (family, _operation, outcome), value in prior.items() if family == "cache" and outcome == "hit")
        prior_cache_misses = sum(value for (family, _operation, outcome), value in prior.items() if family == "cache" and outcome == "miss")
        prior_cache_reads = prior_cache_hits + prior_cache_misses
        prior_cache_rate = 100 * prior_cache_hits / prior_cache_reads if prior_cache_reads else 0.0
        payload["comparison"] = {
            "items_completed_pct": _percent_change(overview["items_completed"], prior_items),
            "uploads_pct": _percent_change(overview["uploads"], prior_uploads),
            "cache_hit_rate_delta": round(overview["cache_hit_rate"] - prior_cache_rate, 1) if prior_cache_reads else None,
        }
    return payload


def _percent_change(current: int, previous: int) -> float | None:
    """Return a bounded-period percentage change when a baseline exists."""
    return round(100 * (current - previous) / previous, 1) if previous else None


def reset_stats(state_dir: str | Path | None = None) -> str:
    """Clear all aggregate buckets and record the reset boundary."""
    reset_at = datetime.now(UTC).isoformat()
    path = _database_path(state_dir)
    with _record_lock, closing(_connect(path)) as db, db:
        db.execute("DELETE FROM stats_daily")
        db.execute("INSERT OR REPLACE INTO stats_meta VALUES ('reset_at', ?)", (reset_at,))
    return reset_at
