"""Privacy-preserving aggregate usage statistics for Upload Assistant."""

from __future__ import annotations

import asyncio
import functools
import json
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
from src.content_duration import content_duration_category, existing_content_duration, prepared_content_duration

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
        if not _enabled:
            _item_timing_reset()


def _item_timing_reset() -> None:
    global _item_started_at
    with _timing_lock:
        _item_started_at = None
        _stage_started_at.clear()
        _stage_totals.clear()
        _request_matches.clear()


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
        streaming_service = getattr(meta, "service_longname", "") or getattr(meta, "service", "")
        if streaming_service:
            add("streaming_service", streaming_service)
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
            if schema_row is not None and schema_row[0] not in {"1", _SCHEMA_VERSION}:
                db.close()
                raise sqlite3.DatabaseError("Unsupported statistics schema version")
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
                    content_seconds INTEGER NOT NULL DEFAULT 0,
                    bytes INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (day, family, service, operation, outcome, category, source, mode, destination)
                )
                """
            )
            current_columns = {str(row[1]) for row in db.execute("PRAGMA table_info(stats_daily)")}
            if "content_seconds" not in current_columns:
                try:
                    db.execute("ALTER TABLE stats_daily ADD COLUMN content_seconds INTEGER NOT NULL DEFAULT 0")
                except sqlite3.OperationalError as exc:
                    if "duplicate column" not in str(exc).lower():
                        raise
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
    content_seconds: int | float = 0,
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
                        (day, family, service, operation, outcome, category, source, mode, destination, count, duration_ms, content_seconds, bytes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (day, family, service, operation, outcome, category, source, mode, destination)
                    DO UPDATE SET
                        count = count + excluded.count,
                        duration_ms = duration_ms + excluded.duration_ms,
                        content_seconds = content_seconds + excluded.content_seconds,
                        bytes = bytes + excluded.bytes
                    """,
                    (*dimensions, int(count), max(0, round(duration_ms)), max(0, round(content_seconds)), max(0, int(bytes_count))),
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


# Per-item timing and post-upload counters, kept in memory and written once
# when the item finishes. Items run one after another in a process.
STAGE_KEYS = ("prep", "confirm", "dupes", "screens", "torrent", "upload", "requests")
_timing_lock = threading.Lock()
_item_started_at: float | None = None
_stage_started_at: dict[str, float] = {}
_stage_totals: dict[str, tuple[float, bool]] = {}
_request_matches: defaultdict[tuple[str, bool], int] = defaultdict(int)


def begin_item_timing() -> None:
    """Start timing a new item and discard anything left from the previous one."""
    global _item_started_at
    _item_timing_reset()
    with _timing_lock:
        _item_started_at = time.monotonic()


def observe_run_event(kind: str, payload: Mapping[str, Any]) -> None:
    """Listener for run events (stages and request matches) published by ``webui_events``."""
    now = time.monotonic()
    with _timing_lock:
        if _item_started_at is None:
            return
        if kind == "stage":
            key = str(payload.get("key", ""))
            status = str(payload.get("status", ""))
            if key not in STAGE_KEYS:
                return
            if status == "start":
                _stage_started_at[key] = now
            elif key in _stage_started_at:
                elapsed = now - _stage_started_at.pop(key)
                seconds, failed = _stage_totals.get(key, (0.0, False))
                _stage_totals[key] = (seconds + elapsed, failed or status == "fail")
        elif kind == "request":
            tracker = _dimension(str(payload.get("tracker", "")).replace(" ", "").upper())
            if tracker:
                _request_matches[(tracker, bool(payload.get("exact")))] += 1


def item_elapsed_ms() -> float:
    with _timing_lock:
        return (time.monotonic() - _item_started_at) * 1000 if _item_started_at is not None else 0.0


def upload_stage_started() -> bool:
    """Return whether the current item reached its upload stage (True when untimed)."""
    with _timing_lock:
        return _item_started_at is None or "upload" in _stage_started_at or "upload" in _stage_totals


async def record_item_timings_async() -> None:
    """Write the finished item's stage durations and request matches, then reset them."""
    with _timing_lock:
        stages = dict(_stage_totals)
        requests = dict(_request_matches)
        _stage_started_at.clear()
        _stage_totals.clear()
        _request_matches.clear()
    for key, (seconds, failed) in stages.items():
        await record_event_async("stage", service=key, operation="completed", outcome="error" if failed else "success", duration_ms=seconds * 1000)
    for (tracker, exact), count in requests.items():
        await record_event_async(
            "post_upload",
            service="request_match",
            operation="exact" if exact else "partial",
            destination=tracker,
            count=count,
        )


# Hosts of metadata providers whose requests count as external operations.
# Tracker, image host and srrDB requests are recorded where they are made.
_METADATA_API_HOSTS = {
    "api.themoviedb.org": "tmdb",
    "api.graphql.imdb.com": "imdb",
    "www.imdb.com": "imdb",
    "api4.thetvdb.com": "tvdb",
    "api.tvmaze.com": "tvmaze",
    "api.igdb.com": "igdb",
    "id.twitch.tv": "igdb",
    "graphql.anilist.co": "anilist",
    "arm.haglund.dev": "anime_relations",
    "musicbrainz.org": "musicbrainz",
    "api.discogs.com": "discogs",
    "openlibrary.org": "openlibrary",
    "m.douban.com": "douban",
    "store.steampowered.com": "steam",
    "www.blu-ray.com": "bluray_com",
    "predb.pw": "predb",
}
_metadata_tracking_installed = False


def metadata_api_service(url: Any) -> str:
    """Return the provider name for a metadata API URL, or "" for any other host."""
    host = str(getattr(url, "host", "") or "").lower()
    if host == "www.googleapis.com":
        return "google_books" if str(getattr(url, "path", "")).startswith("/books") else ""
    if host.startswith("api.audible."):
        return "audible"
    return _METADATA_API_HOSTS.get(host, "")


def _metadata_outcome(status_code: int) -> str:
    # A 404 is a valid "not found" answer from a lookup, not a failed call.
    return "success" if status_code < 400 or status_code == 404 else "error"


def install_metadata_api_tracking() -> None:
    """Count metadata provider requests made through httpx, once per process.

    Every provider module builds its own httpx client, so the shared ``send``
    methods are wrapped. Only hosts in ``_METADATA_API_HOSTS`` are recorded,
    the request itself is never changed, and nothing about it but the provider,
    outcome and duration is stored.
    """
    global _metadata_tracking_installed
    with _configuration_lock:
        if _metadata_tracking_installed:
            return
        try:
            import httpx
        except ImportError:
            return
        original_async_send = httpx.AsyncClient.send
        original_sync_send = httpx.Client.send

        @functools.wraps(original_async_send)
        async def tracked_async_send(self: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
            service = metadata_api_service(request.url) if _enabled else ""
            if not service:
                return await original_async_send(self, request, *args, **kwargs)
            started = time.monotonic()
            try:
                response = await original_async_send(self, request, *args, **kwargs)
            except Exception:
                await record_event_async("api", service=service, operation="metadata", outcome="error", duration_ms=(time.monotonic() - started) * 1000)
                raise
            await record_event_async(
                "api", service=service, operation="metadata", outcome=_metadata_outcome(response.status_code), duration_ms=(time.monotonic() - started) * 1000
            )
            return response

        @functools.wraps(original_sync_send)
        def tracked_sync_send(self: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
            service = metadata_api_service(request.url) if _enabled else ""
            if not service:
                return original_sync_send(self, request, *args, **kwargs)
            started = time.monotonic()
            try:
                response = original_sync_send(self, request, *args, **kwargs)
            except Exception:
                record_event("api", service=service, operation="metadata", outcome="error", duration_ms=(time.monotonic() - started) * 1000)
                raise
            record_event("api", service=service, operation="metadata", outcome=_metadata_outcome(response.status_code), duration_ms=(time.monotonic() - started) * 1000)
            return response

        httpx.AsyncClient.send = tracked_async_send  # type: ignore[method-assign]
        httpx.Client.send = tracked_sync_send  # type: ignore[method-assign]
        _metadata_tracking_installed = True


def _status_text(status: Mapping[str, Any]) -> str:
    message = status.get("status_message", "")
    if isinstance(message, (Mapping, list)):
        try:
            return json.dumps(message, default=str).lower()
        except TypeError, ValueError:
            return str(message).lower()
    return str(message or "").lower()


def tracker_route_outcome(status: Mapping[str, Any], *, upload_started: bool = True, site_check: bool = False) -> str:
    """Normalize one target's terminal state into the dashboard route taxonomy.

    ``upload_started`` is False when the item stopped before its upload stage,
    so approved routes were never attempted: a site check never uploads, and
    otherwise too few trackers passed.
    """
    if status.get("upload_success") is True:
        return "success"
    message = _status_text(status)
    if status.get("banned"):
        return "skipped:banned"
    if "error redoing dupe check" in message:
        return "skipped:search_error"
    if status.get("dupe") or "dupe" in message or "duplicate" in message:
        return "skipped:dupe"
    if status.get("upload_success") is False:
        return "error"
    if status.get("upload") is True:
        if upload_started:
            return "error"
        return "skipped:site_check" if site_check else "skipped:too_few_trackers"
    return f"skipped:{_skip_reason(status, message)}"


def _skip_reason(status: Mapping[str, Any], message: str) -> str:
    explicit = _dimension(status.get("skip_reason"))
    if explicit:
        return explicit
    if "claimed" in message:
        return "claimed"
    if "policy-compliant" in message or "torrent provisioning" in message or "torrent creation" in message:
        return "torrent_policy"
    if status.get("skipped") or message:
        return "rules"
    if status.get("upload") is False and "skipped" in status:
        # Passed every check but was not approved at the upload prompt.
        return "declined"
    return "no_upload"


# Ordered: the first matching category wins. Codes are matched as whole words
# so sizes or IDs that contain the same digits are not misread.
_ERROR_REASON_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "auth",
        re.compile(r"\b(401|403)\b|unauthori[sz]ed|forbidden|log ?in|logged in|cookie|passkey|api[ _-]?key|token|credential|authenticat|csrf|session expired"),
    ),
    ("rate_limit", re.compile(r"\b429\b|rate[ _-]?limit|too many|flood|slow down")),
    ("timeout", re.compile(r"time[ d]?out|timed out")),
    ("server", re.compile(r"\b5\d\d\b|bad gateway|service unavailable|internal server error|maintenance|cloudflare")),
    ("network", re.compile(r"connection|connect ?error|\bdns\b|name resolution|getaddrinfo|\bssl\b|certificate|network|unreachable")),
    ("invalid_response", re.compile(r"data error|\bjson\b|decod|unexpected response|could not parse|parse error")),
    ("rejected", re.compile(r"reject|not allowed|invalid|required|already exists|denied|validation|must |banned|\brules?\b")),
)


def _classify_error_text(text: str) -> str:
    for reason, pattern in _ERROR_REASON_PATTERNS:
        if pattern.search(text):
            return reason
    return ""


def upload_error_reason(status: Mapping[str, Any]) -> str:
    """Return a low-cardinality reason for a failed upload route; the message itself is never stored."""
    explicit = _dimension(status.get("error_reason"))
    if explicit:
        return explicit
    message = _status_text(status)
    if not message:
        return "unknown"
    return _classify_error_text(message) or "other"


def exception_error_reason(error: BaseException) -> str:
    """Return a low-cardinality reason for an exception raised while uploading."""
    if isinstance(error, TimeoutError):
        return "timeout"
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int):
        if status_code in {401, 403}:
            return "auth"
        if status_code == 429:
            return "rate_limit"
        if status_code >= 500:
            return "server"
    name = type(error).__name__.lower()
    if "timeout" in name:
        return "timeout"
    if isinstance(error, ConnectionError) or "connect" in name or "network" in name:
        return "network"
    return _classify_error_text(f"{name} {error}".lower()) or "exception"


def accumulate_upload_durations(meta: Any, flow_meta: Any, destinations: Iterable[str]) -> None:
    """Keep measured upload times when a flow uses a copy of the item metadata."""
    for destination in destinations:
        key = f"{str(destination).replace(' ', '').upper()}_upload_duration"
        duration = float(flow_meta.get(key) or 0)
        if duration > 0:
            meta[key] = float(meta.get(key) or 0) + duration


def _is_client_origin(origin: str) -> bool:
    """Return whether a manifest torrent came from a torrent client instead of local hashing."""
    return origin == "client" or origin.startswith("client:")


def _torrent_manifest(meta: Any) -> Any:
    release_id = str(getattr(meta, "uuid", "") or "")
    if not release_id:
        return None
    try:
        from src.torrent_manifest import TorrentManifest

        return TorrentManifest(getattr(meta, "base_dir", ""), release_id)
    except OSError, TypeError, ValueError:
        return None


def _manifest_entry(manifest: Any, kind: str, key: str) -> Any:
    """Return the default (by layout) or selected (by tracker) manifest entry, if any."""
    if manifest is None:
        return None
    try:
        path = manifest.default_path(key) if kind == "default" else manifest.selected_path(key)
        return manifest.entry_for_path(path) if path is not None else None
    except OSError, TypeError, ValueError:
        return None


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
    prepared_category = str(getattr(meta, "content_duration_category", "") or "")
    content_category = prepared_category or content_duration_category(meta)
    content_seconds = prepared_content_duration(meta) if prepared_category else existing_content_duration(meta)
    upload_started = upload_stage_started()
    site_check = bool(getattr(meta, "site_check", False))
    normalized_outcomes = [tracker_route_outcome(status, upload_started=upload_started, site_check=site_check) for _destination, status, _kind in routes]
    item_outcome = "success" if "success" in normalized_outcomes else "error" if "error" in normalized_outcomes else "no_upload"
    await record_event_async("item", operation="completed", outcome=item_outcome, bytes_count=item_size, duration_ms=item_elapsed_ms())
    await record_release_profile_async(meta, item_outcome)
    await record_media_profile_async(meta)
    manifest = _torrent_manifest(meta)
    # A client torrent registered as a default base is what spares the base
    # hash, whichever stage found it, so count it once per completed item.
    for layout in ("base", "base_subs"):
        entry = _manifest_entry(manifest, "default", layout)
        if entry is not None and _is_client_origin(entry.origin):
            await record_event_async(
                "artifact",
                service="torrent",
                operation="reused",
                outcome="success",
                category=layout,
                bytes_count=entry.content_size or item_size,
            )
    if item_outcome == "success" and content_category and content_seconds > 0:
        await record_event_async(
            "content",
            operation="uploaded",
            outcome="success",
            category=content_category,
            content_seconds=content_seconds,
        )

    for destination, status, destination_type in routes:
        outcome = tracker_route_outcome(status, upload_started=upload_started, site_check=site_check)
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
        if outcome == "error":
            await record_event_async(
                "upload_error",
                service=destination,
                operation=upload_error_reason(status),
                outcome="error",
                category=category,
                destination=destination,
            )
        scoped_outcome = "success" if outcome == "success" else "error" if outcome == "error" else "no_upload"
        await record_release_profile_async(meta, scoped_outcome, destination=destination)
        await record_media_profile_async(meta, destination=destination)
        if outcome == "success" and content_category and content_seconds > 0:
            await record_event_async(
                "content",
                operation="uploaded",
                outcome="success",
                category=content_category,
                destination=destination,
                content_seconds=content_seconds,
            )
        if destination_type == "torrent_tracker":
            # The tracker's [NAME].torrent is a copy of its selected base, so
            # only the selected base's origin says whether it was hashed or reused.
            entry = _manifest_entry(manifest, "selection", destination)
            if entry is not None and _is_client_origin(entry.origin):
                await record_event_async(
                    "artifact",
                    service="torrent",
                    operation="reused",
                    outcome="success",
                    category=entry.layout,
                    destination=destination,
                    bytes_count=entry.content_size or item_size,
                )
            elif entry is not None and entry.origin == "generated":
                await record_event_async(
                    "artifact",
                    service="torrent",
                    operation="created",
                    outcome="success",
                    category=entry.layout,
                    destination=destination,
                )
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
    await record_item_timings_async()


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


def _stats_now(time_basis: str, local_date: str | None = None) -> datetime:
    if time_basis == "utc":
        return datetime.now(UTC)
    if time_basis == "browser":
        browser_date = _parse_date(local_date, "today")
        return datetime.combine(browser_date, datetime.min.time(), tzinfo=UTC)
    raise ValueError("timezone must be one of: utc, browser")


def _empty_payload(
    period: str,
    mode: str,
    generated_at: str,
    *,
    start: str | None,
    end: str,
    tracker: str = "",
    time_basis: str = "utc",
    now: datetime,
) -> dict[str, Any]:
    period_timezone = "UTC" if time_basis == "utc" else "Browser local time"
    return {
        "success": True,
        "range": period,
        "mode": mode,
        "generated_at": generated_at,
        "period": {"from": start, "to": end, "timezone": period_timezone},
        "time_context": {
            "basis": time_basis,
            "today": now.date().isoformat(),
        },
        "filters": {"destinations": [], "active_tracker": tracker or None},
        "overview": {
            "items_completed": 0,
            "uploads": 0,
            "upload_attempts": 0,
            "upload_success_rate": 0.0,
            "torrents_created": 0,
            "nzbs_created": 0,
            "screenshots_created": 0,
            "api_operations": 0,
            "cache_hit_rate": 0.0,
            "uploaded_bytes": 0,
            "unique_uploaded_bytes": 0,
            "processed_bytes": 0,
            "average_item_bytes": 0,
            "duplicate_preventions": 0,
            "pioneering_rate": 0.0,
            "hashing_bytes_avoided": 0,
            "hashed_bytes": 0,
            "hashing_bytes_per_second": 0,
            "hashing_seconds_saved": 0,
            "average_item_seconds": 0.0,
        },
        "stages": [],
        "image_hosts": {"hosts": [], "fallbacks": []},
        "post_upload": {"cross_seeds": 0, "requests_exact": 0, "requests_partial": 0, "trump_reports": 0, "trump_report_errors": 0, "by_destination": []},
        "timeline": [],
        "heatmap": [],
        "comparison": {"items_completed_pct": None, "uploads_pct": None, "cache_hit_rate_delta": None},
        "items": {"success": 0, "no_upload": 0, "error": 0},
        "uploads": {"by_destination": [], "by_category": []},
        "content_time": {"total_seconds": 0, "by_category": []},
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
    time_basis: str = "utc",
    local_date: str | None = None,
) -> dict[str, Any]:
    """Return the stable response shape without reading stored aggregates."""
    if mode not in {"real", "debug"}:
        raise ValueError("mode must be one of: real, debug")
    now = _stats_now(time_basis, local_date)
    start, end = _resolve_period(period, now, date_from, date_to)
    return _empty_payload(
        period,
        mode,
        datetime.now(UTC).isoformat(),
        start=start,
        end=end,
        tracker=_dimension(tracker),
        time_basis=time_basis,
        now=now,
    )


def get_stats(
    period: str = "30d",
    mode: str = "real",
    state_dir: str | Path | None = None,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    tracker: str = "",
    time_basis: str = "utc",
    local_date: str | None = None,
) -> dict[str, Any]:
    active_tracker = _dimension(tracker.upper())
    payload = get_empty_stats(
        period,
        mode,
        date_from=date_from,
        date_to=date_to,
        tracker=active_tracker,
        time_basis=time_basis,
        local_date=local_date,
    )
    now = datetime.fromisoformat(str(payload["time_context"]["today"]))
    start = payload["period"]["from"]
    end = payload["period"]["to"]
    path = _database_path(state_dir)
    if not path.is_file():
        return payload
    try:
        with closing(_connect(path)) as db:
            query = "SELECT day, family, service, operation, outcome, category, source, count, duration_ms, content_seconds, bytes, destination FROM stats_daily WHERE mode = ? AND day <= ?"
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
            prior_rows: list[tuple[str, str, str, str, int, str]] = []
            if start:
                current_start = datetime.fromisoformat(start).date()
                current_end = datetime.fromisoformat(end).date()
                days = (current_end - current_start).days + 1
                prior_end = current_start - timedelta(days=1)
                prior_start = prior_end - timedelta(days=days - 1)
                prior_rows = db.execute(
                    """
                    SELECT family, service, operation, outcome, SUM(count), destination FROM stats_daily
                    WHERE mode = ? AND day >= ? AND day <= ?
                    GROUP BY family, service, operation, outcome, destination
                    """,
                    (mode, prior_start.isoformat(), prior_end.isoformat()),
                ).fetchall()
    except OSError, sqlite3.Error:
        payload.update(success=False, error="Unable to read statistics. Check the statistics database and try again.")
        return payload

    payload["filters"]["destinations"] = [{"destination": str(row[0])} for row in sorted(destination_rows) if row[0]]
    payload["heatmap"] = [{"date": day, "count": int(count)} for day, count in heatmap_rows]
    if rows:
        payload["period"]["from"] = start or min(row[0] for row in rows)

    timeline: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    destinations: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    categories: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    artifacts: dict[tuple[str, str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    cache_services: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    api_services: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    daily_api_services: dict[tuple[str, str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    media_dimensions: dict[tuple[str, str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    media_matrix: dict[tuple[str, str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    streaming_services: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    release_profiles: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    release_profile_categories: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    content_categories: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    sources: dict[str, int] = defaultdict(int)
    error_reasons: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    stages: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    fallbacks: dict[tuple[str, str], int] = defaultdict(int)
    post_upload: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    hashed_bytes = hashed_ms = timed_items = timed_item_ms = 0
    overview = payload["overview"]

    for day, family, service, operation, outcome, category, source, count, duration_ms, content_seconds, bytes_count, destination in rows:
        count = int(count)
        effective_destination = destination or (service if family == "upload" else "")
        # Hashing speed and item time describe this machine, so they are global in every view.
        if family == "artifact" and service == "torrent" and operation == "created" and not destination and int(duration_ms) > 0:
            hashed_bytes += int(bytes_count)
            hashed_ms += int(duration_ms)
        if family == "item" and operation == "completed" and int(duration_ms) > 0:
            timed_items += count
            timed_item_ms += int(duration_ms)
        if active_tracker and family == "artifact" and service == "screenshot" and not destination:
            # Screenshots are shared by every destination of an item, so a
            # tracker view reports the global count (labelled as such) instead of zero.
            if operation == "created" and outcome == "success":
                overview["screenshots_created"] += count
            continue
        if family in {"item", "media", "media_matrix", "release_profile", "artifact", "content"}:
            if active_tracker:
                if family == "item" or destination != active_tracker:
                    continue
            elif destination:
                continue
        elif (
            (family == "upload" and active_tracker and effective_destination != active_tracker)
            or (family in {"upload_error", "post_upload"} and active_tracker and destination != active_tracker)
            or (family in {"cache", "api"} and destination)
        ):
            continue
        if family == "upload_error":
            error_reasons[service][operation] += count
            continue
        if family == "stage":
            stage_bucket = stages[service]
            stage_bucket["count"] += count
            stage_bucket["duration_ms"] += int(duration_ms)
            if outcome == "error":
                stage_bucket["failures"] += count
            continue
        if family == "image_fallback":
            fallbacks[(service, operation)] += count
            continue
        if family == "post_upload":
            post_bucket = post_upload[destination or service]
            if service == "cross_seed":
                post_bucket["cross_seeds"] += count
            elif service == "request_match":
                post_bucket["requests_exact" if operation == "exact" else "requests_partial"] += count
            elif service == "trump_report":
                post_bucket["trump_reports" if outcome == "success" else "trump_report_errors"] += count
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
            if service == "screenshot" and operation == "created" and outcome == "success":
                overview["screenshots_created"] += count
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
            daily_api_services[(day, service, operation)][outcome] += count
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
        elif family == "content" and operation == "uploaded" and outcome == "success" and category:
            bucket = content_categories[category]
            bucket["items"] += count
            bucket["seconds"] += int(content_seconds)

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
            "error_reasons": dict(sorted(error_reasons.get(service, {}).items(), key=lambda item: -item[1])),
            "pioneering_rate": round(100 * values["success"] / (values["success"] + values["reason:dupe"]), 1) if values["success"] + values["reason:dupe"] else 0.0,
        }
        for (service, destination_type), values in sorted(destinations.items(), key=lambda item: -item[1]["success"])
    ]
    payload["uploads"]["by_category"] = [
        {"category": name, "successes": values["success"], "errors": values["error"], "skipped": values["skipped"], "bytes": values["bytes"]}
        for name, values in sorted(categories.items(), key=lambda item: -item[1]["success"])
    ]
    payload["content_time"] = {
        "total_seconds": sum(values["seconds"] for values in content_categories.values()),
        "by_category": [
            {"category": name, "items": values["items"], "seconds": values["seconds"]}
            for name, values in sorted(content_categories.items(), key=lambda item: (-item[1]["seconds"], item[0]))
        ],
    }
    payload["artifacts"] = [
        {"type": artifact_type, "operation": operation, "variant": variant, "count": values["count"], "bytes": values["bytes"]}
        for (artifact_type, operation, variant), values in sorted(artifacts.items())
    ]
    duplicate_preventions = sum(values["reason:dupe"] for values in destinations.values())
    pioneering_total = overview["uploads"] + duplicate_preventions
    overview["duplicate_preventions"] = duplicate_preventions
    overview["pioneering_rate"] = round(100 * overview["uploads"] / pioneering_total, 1) if pioneering_total else 0.0
    hashing_speed = round(hashed_bytes / (hashed_ms / 1000)) if hashed_ms else 0
    overview["hashed_bytes"] = hashed_bytes
    overview["hashing_bytes_per_second"] = hashing_speed
    # The time a reused base would have taken at this machine's measured hashing speed.
    overview["hashing_seconds_saved"] = round(overview["hashing_bytes_avoided"] / hashing_speed) if hashing_speed else 0
    overview["average_item_seconds"] = round(timed_item_ms / timed_items / 1000, 1) if timed_items else 0.0
    stage_order = {key: index for index, key in enumerate(STAGE_KEYS)}
    payload["stages"] = [
        {
            "stage": name,
            "items": values["count"],
            "failures": values["failures"],
            "total_ms": values["duration_ms"],
            "average_ms": round(values["duration_ms"] / values["count"]) if values["count"] else 0,
        }
        for name, values in sorted(stages.items(), key=lambda item: (stage_order.get(item[0], len(stage_order)), item[0]))
    ]
    fallbacks_from: defaultdict[str, int] = defaultdict(int)
    for (from_host, _to_host), value in fallbacks.items():
        fallbacks_from[from_host] += value
    image_hosts = [
        {
            "host": service,
            "uploads": values["success"],
            "failures": values["error"],
            "success_rate": round(100 * values["success"] / (values["success"] + values["error"]), 1) if values["success"] + values["error"] else 0.0,
            "average_duration_ms": round(values["duration_ms"] / (values["success"] + values["error"])) if values["success"] + values["error"] else 0,
            "bytes": values["bytes"],
            "fallbacks_from": fallbacks_from.get(service, 0),
        }
        for (service, operation), values in api_services.items()
        if operation == "image_upload"
    ]
    payload["image_hosts"] = {
        "hosts": sorted(image_hosts, key=lambda row: (-(row["uploads"] + row["failures"]), row["host"])),
        "fallbacks": [{"from": from_host, "to": to_host, "count": value} for (from_host, to_host), value in sorted(fallbacks.items(), key=lambda item: (-item[1], item[0]))],
    }
    post_rows = [
        {"destination": name, **{key: values[key] for key in ("cross_seeds", "requests_exact", "requests_partial", "trump_reports", "trump_report_errors")}}
        for name, values in post_upload.items()
    ]
    payload["post_upload"] = {
        **{key: sum(row[key] for row in post_rows) for key in ("cross_seeds", "requests_exact", "requests_partial", "trump_reports", "trump_report_errors")},
        "by_destination": sorted(
            post_rows, key=lambda row: (-(row["cross_seeds"] + row["requests_exact"] + row["requests_partial"] + row["trump_reports"]), row["destination"])
        ),
    }
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
    for (day, service, operation), values in daily_api_services.items():
        requests = values["request"] or (values["success"] + values["error"])
        timeline[day]["api"] += requests
        api_services[(service, operation)]["requests"] += requests
    api_requests = sum(values["requests"] for values in api_services.values())
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
                "requests": values["requests"],
                "successes": values["success"],
                "errors": values["error"],
                "average_duration_ms": round(values["duration_ms"] / (values["success"] + values["error"])) if values["success"] + values["error"] else 0,
                "bytes": values["bytes"],
            }
            for (service, operation), values in sorted(
                api_services.items(),
                key=lambda item: -item[1]["requests"],
            )
        ],
    )
    first_day = datetime.fromisoformat(str(payload["period"]["from"] or end)).date()
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
        for family, service, operation, outcome, count, destination in prior_rows:
            value = int(count)
            effective_destination = destination or (service if family == "upload" else "")
            if active_tracker:
                if family == "upload" and effective_destination == active_tracker:
                    prior_items += value
                    if outcome == "success":
                        prior_uploads += value
            else:
                if family == "item" and service == "" and operation == "completed" and destination == "":
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
