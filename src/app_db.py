"""The application's single SQLite database.

Statistics, API-key expiry observations and the upload history live in one
file below the user-state directory. Each feature owns its tables; this module
only opens connections and applies the numbered schema migrations, so the
database is created and upgraded the same way by the CLI, upload children and
the Web UI server.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

from src.app_paths import DATA_DIR

DATABASE_FILENAME = "upload_assistant.sqlite3"
# Files that held these tables before the shared database existed. They are
# read once, when the shared database is created, and never written again.
LEGACY_STATS_FILENAME = "stats.sqlite3"
LEGACY_API_KEY_EXPIRY_FILENAME = "api_key_expiry.sqlite3"


# Threads of one process opening a new database wait for each other here;
# other processes are serialized by the write lock taken in _migrate.
_migration_lock = threading.Lock()
# Total time spent retrying the WAL switch; each attempt can also wait busy_timeout.
_WAL_RETRY_SECONDS = 5.0


class NewerSchemaError(sqlite3.DatabaseError):
    """Raised when the database was created by a newer Upload Assistant."""


def database_path(state_dir: str | Path | None = None) -> Path:
    """Return the shared database path for a user-state directory (default: the active one)."""
    return Path(state_dir) / "data" / DATABASE_FILENAME if state_dir is not None else DATA_DIR / DATABASE_FILENAME


def database_available(path: Path) -> bool:
    """Return whether opening ``path`` would find stored data, including data still in an old file."""
    return any((path.parent / name).is_file() for name in (path.name, LEGACY_STATS_FILENAME, LEGACY_API_KEY_EXPIRY_FILENAME))


def _legacy_rows(path: Path, query: str) -> list[tuple[object, ...]]:
    """Read rows from an old per-feature database without changing it."""
    if not path.is_file():
        return []
    try:
        with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)) as legacy:
            return list(legacy.execute(query).fetchall())
    except sqlite3.OperationalError as exc:
        if any(reason in str(exc).lower() for reason in ("busy", "locked")):
            # Still being written, e.g. by an older version that is running:
            # abort the migration so the import is tried again on the next open.
            raise
        # Missing tables or an unreadable file: there is nothing to import.
        return []
    except sqlite3.Error, OSError, ValueError:
        return []


def _import_legacy_stats(db: sqlite3.Connection, data_dir: Path) -> None:
    legacy = data_dir / LEGACY_STATS_FILENAME
    version = _legacy_rows(legacy, "SELECT value FROM stats_meta WHERE key = 'schema_version'")
    if not version or version[0][0] != "2":
        # Version 1 buckets were discarded by the old module too.
        return
    columns = {str(row[1]) for row in _legacy_rows(legacy, "PRAGMA table_info(stats_daily)")}
    if "destination" not in columns:
        return
    if "content_seconds" in columns:
        query = "SELECT day, family, service, operation, outcome, category, source, mode, destination, count, duration_ms, content_seconds, bytes FROM stats_daily"
    else:
        query = "SELECT day, family, service, operation, outcome, category, source, mode, destination, count, duration_ms, 0, bytes FROM stats_daily"
    rows = _legacy_rows(legacy, query)
    db.executemany(
        """
        INSERT OR IGNORE INTO stats_daily
            (day, family, service, operation, outcome, category, source, mode, destination, count, duration_ms, content_seconds, bytes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    reset_at = _legacy_rows(legacy, "SELECT value FROM stats_meta WHERE key = 'reset_at'")
    if reset_at:
        db.execute("INSERT OR REPLACE INTO stats_meta VALUES ('reset_at', ?)", (str(reset_at[0][0]),))


def _import_legacy_api_key_expiry(db: sqlite3.Connection, data_dir: Path) -> None:
    rows = _legacy_rows(data_dir / LEGACY_API_KEY_EXPIRY_FILENAME, "SELECT identity, expires_at, checked_at FROM api_key_expiry")
    db.executemany("INSERT OR IGNORE INTO api_key_expiry VALUES (?, ?, ?)", rows)


def _migrate_1(db: sqlite3.Connection, data_dir: Path) -> None:
    """Statistics and API-key expiry, imported from their old files when present."""
    db.execute("CREATE TABLE stats_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    db.execute(
        """
        CREATE TABLE stats_daily (
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
    db.execute("CREATE TABLE api_key_expiry (identity TEXT PRIMARY KEY, expires_at TEXT, checked_at TEXT NOT NULL)")
    _import_legacy_stats(db, data_dir)
    _import_legacy_api_key_expiry(db, data_dir)


def _migrate_2(db: sqlite3.Connection, _data_dir: Path) -> None:
    """Upload history: one row per processed item, with its IDs, tracker results and request matches."""
    db.execute(
        """
        CREATE TABLE history_items (
            id INTEGER PRIMARY KEY,
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            path TEXT NOT NULL,
            name TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            year INTEGER,
            category TEXT NOT NULL DEFAULT '',
            release_type TEXT NOT NULL DEFAULT '',
            resolution TEXT NOT NULL DEFAULT '',
            release_group TEXT NOT NULL DEFAULT '',
            season TEXT NOT NULL DEFAULT '',
            episode TEXT NOT NULL DEFAULT '',
            size INTEGER NOT NULL DEFAULT 0,
            fingerprint TEXT NOT NULL DEFAULT '',
            infohash TEXT NOT NULL DEFAULT '',
            outcome TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            duration_ms INTEGER NOT NULL DEFAULT 0,
            site_check INTEGER NOT NULL DEFAULT 0,
            personal_release INTEGER NOT NULL DEFAULT 0,
            artwork_url TEXT NOT NULL DEFAULT ''
        )
        """
    )
    db.execute("CREATE INDEX history_items_finished_at ON history_items (finished_at)")
    db.execute("CREATE INDEX history_items_fingerprint ON history_items (fingerprint)")
    db.execute(
        """
        CREATE TABLE history_ids (
            item_id INTEGER NOT NULL REFERENCES history_items (id) ON DELETE CASCADE,
            provider TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY (item_id, provider)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE history_trackers (
            item_id INTEGER NOT NULL REFERENCES history_items (id) ON DELETE CASCADE,
            tracker TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT NOT NULL DEFAULT '',
            link TEXT NOT NULL DEFAULT '',
            torrent_id TEXT NOT NULL DEFAULT '',
            duration REAL,
            dupes TEXT NOT NULL DEFAULT '',
            slot TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (item_id, tracker)
        )
        """
    )
    db.execute("CREATE INDEX history_trackers_tracker ON history_trackers (tracker, status)")
    db.execute(
        """
        CREATE TABLE history_requests (
            id INTEGER PRIMARY KEY,
            item_id INTEGER NOT NULL REFERENCES history_items (id) ON DELETE CASCADE,
            tracker TEXT NOT NULL,
            name TEXT NOT NULL,
            link TEXT NOT NULL DEFAULT '',
            reward TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            exact INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    db.execute("CREATE INDEX history_requests_item ON history_requests (item_id)")


def _migrate_3(db: sqlite3.Connection, _data_dir: Path) -> None:
    """What earlier runs learned about a release (confirmed IDs and manual answers), by content fingerprint."""
    db.execute(
        """
        CREATE TABLE release_memory (
            fingerprint TEXT PRIMARY KEY,
            updated_at TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '',
            ids TEXT NOT NULL DEFAULT '',
            answers TEXT NOT NULL DEFAULT ''
        )
        """
    )


# Append only: a migration that has shipped must never change.
MIGRATIONS: tuple[Callable[[sqlite3.Connection, Path], None], ...] = (_migrate_1, _migrate_2, _migrate_3)
SCHEMA_VERSION = len(MIGRATIONS)


def _schema_version(db: sqlite3.Connection) -> int:
    return int(db.execute("PRAGMA user_version").fetchone()[0])


def _enable_wal(db: sqlite3.Connection) -> None:
    """Switch to WAL; another connection reading the new file can briefly hold the lock this needs."""
    deadline = time.monotonic() + _WAL_RETRY_SECONDS
    while True:
        try:
            db.execute("PRAGMA journal_mode = WAL")
            return
        except sqlite3.OperationalError as exc:
            if time.monotonic() >= deadline or not any(reason in str(exc).lower() for reason in ("busy", "locked")):
                raise
            time.sleep(0.1)


def _migrate(db: sqlite3.Connection, path: Path) -> None:
    if _schema_version(db) == SCHEMA_VERSION:
        return
    # Several processes may open a new database at once; the write lock makes
    # exactly one of them apply each migration.
    db.execute("BEGIN IMMEDIATE")
    try:
        version = _schema_version(db)
        if version > SCHEMA_VERSION:
            raise NewerSchemaError(f"{path.name} was created by a newer version of Upload Assistant")
        for number in range(version + 1, SCHEMA_VERSION + 1):
            MIGRATIONS[number - 1](db, path.parent)
        db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise


def _restrict_permissions(path: Path) -> None:
    """Keep the database readable by its owner only: the history holds release names, paths and links.

    The file is created with mode 0600 before SQLite opens it, and SQLite gives
    its -wal and -shm files the same mode. Files left more open by an earlier
    version are tightened. On Windows the per-user profile folder is already private.
    """
    if os.name == "nt":
        return
    try:
        path.touch(mode=0o600, exist_ok=True)
    except OSError:
        return
    for candidate in (path, path.with_name(f"{path.name}-wal"), path.with_name(f"{path.name}-shm")):
        try:
            if candidate.stat().st_mode & 0o077:
                candidate.chmod(0o600)
        except OSError:
            continue


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open the shared database, creating or upgrading its schema on first use.

    Callers own the connection: close it (``contextlib.closing``) and commit
    writes with ``with db:``, as with a plain ``sqlite3`` connection.
    """
    path = path or database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _restrict_permissions(path)
    db = sqlite3.connect(path, timeout=5)
    try:
        db.execute("PRAGMA busy_timeout = 5000")
        db.execute("PRAGMA foreign_keys = ON")
        # Checked on every open (a cheap header read), so a file replaced while
        # running is migrated too, and a newer one is refused before any change.
        version = _schema_version(db)
        if version > SCHEMA_VERSION:
            raise NewerSchemaError(f"{path.name} was created by a newer version of Upload Assistant")
        if version < SCHEMA_VERSION:
            with _migration_lock:
                _enable_wal(db)
                # Migrations manage their own BEGIN/COMMIT.
                db.isolation_level = None
                try:
                    _migrate(db, path)
                finally:
                    db.isolation_level = "DEFERRED"
    except BaseException:
        db.close()
        raise
    return db
