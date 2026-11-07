"""Local history of processed uploads.

One row is written to the application database when an item finishes (or
stops early), with the release's external IDs, every tracker's final result
and the request matches found for it. Debug runs are not recorded. Unlike the
aggregate statistics, the history keeps names, paths and links: it is a local
record for the person running Upload Assistant, enabled by default through
``DEFAULT.history_enabled``.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import sqlite3
import threading
import time
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from src import webui_events
from src.app_db import connect as connect_app_db
from src.app_db import database_available, database_path
from src.console import logger

# Files below this size (NFOs, checksums, small artwork) change without the
# release changing, so they are left out of the fingerprint when larger ones exist.
FINGERPRINT_MIN_FILE_SIZE = 1024 * 1024
FINGERPRINT_MAX_FILES = 20_000
MAX_REQUESTS_PER_ITEM = 100
OUTCOMES = ("success", "error", "no_upload", "skipped")

_enabled = True
_retention_days = 0
_state_lock = threading.Lock()
_record_lock = threading.Lock()


@dataclass
class _ItemState:
    started_at: str
    started_monotonic: float
    started_stages: set[str] = field(default_factory=set[str])
    dupes: dict[str, dict[str, Any]] = field(default_factory=dict[str, dict[str, Any]])
    slots: dict[str, dict[str, Any]] = field(default_factory=dict[str, dict[str, Any]])
    requests: dict[str, dict[str, Any]] = field(default_factory=dict[str, dict[str, Any]])
    # Torrent links as published when each upload finished (the tracker instance knows its URL).
    links: dict[str, dict[str, str]] = field(default_factory=dict[str, dict[str, str]])


_item: _ItemState | None = None


def history_enabled(config: Mapping[str, Any] | None) -> bool:
    """Return whether the upload history is on; it is unless ``DEFAULT.history_enabled`` is False."""
    default = config.get("DEFAULT") if isinstance(config, Mapping) else None
    if not isinstance(default, Mapping):
        return True
    return cast(Mapping[str, Any], default).get("history_enabled", True) is not False


def configure_history(config: Mapping[str, Any] | None) -> None:
    """Apply the run's history settings."""
    global _enabled, _retention_days
    _enabled = history_enabled(config)
    _retention_days = history_retention_days(config)


def _tracker_key(value: object) -> str:
    """Normalize a tracker name to the key used in ``meta.tracker_status``."""
    return str(value or "").replace(" ", "").upper()


def begin_item() -> None:
    """Start collecting details for a new item and drop anything left from the previous one."""
    global _item
    with _state_lock:
        _item = _ItemState(started_at=datetime.now(UTC).isoformat(), started_monotonic=time.monotonic())


def item_active() -> bool:
    """Whether an item was started and not yet recorded."""
    with _state_lock:
        return _item is not None


def observe_run_event(kind: str, payload: Mapping[str, Any]) -> None:
    """Listener for stage events; the history only needs to know which stages started."""
    if kind != "stage" or payload.get("status") != "start":
        return
    with _state_lock:
        if _item is not None:
            _item.started_stages.add(str(payload.get("key", "")))


def observe_detail(kind: str, payload: Mapping[str, Any]) -> None:
    """Detail listener: keep the last dupe list and slot verdict per tracker, and every request match."""
    with _state_lock:
        if _item is None:
            return
        tracker = _tracker_key(payload.get("tracker"))
        if not tracker:
            return
        if kind == "dupes":
            previous = _item.dupes.get(tracker, {})
            entries = cast(list[Any], payload.get("entries") or previous.get("entries") or [])
            _item.dupes[tracker] = {"entries": entries, "note": payload.get("note") or previous.get("note") or "", "trumpable": bool(payload.get("trumpable"))}
        elif kind == "slot":
            _item.slots[tracker] = {key: value for key, value in payload.items() if key != "tracker"}
        elif kind == "tracker" and payload.get("status") == "success" and payload.get("link"):
            _item.links[tracker] = {"link": str(payload["link"]), "torrent_id": str(payload.get("torrent_id") or "")}
        elif kind == "request" and len(_item.requests) < MAX_REQUESTS_PER_ITEM:
            key = f"{tracker}|{payload.get('link') or payload.get('name')}"
            _item.requests.setdefault(key, {**payload, "tracker": tracker})


def content_fingerprint(path: str | Path) -> str:
    """Identify a release by its files' relative paths and sizes, or "" when it cannot be read.

    A folder's own name is left out, so renaming it keeps the fingerprint; a
    single file is identified by its name and size.
    """
    root = Path(path)
    entries: list[tuple[str, int]] = []

    def unreadable(error: OSError) -> None:
        # A fingerprint of only the readable part could match another release.
        raise error

    try:
        if root.is_file():
            entries.append((root.name, root.stat().st_size))
        elif root.is_dir():
            for directory, _dirs, files in os.walk(root, onerror=unreadable):
                for name in files:
                    file_path = Path(directory) / name
                    try:
                        size = file_path.stat().st_size
                    except FileNotFoundError:
                        # A broken symlink is not part of the release's content.
                        if file_path.is_symlink():
                            continue
                        raise
                    entries.append((file_path.relative_to(root).as_posix(), size))
                    if len(entries) > FINGERPRINT_MAX_FILES:
                        return ""
    except OSError:
        return ""
    large = [entry for entry in entries if entry[1] >= FINGERPRINT_MIN_FILE_SIZE]
    chosen = sorted(large or entries)
    if not chosen:
        return ""
    return sha256("\n".join(f"{name}\t{size}" for name, size in chosen).encode("utf-8")).hexdigest()


def _text(value: object, limit: int = webui_events.MAX_TEXT_LENGTH, *, markup: bool = True) -> str:
    """Return redacted plain text; ``markup=False`` keeps literal brackets, as in release names."""
    if value in (None, ""):
        return ""
    if isinstance(value, (Mapping, list)):
        try:
            value = json.dumps(value, default=str)
        except TypeError, ValueError:
            value = str(value)
    return webui_events.plain_text(value, limit, markup=markup)


def _http_link(value: object) -> str:
    """Return ``value`` when it is an http(s) link, otherwise ""."""
    link = _text(value, 2000, markup=False)
    return link if link.lower().startswith(("http://", "https://")) else ""


def _positive_int(value: object) -> int:
    """Return ``value`` as a positive integer, or 0."""
    try:
        number = int(str(value).strip())
    except TypeError, ValueError:
        return 0
    return number if number > 0 else 0


def _discogs_ids(meta: Any) -> dict[str, str]:
    """Return the Discogs release and master IDs, as numbers.

    The music pipeline keeps the IDs it used (from an argument, a choice or an
    automatic match) in ``music_release``; the arguments, which may be URLs,
    are only read when the pipeline did not run.
    """
    from src.music.sources import DiscogsEnricher

    ids: dict[str, str] = {}
    release = getattr(meta, "music_release", None)
    known = cast(Mapping[str, Any], release).get("external_ids") if isinstance(release, Mapping) else None
    if isinstance(known, Mapping):
        # The selected release's IDs belong together; an argument the pipeline
        # did not use (for example with --no-music-discogs) must not join them.
        for kind in ("release", "master"):
            reference = DiscogsEnricher.parse_reference(cast(Mapping[str, Any], known).get(f"discogs_{kind}"), kind)
            if reference and reference[0] == kind:
                ids[f"discogs_{kind}"] = reference[1]
        return ids
    for attribute, default_kind in (("music_discogs_release_id", "release"), ("music_discogs_master_id", "master"), ("music_discogs_id", "release")):
        reference = DiscogsEnricher.parse_reference(getattr(meta, attribute, ""), default_kind)
        if reference:
            ids.setdefault(f"discogs_{reference[0]}", reference[1])
    return ids


def external_ids(meta: Any) -> dict[str, str]:
    """Return the release's known external IDs as provider -> value, in the format the CLI accepts."""
    ids: dict[str, str] = {}
    imdb = _positive_int(getattr(meta, "imdb_id", 0))
    if imdb:
        ids["imdb"] = f"tt{imdb:07d}"
    tmdb = _positive_int(getattr(meta, "tmdb_id", 0))
    category = str(getattr(meta, "category", "") or "").upper()
    if tmdb and category in {"MOVIE", "TV"}:
        ids["tmdb"] = f"{'movie' if category == 'MOVIE' else 'tv'}/{tmdb}"
    for provider, attribute in (
        ("tvdb", "tvdb_id"),
        ("tvmaze", "tvmaze_id"),
        ("mal", "mal_id"),
        ("igdb", "igdb_id"),
        ("douban", "douban_id"),
    ):
        number = _positive_int(getattr(meta, attribute, 0))
        if number:
            ids[provider] = str(number)
    ids.update(_discogs_ids(meta))
    for provider, attributes in (
        ("openlibrary", ("openlibrary",)),
        ("isbn", ("book_isbn", "isbn")),
        ("asin", ("book_asin", "asin")),
        ("tpdb", ("tpdb_id",)),
        ("blvckout", ("blvckout_id",)),
    ):
        for attribute in attributes:
            value = _text(getattr(meta, attribute, ""), 64, markup=False)
            if value and value not in {"0", "None"}:
                ids[provider] = value
                break
    return ids


def _tracker_link(status: Mapping[str, Any], tracker_class: Any) -> str:
    """Return the torrent page from the status, or from the tracker's torrent URL and the torrent ID."""
    link = _http_link(status.get("torrent_link"))
    torrent_id = status.get("torrent_id")
    if not link and torrent_id not in (None, ""):
        link = _http_link(f"{getattr(tracker_class, 'torrent_url', '')}{torrent_id}")
    return link


def _usenet_row(meta: Any, upload_started: bool) -> dict[str, Any] | None:
    """Return the result of an NNTP post the run asked for, which has no tracker status of its own."""
    trackers = getattr(meta, "trackers", None) or []
    requested = bool(getattr(meta, "usenet", False)) or "USENET" in {_tracker_key(tracker) for tracker in trackers if isinstance(tracker, str)}
    if not requested:
        return None
    posted = bool(getattr(meta, "nzb_path", None))
    if not posted and not upload_started:
        return None
    return {
        "tracker": "USENET",
        "status": "success" if posted else "failed",
        "message": "Posted to Usenet" if posted else "Usenet upload failed",
        "link": "",
        "torrent_id": "",
        "duration": None,
        "dupes": None,
        "slot": None,
    }


def _tracker_rows(meta: Any, tracker_class_map: Mapping[str, Any], state: _ItemState | None) -> list[dict[str, Any]]:
    """Return one row per destination with its final result, link, dupes and slot verdict."""
    raw_statuses = getattr(meta, "tracker_status", {})
    statuses = cast(Mapping[str, Any], raw_statuses if isinstance(raw_statuses, Mapping) else {})
    upload_started = state is None or "upload" in state.started_stages
    rows: list[dict[str, Any]] = []
    for raw_name, raw_status in statuses.items():
        tracker = _tracker_key(raw_name)
        if not tracker or tracker in {"MANUAL", "USENET"} or not isinstance(raw_status, Mapping):
            continue
        status = cast(Mapping[str, Any], raw_status)
        resolved = webui_events.tracker_status_from_meta(status, final=True, upload_started=upload_started)
        message = status.get("status_message")
        if resolved == "success":
            text = _text(message)
            message_text = "" if "data error" in text.lower() else text
        else:
            message_text = _text(message) or webui_events.DEFAULT_STATUS_MESSAGES.get(resolved, "")
        duration = getattr(meta, "get", lambda *_args: None)(f"{tracker}_upload_duration")
        published = state.links.get(tracker, {}) if state else {}
        link = (published.get("link") or _tracker_link(status, tracker_class_map.get(tracker))) if resolved == "success" else ""
        torrent_id = status.get("torrent_id") or published.get("torrent_id")
        rows.append(
            {
                "tracker": tracker,
                "status": resolved,
                "message": message_text,
                "link": link,
                "torrent_id": _text(torrent_id, 64, markup=False) if resolved == "success" else "",
                "duration": round(float(duration), 2) if isinstance(duration, (int, float)) and duration > 0 else None,
                "dupes": state.dupes.get(tracker) if state else None,
                "slot": state.slots.get(tracker) if state else None,
            }
        )
    # Trackers whose dupe list or slot verdict was shown but that have no final status.
    if state is not None:
        known = {row["tracker"] for row in rows}
        rows.extend(
            {
                "tracker": tracker,
                "status": "skipped",
                "message": webui_events.DEFAULT_STATUS_MESSAGES["skipped"],
                "link": "",
                "torrent_id": "",
                "duration": None,
                "dupes": state.dupes.get(tracker),
                "slot": state.slots.get(tracker),
            }
            for tracker in sorted((set(state.dupes) | set(state.slots)) - known)
        )
    usenet = _usenet_row(meta, upload_started)
    if usenet is not None:
        rows.append(usenet)
    return rows


def _artwork_url(meta: Any) -> str:
    """Return a public cover URL for the release, or ""."""
    url = _http_link(getattr(meta, "artwork_url", ""))
    if url:
        return url
    poster = str(getattr(meta, "tmdb_poster_path", "") or "")
    return _http_link(f"{webui_events.TMDB_POSTER_BASE}{poster}") if poster.startswith("/") else ""


def _year(meta: Any) -> int | None:
    """Return the release year when it is plausible."""
    year = _positive_int(getattr(meta, "year", 0))
    return year if 1800 <= year <= 2200 else None


def build_item_record(meta: Any, tracker_class_map: Mapping[str, Any], *, outcome: str | None = None, reason: str = "") -> dict[str, Any] | None:
    """Collect everything stored for one finished item, or None when it is not recorded."""
    if not _enabled or bool(getattr(meta, "debug", False)):
        return None
    with _state_lock:
        state = _item
    path = str(getattr(meta, "path", "") or "")
    if not path:
        return None
    trackers = _tracker_rows(meta, tracker_class_map, state)
    if outcome not in OUTCOMES:
        statuses = {row["status"] for row in trackers}
        failed = "failed" in statuses or reason == "exception"
        outcome = "success" if "success" in statuses else "error" if failed else "no_upload"
    site_check = bool(getattr(meta, "site_check", False))
    if not reason and site_check:
        reason = "site_check"
    started_at = state.started_at if state else datetime.now(UTC).isoformat()
    duration_ms = round((time.monotonic() - state.started_monotonic) * 1000) if state else 0
    requests = list(state.requests.values()) if state else []
    return {
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "source": _text(os.environ.get("UA_STATS_SOURCE", "cli"), 20) or "cli",
        "path": path,
        "name": _text(getattr(meta, "name", ""), 500, markup=False) or _text(Path(path).name, 500, markup=False),
        "title": _text(getattr(meta, "title", ""), 300, markup=False),
        "year": _year(meta),
        "category": _text(getattr(meta, "category", ""), 20, markup=False).upper(),
        "release_type": _text(getattr(meta, "type", ""), 40, markup=False),
        "resolution": _text(getattr(meta, "resolution", ""), 20, markup=False),
        "release_group": _text(str(getattr(meta, "tag", "") or "").lstrip("-"), 100, markup=False),
        "season": _text(getattr(meta, "season", ""), 20, markup=False) if str(getattr(meta, "season", "") or "") not in {"0", ""} else "",
        "episode": _text(getattr(meta, "episode", ""), 20, markup=False),
        "size": max(0, _positive_int(getattr(meta, "source_size", 0))),
        "fingerprint": str(getattr(meta, "release_fingerprint", "") or "") or content_fingerprint(path),
        "infohash": _text(getattr(meta, "infohash", ""), 64, markup=False).lower(),
        "outcome": outcome,
        "reason": _text(reason, 60),
        "duration_ms": duration_ms,
        "site_check": site_check,
        "personal_release": getattr(meta, "personalrelease", False) is True,
        "artwork_url": _artwork_url(meta),
        "ids": external_ids(meta),
        "trackers": trackers,
        "requests": requests,
    }


def _json(value: object) -> str:
    """Serialize a stored detail compactly, or "" when there is none."""
    if not value:
        return ""
    try:
        return json.dumps(value, default=str, separators=(",", ":"))
    except TypeError, ValueError:
        return ""


def record_item(record: Mapping[str, Any], state_dir: str | Path | None = None) -> int | None:
    """Write one item and its details; return its id, or None when the database is unavailable."""
    columns = (
        "started_at",
        "finished_at",
        "source",
        "path",
        "name",
        "title",
        "year",
        "category",
        "release_type",
        "resolution",
        "release_group",
        "season",
        "episode",
        "size",
        "fingerprint",
        "infohash",
        "outcome",
        "reason",
        "duration_ms",
        "site_check",
        "personal_release",
        "artwork_url",
    )
    values = tuple(int(record[column]) if column in {"site_check", "personal_release"} else record[column] for column in columns)
    for attempt in range(4):
        try:
            with _record_lock, closing(connect_app_db(database_path(state_dir))) as db, db:
                cursor = db.execute(f"INSERT INTO history_items ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})", values)  # noqa: S608
                item_id = cast(int, cursor.lastrowid)
                db.executemany("INSERT INTO history_ids VALUES (?, ?, ?)", [(item_id, provider, value) for provider, value in cast(Mapping[str, str], record["ids"]).items()])
                db.executemany(
                    "INSERT OR REPLACE INTO history_trackers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (item_id, row["tracker"], row["status"], row["message"], row["link"], row["torrent_id"], row["duration"], _json(row["dupes"]), _json(row["slot"]))
                        for row in cast(list[Mapping[str, Any]], record["trackers"])
                    ],
                )
                db.executemany(
                    "INSERT INTO history_requests (item_id, tracker, name, link, reward, status, exact) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            item_id,
                            str(request.get("tracker", "")),
                            str(request.get("name", "")),
                            str(request.get("link", "")),
                            str(request.get("reward", "")),
                            str(request.get("status", "")),
                            int(bool(request.get("exact"))),
                        )
                        for request in cast(list[Mapping[str, Any]], record["requests"])
                    ],
                )
            return item_id
        except sqlite3.OperationalError as exc:
            if attempt == 3 or not any(reason in str(exc).lower() for reason in ("busy", "locked")):
                logger.debug(f"Upload history was not saved: {exc}")
                return None
            time.sleep(0.05 * (attempt + 1))
        except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
            logger.debug(f"Upload history was not saved: {exc}")
            return None
    return None


# Remembering a release between runs -------------------------------------------
#
# Keyed by content fingerprint, so a renamed folder or a fresh tmp/ directory
# still finds what an earlier run learned. Unlike the history list, this is
# also kept for debug runs: a person confirming IDs there confirms them for
# the real upload too.

_PROVIDER_LABELS = {
    "imdb": "IMDb",
    "tmdb": "TMDb",
    "tvdb": "TVDB",
    "tvmaze": "TVmaze",
    "mal": "MAL",
    "douban": "Douban",
    "igdb": "IGDB",
    "openlibrary": "Open Library",
    "isbn": "ISBN",
    "asin": "ASIN",
    "discogs_release": "Discogs release",
    "discogs_master": "Discogs master",
    "tpdb": "ThePornDB",
    "blvckout": "BLVCKOUT",
}
# Fields set by ID arguments, and IDs already resolved before the metadata search.
_MANUAL_ID_FIELDS = (
    "imdb_manual",
    "tmdb_manual",
    "tvdb_manual",
    "tvmaze_manual",
    "mal_manual",
    "douban_manual",
    "igdb_manual",
    "steam_manual",
    "music_discogs_id",
    "music_discogs_release_id",
    "music_discogs_master_id",
    "book_isbn",
    "book_asin",
    "openlibrary",
    "tpdb_manual",
    "blvckout_manual",
)
# IDs the metadata search copies from a manual field and keeps on a later pass.
_DERIVED_ID_FIELDS = {"tvdb_manual": "tvdb_id", "tvmaze_manual": "tvmaze_id", "mal_manual": "mal_id"}


def _id_number(value: object) -> int:
    """Return an ID as a number (``tt`` prefix allowed), or 0."""
    text = str(value or "").strip()
    return _positive_int(text[2:] if text.lower().startswith("tt") else text)


# Fields set together with a manual ID field, by its argument or by apply_saved_ids.
_COMPANION_ID_FIELDS = {"tmdb_manual": ("tmdb_manual_category",), "book_isbn": ("isbn",), "book_asin": ("asin",)}


def keep_given_ids(meta: Any, parser: Any, args: list[str] | tuple[str, ...]) -> None:
    """Keep the IDs ``args`` (a confirmation edit) gives, even when they equal a saved ID.

    Without this, an edit such as ``--tmdb tv/2 --no-saved-ids`` after saved
    ID tv/2 was applied would have that ID undone with the other saved ones.
    """
    filled = getattr(meta, "saved_id_fields", None)
    if not isinstance(filled, dict) or not filled:
        return
    for action in getattr(parser, "_actions", []):
        dest = getattr(action, "dest", "")
        options = getattr(action, "option_strings", [])
        if dest not in filled or not any(arg == option or arg.startswith(f"{option}=") for option in options for arg in args):
            continue
        for field_name in (dest, _DERIVED_ID_FIELDS.get(dest, ""), *_COMPANION_ID_FIELDS.get(dest, ())):
            cast(dict[str, Any], filled).pop(field_name, None)


def _undo_saved_ids(meta: Any) -> None:
    """Restore the fields an earlier pass filled from saved IDs, unless something changed them since.

    A confirmation edit prepares the release again on the same ``meta``; the
    saved IDs are then decided afresh (an ID given in the edit, or
    ``--no-saved-ids``, must not leave the earlier pass's IDs in place).
    """
    filled = dict(getattr(meta, "saved_id_fields", {}) or {})
    meta.saved_id_fields = {}
    for field_name, (previous, applied) in filled.items():
        current = getattr(meta, field_name, None)
        if current == applied or (_id_number(applied) and _id_number(current) == _id_number(applied)):
            setattr(meta, field_name, previous)


def _read_memory(fingerprint: str, state_dir: str | Path | None = None) -> dict[str, Any] | None:
    """Return the category, IDs and answers saved for a fingerprint, or None."""
    path = database_path(state_dir)
    if not fingerprint or not database_available(path):
        return None
    with closing(connect_app_db(path)) as db:
        row = db.execute("SELECT category, ids, answers FROM release_memory WHERE fingerprint = ?", (fingerprint,)).fetchone()
    if row is None:
        return None
    ids = _loads(row[1])
    answers = _loads(row[2])
    return {
        "category": str(row[0] or ""),
        "ids": {str(key): str(value) for key, value in ids.items() if value} if isinstance(ids, dict) else {},
        "answers": answers if isinstance(answers, dict) else {},
    }


async def load_release_memory(meta: Any) -> None:
    """Fingerprint the release, then reload the answers and confirmed IDs an earlier run saved for it.

    Answers already on ``meta`` (from ``--answer``) win. The IDs are only kept on
    ``meta.saved_ids`` here; :func:`apply_saved_ids` uses them once the category is known.
    """
    _undo_saved_ids(meta)
    path = str(getattr(meta, "path", "") or "")
    if not path:
        return
    try:
        fingerprint = await asyncio.to_thread(content_fingerprint, path)
        meta.release_fingerprint = fingerprint
        memory = await asyncio.to_thread(_read_memory, fingerprint)
    except (OSError, sqlite3.Error) as exc:
        logger.debug(f"Could not read what earlier runs saved for this release: {exc}")
        return
    # Saved answers are now on meta (or there were none), so saving them later may drop rejected ones.
    meta.release_memory_loaded = bool(fingerprint)
    if memory is None:
        return
    for key, value in memory["answers"].items():
        meta.manual_answers.setdefault(str(key), value)
    meta.saved_ids = {**memory["ids"], "category": memory["category"]} if memory["ids"] else {}


def apply_saved_ids(meta: Any) -> list[str]:
    """Use remembered IDs as if they had been given on the command line, for IDs not given there.

    They are applied only when the release still has the category it had when
    they were confirmed. Return a description of each ID used.
    """
    saved = dict(getattr(meta, "saved_ids", {}) or {})
    category = str(getattr(meta, "category", "") or "").upper()
    # XXX is only detected from markers in the name, so a confirmed adult video
    # without one would be prepared as a movie; restore XXX before that happens.
    restore_xxx = not category and str(saved.get("category", "")).upper() == "XXX" and not getattr(meta, "manual_category", None)
    if not saved or (not category and not restore_xxx):
        # Video categories are only known when the metadata search starts; try again then.
        return []
    # Decided once per run, whatever the outcome.
    meta.saved_ids = {}
    saved_category = saved.pop("category", "").upper()
    if getattr(meta, "no_saved_ids", False):
        return []
    # Each field set here is noted so a confirmation edit, which prepares the
    # release again, can undo it before the saved IDs are decided again.
    filled: dict[str, list[Any]] = {}
    meta.saved_id_fields = filled

    def assign(field_name: str, value: object) -> None:
        filled.setdefault(field_name, [getattr(meta, field_name, None), value])
        setattr(meta, field_name, value)

    # Saved IDs belong together: once any ID was given (for example a corrected
    # --imdb at the confirmation prompt), the others may no longer match it.
    # IDs found automatically (scene or tracker data) are replaced instead.
    # Checked before the category changes, which only the saved IDs justify.
    given = [field_name for field_name in _MANUAL_ID_FIELDS if getattr(meta, field_name, None)]
    if given:
        logger.debug(f"Not reusing saved IDs because IDs were given: {', '.join(given)}")
        return []
    if restore_xxx:
        category = "XXX"
        assign("category", category)
    if saved_category != category:
        # A video without an episode or season pattern is first guessed as MOVIE;
        # a TV category confirmed earlier replaces that guess, as --tmdb tv/ would,
        # and so does XXX for an adult video whose name carries no XXX marker.
        guessed_movie = category == "MOVIE" and not getattr(meta, "manual_category", None) and not getattr(meta, "tmdb_manual_category", "")
        if not (guessed_movie and saved_category in ("TV", "XXX")):
            return []
        category = saved_category
        assign("category", category)
    applied: list[str] = []

    def fill(field_name: str, provider: str, value: object, *copies: str) -> None:
        """Set one manual ID field (and the fields it is copied to) from a saved value and note it for the log."""
        if value in (None, "", 0):
            return
        assign(field_name, value)
        for copy in copies:
            assign(copy, value)
        if field_name in _DERIVED_ID_FIELDS:
            # The metadata search copies it there and keeps it on a later pass; undone with it.
            derived = _DERIVED_ID_FIELDS[field_name]
            filled.setdefault(derived, [getattr(meta, derived, None), value])
        applied.append(f"{_PROVIDER_LABELS.get(provider, provider)} {saved[provider]}")

    if category in {"MOVIE", "TV"}:
        if not getattr(meta, "no_imdb", False):
            fill("imdb_manual", "imdb", saved.get("imdb"))
        kind, _separator, number = saved.get("tmdb", "").partition("/")
        if _positive_int(number) and kind.upper() == category:
            fill("tmdb_manual", "tmdb", _positive_int(number))
            assign("tmdb_manual_category", category)
        fill("tvdb_manual", "tvdb", saved.get("tvdb"))
        fill("mal_manual", "mal", saved.get("mal"))
        fill("douban_manual", "douban", _positive_int(saved.get("douban")))
        if category == "TV":
            fill("tvmaze_manual", "tvmaze", _positive_int(saved.get("tvmaze")))
    elif category == "GAME":
        fill("igdb_manual", "igdb", saved.get("igdb"))
    elif category == "MUSIC":
        fill("music_discogs_release_id", "discogs_release", saved.get("discogs_release"))
        fill("music_discogs_master_id", "discogs_master", saved.get("discogs_master"))
    elif category == "BOOK":
        # As --isbn and --asin do (Args._apply_book_meta_overrides), the lookups read isbn and asin.
        fill("book_isbn", "isbn", saved.get("isbn"), "isbn")
        fill("book_asin", "asin", saved.get("asin"), "asin")
        fill("openlibrary", "openlibrary", saved.get("openlibrary"))
    elif category == "XXX":
        fill("tpdb_manual", "tpdb", saved.get("tpdb"))
        fill("blvckout_manual", "blvckout", saved.get("blvckout"))
    if category in {"MOVIE", "TV"} and (getattr(meta, "imdb_manual", None) or getattr(meta, "tmdb_manual", None)):
        # As when --imdb or --tmdb is given: confirmed IDs win over ones found automatically.
        meta.imdb_id = meta.imdb = meta.tmdb_id = meta.tmdb = None
    if applied:
        logger.info(f"[cyan]Using IDs confirmed for this release in an earlier run: {', '.join(applied)}. Use --no-saved-ids to search again.[/cyan]")
    return applied


def _trusted_ids(meta: Any) -> dict[str, str] | None:
    """Return the IDs an upload succeeded with, else those a person confirmed, else None.

    Confirmed IDs are the ones shown at "Is this correct?": an ID found later,
    for example by a tracker check, is only trusted once an upload used it.
    """
    statuses = getattr(meta, "tracker_status", {})
    if isinstance(statuses, Mapping) and any(isinstance(status, Mapping) and status.get("upload_success") is True for status in cast(Mapping[str, Any], statuses).values()):
        return external_ids(meta)
    if getattr(meta, "ids_confirmed", False) is True:
        return dict(getattr(meta, "confirmed_ids", {}) or {})
    return None


def remember_release(meta: Any, state_dir: str | Path | None = None) -> bool:
    """Save the release's manual answers, and its IDs when confirmed, for later runs. Return whether a row was written."""
    path = str(getattr(meta, "path", "") or "")
    fingerprint = str(getattr(meta, "release_fingerprint", "") or "") or (content_fingerprint(path) if path else "")
    if not fingerprint:
        return False
    answers: dict[str, Any] = dict(getattr(meta, "manual_answers", {}) or {})
    # An empty set (e.g. a release with no IDs) keeps what an earlier run confirmed.
    ids = _trusted_ids(meta) or None
    database = database_path(state_dir)
    if not answers and not ids and not database_available(database):
        return False
    with _record_lock, closing(connect_app_db(database)) as db, db:
        existing = db.execute("SELECT category, ids, answers FROM release_memory WHERE fingerprint = ?", (fingerprint,)).fetchone()
        if existing is not None and not getattr(meta, "release_memory_loaded", False):
            # The saved answers never reached meta (the item stopped first, or
            # reading them failed): keep them, with this run's answers on top.
            saved_answers = _loads(existing[2])
            if isinstance(saved_answers, dict):
                answers = {**cast(dict[str, Any], saved_answers), **answers}
        if existing is None and not answers and not ids:
            return False
        category = _text(getattr(meta, "category", ""), 20).upper() if ids else (existing[0] if existing else "")
        stored_ids = _json(ids) if ids is not None else (existing[1] if existing else "")
        db.execute(
            """
            INSERT INTO release_memory (fingerprint, updated_at, category, ids, answers) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (fingerprint) DO UPDATE SET
                updated_at = excluded.updated_at, category = excluded.category, ids = excluded.ids, answers = excluded.answers
            """,
            (fingerprint, datetime.now(UTC).isoformat(), category, stored_ids, _json(answers)),
        )
    return True


async def record_item_async(meta: Any, tracker_class_map: Mapping[str, Any], *, outcome: str | None = None, reason: str = "") -> None:
    """Record a finished item and remember the release without blocking the event loop.

    Neither may break an upload, so failures are only logged.
    """
    global _item
    try:
        await asyncio.to_thread(remember_release, meta)
    except Exception as exc:
        logger.debug(f"Release IDs and answers were not saved: {exc}")
    try:
        record = await asyncio.to_thread(build_item_record, meta, tracker_class_map, outcome=outcome, reason=reason)
        if record is not None:
            await asyncio.to_thread(record_item, record)
            if _retention_days:
                await asyncio.to_thread(prune_history, _retention_days)
    except Exception as exc:
        logger.debug(f"Upload history was not saved: {exc}")
    finally:
        with _state_lock:
            _item = None


# Reading the history (Web UI) ------------------------------------------------

TRACKER_STATUSES = ("success", "failed", "dupe", "banned", "skipped")
MAX_PAGE_SIZE = 200
# Largest value SQLite can bind; larger IDs or offsets cannot match anything.
_SQLITE_MAX_INTEGER = 2**63 - 1
_ITEM_COLUMNS = (
    "id",
    "started_at",
    "finished_at",
    "source",
    "path",
    "name",
    "title",
    "year",
    "category",
    "release_type",
    "resolution",
    "release_group",
    "season",
    "episode",
    "size",
    "fingerprint",
    "infohash",
    "outcome",
    "reason",
    "duration_ms",
    "site_check",
    "personal_release",
    "artwork_url",
)
_SUMMARY_COLUMNS = tuple(column for column in _ITEM_COLUMNS if column not in {"started_at", "fingerprint", "infohash", "duration_ms"})
_LIKE_ESCAPE = "\\"


def _instant(value: str, label: str) -> str:
    """Normalize an ISO date or date-time to the UTC form stored in ``finished_at``."""
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO 8601 date or date-time") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def _like_pattern(term: str) -> str:
    escaped = term.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2).replace("%", f"{_LIKE_ESCAPE}%").replace("_", f"{_LIKE_ESCAPE}_")
    return f"%{escaped}%"


# A search term without a prefix also matches these IDs, whose stored form
# (tt0123456, movie/42, an ISBN, an ASIN, OL123W) cannot be mistaken for a
# year or another number; "provider:value" (e.g. tvdb:12345) matches any ID.
_DISTINCT_ID_PROVIDERS = ("imdb", "tmdb", "isbn", "asin", "openlibrary", "tpdb")
_ID_SEARCH_ALIASES = {"discogs": ("discogs_release", "discogs_master")}


def _id_search_key(value: str) -> str:
    """Compare IDs without case or hyphens (ISBNs are often written with them)."""
    return value.strip().replace("-", "").upper()


def _id_exists(providers: tuple[str, ...], values: list[str]) -> tuple[str, list[object]]:
    """Return a clause matching entries with one of ``values`` for one of ``providers``."""
    if not values:
        return "0", []
    provider_marks = ", ".join("?" for _ in providers)
    value_marks = ", ".join("?" for _ in values)
    clause = (
        f"EXISTS (SELECT 1 FROM history_ids i WHERE i.item_id = history_items.id AND i.provider IN ({provider_marks}) AND UPPER(REPLACE(i.value, '-', '')) IN ({value_marks}))"  # noqa: S608
    )
    return clause, [*providers, *values]


def _plain_id_values(term: str) -> list[str]:
    """Return the stored forms a search term matches among the distinctive IDs."""
    key = _id_search_key(term)
    values = [key] if key else []
    imdb = _id_number(key) if key.startswith("TT") else 0
    if imdb and f"TT{imdb:07d}" != key:
        # tt123456 and tt0123456 are the same title.
        values.append(f"TT{imdb:07d}")
    return values


def _searched_id_values(provider: str, value: str) -> list[str]:
    """Return the stored forms of an ID typed after ``provider:``."""
    key = _id_search_key(value)
    if not key:
        return []
    if provider == "imdb":
        number = _id_number(key)
        return [f"TT{number:07d}"] if number else []
    if provider == "tmdb":
        kind, separator, number = key.partition("/")
        if separator:
            return [f"{kind}/{_positive_int(number)}"] if kind in {"MOVIE", "TV"} and _positive_int(number) else []
        number_value = _positive_int(key)
        return [f"MOVIE/{number_value}", f"TV/{number_value}"] if number_value else []
    if provider in {"isbn", "asin", "openlibrary", "blvckout"}:
        return [key]
    if provider == "tpdb":
        # Stored as scenes/ID or movies/ID; a bare ID matches either.
        return [key] if "/" in key else [f"{kind}/{key}" for kind in ("SCENES", "MOVIES", "JAV")]
    number = _positive_int(key)
    return [str(number)] if number else []


def _discogs_search(provider: str, value: str) -> tuple[tuple[str, ...], list[str]]:
    """Return the providers and ID a Discogs search term matches.

    A kind written in the value (``master/45`` or a master URL) selects that
    kind; a bare ID searches both unless the prefix names one, and a kind that
    contradicts the prefix matches nothing.
    """
    from src.music.sources import DiscogsEnricher

    reference = DiscogsEnricher.parse_reference(value.strip(), "")
    if reference is None:
        return _ID_SEARCH_ALIASES["discogs"], []
    kind, identifier = reference
    if not kind:
        return _ID_SEARCH_ALIASES.get(provider, (provider,)), [identifier]
    if provider not in {"discogs", f"discogs_{kind}"}:
        return (provider,), []
    return (f"discogs_{kind}",), [identifier]


def _prefixed_id_filter(term: str) -> tuple[str, list[object]] | None:
    """Return the clause for a ``provider:value`` term, or None when the term has no known provider."""
    prefix, separator, value = term.partition(":")
    provider = prefix.lower()
    if not separator or (provider not in _PROVIDER_LABELS and provider not in _ID_SEARCH_ALIASES):
        return None
    if provider.startswith("discogs"):
        return _id_exists(*_discogs_search(provider, value))
    # A known provider with a malformed ID matches nothing rather than every name containing it.
    return _id_exists(_ID_SEARCH_ALIASES.get(provider, (provider,)), _searched_id_values(provider, value))


def _filters(
    *,
    search: str,
    category: str,
    tracker: str,
    tracker_status: str,
    has_requests: bool,
    after: str,
    before: str,
) -> tuple[list[str], list[object]]:
    clauses: list[str] = []
    parameters: list[object] = []
    for term in search.split()[:10]:
        prefixed = _prefixed_id_filter(term)
        if prefixed is not None:
            clauses.append(prefixed[0])
            parameters.extend(prefixed[1])
            continue
        pattern = _like_pattern(term)
        id_clause, id_parameters = _id_exists(_DISTINCT_ID_PROVIDERS, _plain_id_values(term))
        clauses.append("(" + " OR ".join([*(f"{column} LIKE ? ESCAPE ?" for column in ("name", "title", "path", "release_group")), id_clause]) + ")")
        for _column in range(4):
            parameters.extend([pattern, _LIKE_ESCAPE])
        parameters.extend(id_parameters)
    if category:
        clauses.append("category = ?")
        parameters.append(category.upper())
    if tracker_status and tracker_status not in TRACKER_STATUSES:
        raise ValueError(f"tracker_status must be one of: {', '.join(TRACKER_STATUSES)}")
    if tracker:
        clause = "EXISTS (SELECT 1 FROM history_trackers t WHERE t.item_id = history_items.id AND t.tracker = ?"
        parameters.append(_tracker_key(tracker))
        if tracker_status:
            clause += " AND t.status = ?"
            parameters.append(tracker_status)
        clauses.append(clause + ")")
    elif tracker_status:
        clauses.append("EXISTS (SELECT 1 FROM history_trackers t WHERE t.item_id = history_items.id AND t.status = ?)")
        parameters.append(tracker_status)
    if has_requests:
        clauses.append("EXISTS (SELECT 1 FROM history_requests r WHERE r.item_id = history_items.id)")
    if after:
        clauses.append("finished_at >= ?")
        parameters.append(_instant(after, "after"))
    if before:
        clauses.append("finished_at < ?")
        parameters.append(_instant(before, "before"))
    return clauses, parameters


def _empty_page(limit: int, offset: int) -> dict[str, Any]:
    return {
        "items": [],
        "total": 0,
        "limit": limit,
        "offset": offset,
        "counts": dict.fromkeys(OUTCOMES, 0),
        "facets": {"categories": [], "trackers": []},
    }


def _row_dict(columns: tuple[str, ...], row: tuple[Any, ...]) -> dict[str, Any]:
    item = dict(zip(columns, row, strict=True))
    for flag in ("site_check", "personal_release"):
        if flag in item:
            item[flag] = bool(item[flag])
    return item


def list_items(
    state_dir: str | Path | None = None,
    *,
    search: str = "",
    category: str = "",
    tracker: str = "",
    tracker_status: str = "",
    outcome: str = "",
    has_requests: bool = False,
    after: str = "",
    before: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Return one page of history entries, newest first, with outcome counts and filter options."""
    limit = max(1, min(MAX_PAGE_SIZE, int(limit)))
    offset = max(0, min(_SQLITE_MAX_INTEGER, int(offset)))
    if outcome and outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of: {', '.join(OUTCOMES)}")
    clauses, parameters = _filters(
        search=search,
        category=category,
        tracker=tracker,
        tracker_status=tracker_status,
        has_requests=has_requests,
        after=after,
        before=before,
    )
    page = _empty_page(limit, offset)
    path = database_path(state_dir)
    if not database_available(path):
        return page
    # Outcome counts ignore the outcome filter itself, so every chip keeps its number.
    base_where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    page_clauses = [*clauses, "outcome = ?"] if outcome else clauses
    page_parameters = [*parameters, outcome] if outcome else parameters
    page_where = f"WHERE {' AND '.join(page_clauses)}" if page_clauses else ""
    with closing(connect_app_db(path)) as db:
        for row_outcome, count in db.execute(f"SELECT outcome, COUNT(*) FROM history_items {base_where} GROUP BY outcome", parameters):  # noqa: S608
            if row_outcome in page["counts"]:
                page["counts"][row_outcome] = int(count)
        page["total"] = int(db.execute(f"SELECT COUNT(*) FROM history_items {page_where}", page_parameters).fetchone()[0])  # noqa: S608
        rows = db.execute(
            f"SELECT {', '.join(_SUMMARY_COLUMNS)} FROM history_items {page_where} ORDER BY finished_at DESC, id DESC LIMIT ? OFFSET ?",  # noqa: S608
            [*page_parameters, limit, offset],
        ).fetchall()
        items = [_row_dict(_SUMMARY_COLUMNS, row) for row in rows]
        by_id = {item["id"]: item for item in items}
        for item in items:
            item.update(trackers=[], request_count=0, ids={})
        if by_id:
            marks = ", ".join("?" for _ in by_id)
            ids = list(by_id)
            for item_id, name, status, link in db.execute(
                f"SELECT item_id, tracker, status, link FROM history_trackers WHERE item_id IN ({marks}) ORDER BY tracker",  # noqa: S608
                ids,
            ):
                by_id[item_id]["trackers"].append({"tracker": name, "status": status, "link": link})
            for item_id, count in db.execute(f"SELECT item_id, COUNT(*) FROM history_requests WHERE item_id IN ({marks}) GROUP BY item_id", ids):  # noqa: S608
                by_id[item_id]["request_count"] = int(count)
            for item_id, provider, value in db.execute(f"SELECT item_id, provider, value FROM history_ids WHERE item_id IN ({marks})", ids):  # noqa: S608
                by_id[item_id]["ids"][provider] = value
        page["items"] = items
        page["facets"] = {
            "categories": [row[0] for row in db.execute("SELECT DISTINCT category FROM history_items WHERE category != '' ORDER BY category")],
            "trackers": [row[0] for row in db.execute("SELECT DISTINCT tracker FROM history_trackers ORDER BY tracker")],
        }
    return page


def id_link(provider: str, value: str) -> str:
    """Return the public page of an external ID, or "" when it has none."""
    if provider == "imdb":
        return f"https://www.imdb.com/title/{value}/" if value.startswith("tt") and value[2:].isdigit() else ""
    if provider == "tmdb":
        kind, _separator, number = value.partition("/")
        return f"https://www.themoviedb.org/{kind}/{number}" if kind in {"movie", "tv"} and number.isdigit() else ""
    if provider == "openlibrary":
        kinds = {"W": "works", "M": "books", "A": "authors"}
        identifier = value.upper()
        valid = identifier.startswith("OL") and identifier[2:-1].isdigit() and identifier[-1:] in kinds
        return f"https://openlibrary.org/{kinds[identifier[-1]]}/{identifier}" if valid else ""
    if not value.isdigit():
        return ""
    return {
        "tvdb": f"https://thetvdb.com/dereferrer/series/{value}",
        "tvmaze": f"https://www.tvmaze.com/shows/{value}",
        "mal": f"https://myanimelist.net/anime/{value}",
        "douban": f"https://movie.douban.com/subject/{value}/",
        "discogs_release": f"https://www.discogs.com/release/{value}",
        "discogs_master": f"https://www.discogs.com/master/{value}",
    }.get(provider, "")


def _loads(value: str) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except ValueError:
        return None


def get_item(item_id: int, state_dir: str | Path | None = None) -> dict[str, Any] | None:
    """Return one entry with its IDs, tracker results and request matches, or None."""
    path = database_path(state_dir)
    if not 0 < int(item_id) <= _SQLITE_MAX_INTEGER or not database_available(path):
        return None
    with closing(connect_app_db(path)) as db:
        row = db.execute(f"SELECT {', '.join(_ITEM_COLUMNS)} FROM history_items WHERE id = ?", (int(item_id),)).fetchone()  # noqa: S608
        if row is None:
            return None
        item = _row_dict(_ITEM_COLUMNS, row)
        item["ids"] = [
            {"provider": provider, "value": value, "link": id_link(provider, value)}
            for provider, value in db.execute("SELECT provider, value FROM history_ids WHERE item_id = ? ORDER BY provider", (item["id"],))
        ]
        item["trackers"] = [
            {
                "tracker": tracker,
                "status": status,
                "message": message,
                "link": link,
                "torrent_id": torrent_id,
                "duration": duration,
                "dupes": _loads(dupes),
                "slot": _loads(slot),
            }
            for tracker, status, message, link, torrent_id, duration, dupes, slot in db.execute(
                "SELECT tracker, status, message, link, torrent_id, duration, dupes, slot FROM history_trackers WHERE item_id = ? ORDER BY tracker",
                (item["id"],),
            )
        ]
        item["requests"] = [
            {"tracker": tracker, "name": name, "link": link, "reward": reward, "status": status, "exact": bool(exact)}
            for tracker, name, link, reward, status, exact in db.execute(
                "SELECT tracker, name, link, reward, status, exact FROM history_requests WHERE item_id = ? ORDER BY id",
                (item["id"],),
            )
        ]
    return item


def delete_item(item_id: int, state_dir: str | Path | None = None) -> bool:
    """Remove one entry and its details; return whether it existed."""
    path = database_path(state_dir)
    if not 0 < int(item_id) <= _SQLITE_MAX_INTEGER or not database_available(path):
        return False
    with _record_lock, closing(connect_app_db(path)) as db, db:
        return db.execute("DELETE FROM history_items WHERE id = ?", (int(item_id),)).rowcount > 0


def clear_history(state_dir: str | Path | None = None) -> int:
    """Remove every entry; statistics and other tables are untouched. Return the number removed."""
    path = database_path(state_dir)
    if not database_available(path):
        return 0
    with _record_lock, closing(connect_app_db(path)) as db, db:
        return db.execute("DELETE FROM history_items").rowcount


# Export and retention -----------------------------------------------------------

EXPORT_MAX_ITEMS = 100_000
EXPORT_CSV_COLUMNS = (
    "finished_at",
    "name",
    "title",
    "year",
    "category",
    "release_type",
    "resolution",
    "release_group",
    "season",
    "episode",
    "size",
    "outcome",
    "reason",
    "source",
    "path",
    "ids",
    "trackers",
    "links",
    "requests",
)
# A spreadsheet runs a cell starting with these as a formula; names and
# messages come from release folders and trackers, so they are neutralized.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def export_items(
    state_dir: str | Path | None = None,
    *,
    search: str = "",
    category: str = "",
    tracker: str = "",
    tracker_status: str = "",
    outcome: str = "",
    has_requests: bool = False,
    after: str = "",
    before: str = "",
) -> list[dict[str, Any]]:
    """Return every entry matching the filters (newest first, at most EXPORT_MAX_ITEMS) with all details."""
    if outcome and outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of: {', '.join(OUTCOMES)}")
    clauses, parameters = _filters(
        search=search,
        category=category,
        tracker=tracker,
        tracker_status=tracker_status,
        has_requests=has_requests,
        after=after,
        before=before,
    )
    if outcome:
        clauses.append("outcome = ?")
        parameters.append(outcome)
    path = database_path(state_dir)
    if not database_available(path):
        return []
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with closing(connect_app_db(path)) as db:
        # One read transaction: an item recorded while exporting must not
        # appear in the detail queries without appearing in the item query.
        db.execute("BEGIN")
        rows = db.execute(
            f"SELECT {', '.join(_ITEM_COLUMNS)} FROM history_items {where} ORDER BY finished_at DESC, id DESC LIMIT {EXPORT_MAX_ITEMS}",  # noqa: S608
            parameters,
        ).fetchall()
        items = [_row_dict(_ITEM_COLUMNS, row) for row in rows]
        by_id = {item["id"]: item for item in items}
        for item in items:
            item.update(ids={}, trackers=[], requests=[])
        # The details are read for the selected items only, without filtering again.
        db.execute("CREATE TEMP TABLE IF NOT EXISTS export_selection (id INTEGER PRIMARY KEY)")
        db.execute("DELETE FROM export_selection")
        db.executemany("INSERT INTO export_selection VALUES (?)", ((item_id,) for item_id in by_id))
        for item_id, provider, value in db.execute("SELECT item_id, provider, value FROM history_ids JOIN export_selection s ON s.id = item_id ORDER BY provider"):
            by_id[item_id]["ids"][provider] = value
        for item_id, name, status, message, link, torrent_id, duration in db.execute(
            "SELECT item_id, tracker, status, message, link, torrent_id, duration FROM history_trackers JOIN export_selection s ON s.id = item_id ORDER BY tracker"
        ):
            by_id[item_id]["trackers"].append({"tracker": name, "status": status, "message": message, "link": link, "torrent_id": torrent_id, "duration": duration})
        for item_id, name, request_name, link, reward, status, exact in db.execute(
            "SELECT item_id, tracker, name, link, reward, status, exact FROM history_requests JOIN export_selection s ON s.id = item_id ORDER BY history_requests.id"
        ):
            by_id[item_id]["requests"].append({"tracker": name, "name": request_name, "link": link, "reward": reward, "status": status, "exact": bool(exact)})
        db.commit()
    return items


def _csv_cell(value: object) -> str:
    """Return a CSV cell that a spreadsheet will show as text, never run as a formula."""
    text = "" if value is None else str(value)
    # Some importers trim leading whitespace before deciding a cell is a formula.
    return f"'{text}" if text.lstrip(" \t\r\n").startswith(_FORMULA_PREFIXES) else text


def export_csv(items: list[dict[str, Any]]) -> str:
    """Render exported entries as CSV, one row per entry, with list fields joined by "; "."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(EXPORT_CSV_COLUMNS)
    for item in items:
        flattened = {
            **item,
            "ids": "; ".join(f"{provider}={value}" for provider, value in item["ids"].items()),
            "trackers": "; ".join(f"{tracker['tracker']}={tracker['status']}" for tracker in item["trackers"]),
            "links": "; ".join(f"{tracker['tracker']}={tracker['link']}" for tracker in item["trackers"] if tracker["link"]),
            "requests": "; ".join(f"{request['tracker']}: {request['name']}" + (f" ({request['reward']})" if request["reward"] else "") for request in item["requests"]),
        }
        writer.writerow([_csv_cell(flattened.get(column)) for column in EXPORT_CSV_COLUMNS])
    return buffer.getvalue()


def history_retention_days(config: Mapping[str, Any] | None) -> int:
    """Days entries are kept (``DEFAULT.history_retention_days``); 0 keeps them forever."""
    default = config.get("DEFAULT") if isinstance(config, Mapping) else None
    value = cast(Mapping[str, Any], default).get("history_retention_days", 0) if isinstance(default, Mapping) else 0
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except TypeError, ValueError, OverflowError:
        return 0


def prune_history(days: int, state_dir: str | Path | None = None) -> int:
    """Remove entries that finished more than ``days`` days ago; return how many were removed."""
    path = database_path(state_dir)
    if days <= 0 or not database_available(path):
        return 0
    try:
        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    except OverflowError:
        # Older than any date that can be represented: nothing is old enough.
        return 0
    with _record_lock, closing(connect_app_db(path)) as db, db:
        return db.execute("DELETE FROM history_items WHERE finished_at < ?", (cutoff,)).rowcount
