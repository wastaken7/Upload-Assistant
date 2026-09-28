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
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from src.app_paths import DATA_DIR

_SCHEMA_VERSION = "2"
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
        add("hdr", _hdr_bucket(meta))
        streaming_service = getattr(meta, "service_longname", "") or getattr(meta, "service", "")
        release_source = f"{getattr(meta, 'type', '')} {getattr(meta, 'source', '')}".upper()
        if streaming_service:
            add("streaming_service", streaming_service)
        elif "WEB" in release_source:
            add("streaming_service", "Unknown")
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


def _primary_video_track(meta: Any) -> Mapping[str, Any]:
    mediainfo = getattr(meta, "mediainfo", {})
    if not isinstance(mediainfo, Mapping):
        return {}
    media = mediainfo.get("media", {})
    if not isinstance(media, Mapping):
        return {}
    tracks = media.get("track", [])
    if not isinstance(tracks, list):
        return {}
    return next((track for track in tracks if isinstance(track, Mapping) and track.get("@type") == "Video"), {})


def _hdr_bucket(value: object) -> str:
    meta = value if not isinstance(value, (str, bytes)) else None
    track = _primary_video_track(meta) if meta is not None else {}
    raw_hdr = getattr(meta, "hdr", "") or getattr(meta, "HDR", "") if meta is not None else value
    profile = str(track.get("HDR_Format_Profile", "") or "")
    compatibility = " ".join(str(track.get(key, "") or "") for key in ("HDR_Format_Compatibility", "HDR_Format_String", "HDR_Format"))
    text = f"{raw_hdr} {profile} {compatibility}".upper()
    has_dv = "DOLBY VISION" in text or "DVHE." in text or re.search(r"(^|\W)DV($|\W)", text)
    has_hdr10_plus = "HDR10+" in text or "HDR10PLUS" in text or "SMPTE ST 2094 APP 4" in text
    has_hdr10 = "HDR10" in text or bool(re.search(r"(^|\W)HDR($|\W)", text))
    if has_dv:
        match = re.search(r"DVHE\.(\d{2})", profile.upper())
        label = f"Dolby Vision Profile {int(match.group(1))}" if match else "Dolby Vision - profile unknown"
        if has_hdr10_plus:
            return f"{label} + HDR10+"
        if has_hdr10:
            return f"{label} + HDR10"
        return label
    if has_hdr10_plus:
        return "HDR10+"
    if has_hdr10:
        return "HDR10"
    if "HLG" in text:
        return "HLG"
    if "PQ10" in text or "WCG" in text:
        return "PQ10/WCG"
    return "SDR"


async def record_media_profile_async(meta: Any, *, destination: str = "") -> None:
    """Record one item's category-appropriate technical profile."""
    category = str(getattr(meta, "category", "") or "")
    size = max(0, int(getattr(meta, "source_size", 0) or 0))
    for dimension, value in media_profile_dimensions(meta):
        await record_event_async("media", service=dimension, operation=value, category=category, destination=destination, bytes_count=size)
    resolution = _dimension(getattr(meta, "resolution", ""))
    if resolution and category.upper() in {"MOVIE", "TV", "FANRES", "XXX", "SPORTS"}:
        codec = _dimension(_video_codec_bucket(getattr(meta, "video_codec", "") or getattr(meta, "video", "")), default="Unknown")
        profile = _dimension(_hdr_bucket(meta), default="SDR")
        await record_event_async(
            "media_matrix",
            service=resolution,
            operation=f"{codec}__{profile}",
            category=category,
            destination=destination,
            bytes_count=size,
        )


async def record_release_profile_async(meta: Any, outcome: str, *, destination: str = "") -> None:
    """Record a privacy-safe personal/standard release result."""
    await record_event_async(
        "release_profile",
        service="personal" if bool(getattr(meta, "personalrelease", False)) else "standard",
        operation="completed",
        outcome=outcome,
        category=str(getattr(meta, "category", "") or ""),
        destination=destination,
        bytes_count=max(0, int(getattr(meta, "source_size", 0) or 0)),
    )


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
            db.execute("CREATE TABLE IF NOT EXISTS stats_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            schema_row = db.execute("SELECT value FROM stats_meta WHERE key = 'schema_version'").fetchone()
            existing_columns = {str(row[1]) for row in db.execute("PRAGMA table_info(stats_daily)")}
            if (schema_row is not None and schema_row[0] != _SCHEMA_VERSION) or (existing_columns and "destination" not in existing_columns):
                db.execute("DROP TABLE IF EXISTS stats_daily")
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
                    destination TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    duration_ms INTEGER NOT NULL DEFAULT 0,
                    bytes INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (day, family, service, operation, outcome, category, source, mode, destination)
                )
                """
            )
            db.execute("INSERT OR REPLACE INTO stats_meta VALUES ('schema_version', ?)", (_SCHEMA_VERSION,))
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
    destination: str = "",
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
        _dimension(destination),
    )
    for attempt in range(4):
        try:
            with _record_lock, closing(_connect(_database_path(state_dir))) as db, db:
                db.execute(
                    """
                    INSERT INTO stats_daily
                        (day, family, service, operation, outcome, category, source, mode, destination, count, duration_ms, bytes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (day, family, service, operation, outcome, category, source, mode, destination)
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


def tracker_route_outcome(status: Mapping[str, Any]) -> str:
    """Normalize one target's terminal state into the dashboard route taxonomy."""
    if status.get("upload_success") is True:
        return "success"
    message = str(status.get("status_message", "") or "").lower()
    if status.get("dupe") or "dupe" in message or "duplicate" in message:
        return "skipped:dupe"
    if status.get("upload_success") is False or status.get("upload") is True:
        return "error"
    return "skipped:no_upload"


async def record_completed_item_stats_async(meta: Any, tracker_class_map: Mapping[str, Any]) -> None:
    """Record global item facts and one complete route for every destination."""
    if not _enabled:
        return
    raw_statuses = getattr(meta, "tracker_status", {})
    statuses = raw_statuses if isinstance(raw_statuses, Mapping) else {}
    routes: list[tuple[str, Mapping[str, Any], str]] = []
    for raw_name, raw_status in statuses.items():
        destination = _dimension(str(raw_name).replace(" ", "").upper())
        if not destination or destination in {"MANUAL", "USENET"} or not isinstance(raw_status, Mapping):
            continue
        tracker_type = tracker_class_map.get(destination)
        destination_type = "usenet_indexer" if tracker_type and getattr(tracker_type, "is_usenet", False) else "torrent_tracker"
        routes.append((destination, raw_status, destination_type))

    item_size = max(0, int(getattr(meta, "source_size", 0) or 0))
    category = str(getattr(meta, "category", "") or "")
    normalized_outcomes = [tracker_route_outcome(status) for _destination, status, _kind in routes]
    item_outcome = "success" if "success" in normalized_outcomes else "error" if "error" in normalized_outcomes else "no_upload"
    await record_event_async("item", operation="completed", outcome=item_outcome, bytes_count=item_size)
    await record_release_profile_async(meta, item_outcome)
    await record_media_profile_async(meta)

    for destination, status, destination_type in routes:
        outcome = tracker_route_outcome(status)
        duration_ms = float(getattr(meta, "get", lambda *_args: 0)(f"{destination}_upload_duration") or 0) * 1000
        await record_event_async(
            "upload",
            service=destination,
            operation=destination_type,
            outcome=outcome,
            category=category,
            destination=destination,
            duration_ms=duration_ms,
            bytes_count=item_size,
        )
        scoped_outcome = "success" if outcome == "success" else "error" if outcome == "error" else "no_upload"
        await record_release_profile_async(meta, scoped_outcome, destination=destination)
        await record_media_profile_async(meta, destination=destination)
        if destination_type == "torrent_tracker":
            torrent_path = Path(str(getattr(meta, "base_dir", ""))) / "tmp" / str(getattr(meta, "uuid", "")) / f"[{destination}].torrent"
            if torrent_path.is_file():
                await record_event_async(
                    "artifact",
                    service="torrent",
                    operation="created",
                    outcome="success",
                    category="tracker",
                    destination=destination,
                )
            try:
                from src.torrent_manifest import TorrentManifest

                manifest = TorrentManifest(getattr(meta, "base_dir", ""), str(getattr(meta, "uuid", "")))
                selected = manifest.selected_path(destination)
                entry = manifest.entry_for_path(selected) if selected is not None else None
                if entry is not None and entry.origin == "client":
                    await record_event_async(
                        "artifact",
                        service="torrent",
                        operation="reused",
                        outcome="success",
                        category="base",
                        destination=destination,
                        bytes_count=item_size,
                    )
            except OSError, TypeError, ValueError:
                pass
        else:
            nzb_paths = getattr(meta, "usenet_nzb_paths", [])
            nzb_count = sum(1 for path in nzb_paths if Path(str(path)).is_file()) if isinstance(nzb_paths, list) else 0
            if nzb_count:
                await record_event_async(
                    "artifact",
                    service="nzb",
                    operation="created",
                    outcome="success",
                    category="assigned",
                    destination=destination,
                    count=nzb_count,
                )


def _parse_date(value: str | None, label: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must use YYYY-MM-DD") from exc


def _resolve_period(period: str, today: datetime, date_from: str | None = None, date_to: str | None = None) -> tuple[str | None, str]:
    current = today.date()
    if period == "custom":
        start_date = _parse_date(date_from, "from")
        end_date = _parse_date(date_to, "to")
        if start_date > end_date:
            raise ValueError("from must be on or before to")
        if end_date > current:
            raise ValueError("to cannot be in the future")
        return start_date.isoformat(), end_date.isoformat()
    if period == "today":
        return current.isoformat(), current.isoformat()
    if period == "this_month":
        return current.replace(day=1).isoformat(), current.isoformat()
    if period == "last_month":
        this_month = current.replace(day=1)
        end_date = this_month - timedelta(days=1)
        return end_date.replace(day=1).isoformat(), end_date.isoformat()
    if period == "all":
        return None, current.isoformat()
    days = _PERIOD_DAYS.get(period)
    if days:
        return (current - timedelta(days=days - 1)).isoformat(), current.isoformat()
    raise ValueError("range must be one of: today, this_month, last_month, 7d, 30d, 90d, 1y, all, custom")


def _empty_payload(period: str, mode: str, generated_at: str, *, start: str | None, end: str, tracker: str = "") -> dict[str, Any]:
    return {
        "success": True,
        "range": period,
        "mode": mode,
        "generated_at": generated_at,
        "period": {"from": start, "to": end, "timezone": "UTC"},
        "filters": {"destinations": [], "active_tracker": tracker or None},
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
            "unique_uploaded_bytes": 0,
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
        "sankey": {"unit": "item_destination_route", "nodes": [], "links": []},
        "media": {"categories": [], "dimensions": [], "matrix": []},
        "streaming": {"services": []},
        "release_profiles": {"profiles": [], "by_category": []},
        "artifacts": [],
        "cache": {"hits": 0, "misses": 0, "writes": 0, "bypasses": 0, "bytes_written": 0, "hit_rate": 0.0, "by_provider": []},
        "api": {"total": 0, "requests": 0, "successes": 0, "errors": 0, "by_service": []},
        "sources": [],
    }


def get_empty_stats(
    period: str = "30d",
    mode: str = "real",
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    tracker: str = "",
) -> dict[str, Any]:
    """Return the stable response shape without reading stored aggregates."""
    if mode not in {"real", "debug"}:
        raise ValueError("mode must be one of: real, debug")
    now = datetime.now(UTC)
    start, end = _resolve_period(period, now, date_from, date_to)
    return _empty_payload(period, mode, now.isoformat(), start=start, end=end, tracker=_dimension(tracker))


def get_stats(
    period: str = "30d",
    mode: str = "real",
    state_dir: str | Path | None = None,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    tracker: str = "",
) -> dict[str, Any]:
    active_tracker = _dimension(tracker.upper())
    payload = get_empty_stats(period, mode, date_from=date_from, date_to=date_to, tracker=active_tracker)
    now = datetime.fromisoformat(str(payload["generated_at"]))
    start = payload["period"]["from"]
    end = payload["period"]["to"]
    path = _database_path(state_dir)
    if not path.is_file():
        return payload
    try:
        with closing(_connect(path)) as db:
            query = "SELECT day, family, service, operation, outcome, category, source, count, duration_ms, bytes, destination FROM stats_daily WHERE mode = ? AND day <= ?"
            parameters: list[object] = [mode, end]
            if start:
                query += " AND day >= ?"
                parameters.append(start)
            rows = db.execute(query, parameters).fetchall()
            if start:
                destination_rows = db.execute(
                    "SELECT DISTINCT service FROM stats_daily WHERE mode = ? AND family = 'upload' AND day <= ? AND day >= ?",
                    (mode, end, start),
                ).fetchall()
            else:
                destination_rows = db.execute(
                    "SELECT DISTINCT service FROM stats_daily WHERE mode = ? AND family = 'upload' AND day <= ?",
                    (mode, end),
                ).fetchall()
            heatmap_start = (now.date() - timedelta(days=364)).isoformat()
            if active_tracker:
                heatmap_rows = db.execute(
                    """
                    SELECT day, SUM(count) FROM stats_daily
                    WHERE mode = ? AND family = 'upload' AND day >= ?
                      AND (destination = ? OR (destination = '' AND service = ?))
                    GROUP BY day ORDER BY day
                    """,
                    (mode, heatmap_start, active_tracker, active_tracker),
                ).fetchall()
            else:
                heatmap_rows = db.execute(
                    """
                    SELECT day, SUM(count) FROM stats_daily
                    WHERE mode = ? AND family = 'item' AND operation = 'completed'
                      AND destination = '' AND day >= ?
                    GROUP BY day ORDER BY day
                    """,
                    (mode, heatmap_start),
                ).fetchall()
            prior_rows: list[tuple[str, str, str, int, str]] = []
            if start:
                current_start = datetime.fromisoformat(start).date()
                current_end = datetime.fromisoformat(end).date()
                days = (current_end - current_start).days + 1
                prior_end = current_start - timedelta(days=1)
                prior_start = prior_end - timedelta(days=days - 1)
                prior_rows = db.execute(
                    """
                    SELECT family, service, outcome, SUM(count), destination FROM stats_daily
                    WHERE mode = ? AND day >= ? AND day <= ?
                    GROUP BY family, service, outcome, destination
                    """,
                    (mode, prior_start.isoformat(), prior_end.isoformat()),
                ).fetchall()
    except OSError, sqlite3.Error:
        return payload

    payload["filters"]["destinations"] = [{"destination": str(row[0])} for row in sorted(destination_rows) if row[0]]
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
    media_matrix: dict[tuple[str, str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    streaming_services: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    release_profiles: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    release_profile_categories: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    sources: dict[str, int] = defaultdict(int)
    overview = payload["overview"]

    for day, family, service, operation, outcome, category, source, count, duration_ms, bytes_count, destination in rows:
        count = int(count)
        effective_destination = destination or (service if family == "upload" else "")
        if family in {"item", "media", "media_matrix", "release_profile", "artifact"}:
            if active_tracker:
                if family == "item" or destination != active_tracker:
                    continue
            elif destination:
                continue
        elif (family == "upload" and active_tracker and effective_destination != active_tracker) or (family in {"cache", "api"} and destination):
            continue
        if family == "item":
            if operation == "completed":
                overview["items_completed"] += count
                if outcome in payload["items"]:
                    payload["items"][outcome] += count
                timeline[day]["items"] += count
                timeline[day]["processed_bytes"] += int(bytes_count)
                overview["processed_bytes"] += int(bytes_count)
                if outcome == "success":
                    overview["unique_uploaded_bytes"] += int(bytes_count)
                sources[source] += count
        elif family == "upload":
            bucket = destinations[(service, operation)]
            normalized_outcome = "skipped" if outcome.startswith("skipped:") else outcome
            bucket[normalized_outcome] += count
            if outcome.startswith("skipped:"):
                bucket[f"reason:{outcome.partition(':')[2] or 'rule'}"] += count
            bucket["duration_ms"] += int(duration_ms)
            bucket["processed_bytes"] += int(bytes_count)
            if outcome in {"success", "error"}:
                bucket["attempts"] += count
                overview["upload_attempts"] += count
            if outcome == "success":
                bucket["bytes"] += int(bytes_count)
                overview["uploads"] += count
                timeline[day]["uploads"] += count
                timeline[day]["uploaded_bytes"] += int(bytes_count)
                overview["uploaded_bytes"] += int(bytes_count)
            elif outcome == "error":
                timeline[day]["upload_errors"] += count
            if active_tracker:
                overview["items_completed"] += count
                overview["processed_bytes"] += int(bytes_count)
                timeline[day]["items"] += count
                timeline[day]["processed_bytes"] += int(bytes_count)
                if outcome == "success":
                    payload["items"]["success"] += count
                    overview["unique_uploaded_bytes"] += int(bytes_count)
                elif outcome == "error":
                    payload["items"]["error"] += count
                else:
                    payload["items"]["no_upload"] += count
                sources[source] += count
            if category:
                categories[category][normalized_outcome] += count
                if outcome == "success":
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
            if service == "streaming_service":
                streaming_services[operation]["count"] += count
                streaming_services[operation]["bytes"] += int(bytes_count)
        elif family == "media_matrix":
            codec, _separator, hdr = operation.partition("__")
            bucket = media_matrix[(category, service, f"{codec}__{hdr}")]
            bucket["count"] += count
            bucket["bytes"] += int(bytes_count)
        elif family == "release_profile" and operation == "completed":
            bucket = release_profiles[service]
            bucket["count"] += count
            bucket[outcome] += count
            bucket["bytes"] += int(bytes_count)
            if category:
                category_bucket = release_profile_categories[(service, category)]
                category_bucket["count"] += count
                category_bucket[outcome] += count
                category_bucket["bytes"] += int(bytes_count)

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
            "processed_bytes": values["processed_bytes"],
            "skip_reasons": {key.removeprefix("reason:"): value for key, value in values.items() if key.startswith("reason:")},
            "pioneering_rate": round(100 * values["success"] / (values["success"] + values["reason:dupe"]), 1) if values["success"] + values["reason:dupe"] else 0.0,
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
    payload["media"]["matrix"] = [
        {
            "category": category,
            "resolution": resolution,
            "profile": profile.replace("__", " · "),
            "count": totals["count"],
            "bytes": totals["bytes"],
        }
        for (category, resolution, profile), totals in sorted(media_matrix.items())
    ]
    payload["streaming"]["services"] = [
        {
            "service": service,
            "items": totals["count"],
            "bytes": totals["bytes"],
            "average_item_bytes": round(totals["bytes"] / totals["count"]) if totals["count"] else 0,
        }
        for service, totals in sorted(streaming_services.items(), key=lambda item: -item[1]["count"])
    ]
    payload["release_profiles"]["profiles"] = [
        {
            "profile": profile,
            "items": totals["count"],
            "successes": totals["success"],
            "without_upload": totals["no_upload"],
            "errors": totals["error"],
            "bytes": totals["bytes"],
            "success_rate": round(100 * totals["success"] / totals["count"], 1) if totals["count"] else 0.0,
        }
        for profile, totals in sorted(release_profiles.items())
    ]
    payload["release_profiles"]["by_category"] = [
        {
            "profile": profile,
            "category": category,
            "items": totals["count"],
            "successes": totals["success"],
            "without_upload": totals["no_upload"],
            "errors": totals["error"],
            "bytes": totals["bytes"],
            "success_rate": round(100 * totals["success"] / totals["count"], 1) if totals["count"] else 0.0,
        }
        for (profile, category), totals in sorted(release_profile_categories.items())
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
    last_day = datetime.fromisoformat(str(payload["period"]["to"])).date()
    timeline_rows: list[dict[str, Any]] = []
    cursor = first_day
    while cursor <= last_day:
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
    outcome_nodes = {
        "success": ("outcome:uploaded", "Upload"),
        "dupe": ("outcome:duplicate", "Duplicate"),
        "error": ("outcome:error", "Error"),
        "no_upload": ("outcome:no_upload", "No upload"),
    }
    sankey_nodes: list[dict[str, Any]] = [{"id": "routes", "kind": "root", "label": "Processed routes", "total": 0}]
    sankey_links: list[dict[str, Any]] = []
    outcome_totals: defaultdict[str, int] = defaultdict(int)
    for (destination, _destination_type), values in destinations.items():
        outcomes = {
            "success": values["success"],
            "dupe": values["reason:dupe"],
            "error": values["error"],
            "no_upload": values["skipped"] - values["reason:dupe"],
        }
        total = sum(outcomes.values())
        if not total:
            continue
        tracker_id = f"tracker:{destination}"
        sankey_nodes.append({"id": tracker_id, "kind": "tracker", "label": destination, "total": total, "destination": destination})
        sankey_links.append({"source": "routes", "target": tracker_id, "value": total})
        sankey_nodes[0]["total"] += total
        for key, value in outcomes.items():
            if value:
                outcome_id, _label = outcome_nodes[key]
                sankey_links.append({"source": tracker_id, "target": outcome_id, "value": value})
                outcome_totals[key] += value
    for key, (node_id, label) in outcome_nodes.items():
        if outcome_totals[key]:
            sankey_nodes.append({"id": node_id, "kind": "outcome", "label": label, "total": outcome_totals[key]})
    payload["sankey"] = {"unit": "item_destination_route", "nodes": sankey_nodes if sankey_links else [], "links": sankey_links}
    if prior_rows:
        prior_items = 0
        prior_uploads = 0
        prior_cache_hits = 0
        prior_cache_misses = 0
        for family, service, outcome, count, destination in prior_rows:
            value = int(count)
            effective_destination = destination or (service if family == "upload" else "")
            if active_tracker:
                if family == "upload" and effective_destination == active_tracker:
                    prior_items += value
                    if outcome == "success":
                        prior_uploads += value
            else:
                if family == "item" and service == "" and destination == "":
                    prior_items += value
                if family == "upload" and outcome == "success":
                    prior_uploads += value
            if family == "cache" and destination == "":
                if outcome == "hit":
                    prior_cache_hits += value
                elif outcome == "miss":
                    prior_cache_misses += value
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
