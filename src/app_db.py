"""The application's single SQLite database.

Statistics, API-key expiry observations and the upload history live in one
file below the user-state directory. Each feature owns its tables; this module
only opens connections and applies the numbered schema migrations, so the
database is created and upgraded the same way by the CLI, upload children and
the Web UI server.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

from src.app_paths import DATA_DIR

DATABASE_FILENAME = "upload_assistant.sqlite3"
# Files that held these tables before the shared database existed. They are
# read once, when the shared database is created, and never written again.
LEGACY_STATS_FILENAME = "stats.sqlite3"
LEGACY_API_KEY_EXPIRY_FILENAME = "api_key_expiry.sqlite3"

_init_lock = threading.Lock()
_initialized_paths: set[Path] = set()


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
        with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=2)) as legacy:
            return list(legacy.execute(query).fetchall())
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


# Append only: a migration that has shipped must never change.
MIGRATIONS: tuple[Callable[[sqlite3.Connection, Path], None], ...] = (_migrate_1,)
SCHEMA_VERSION = len(MIGRATIONS)


def _schema_version(db: sqlite3.Connection) -> int:
    return int(db.execute("PRAGMA user_version").fetchone()[0])


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


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open the shared database, creating or upgrading its schema on first use.

    Callers own the connection: close it (``contextlib.closing``) and commit
    writes with ``with db:``, as with a plain ``sqlite3`` connection.
    """
    path = path or database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5)
    try:
        db.execute("PRAGMA busy_timeout = 5000")
        db.execute("PRAGMA foreign_keys = ON")
        key = path.resolve()
        with _init_lock:
            if key not in _initialized_paths:
                db.execute("PRAGMA journal_mode = WAL")
                # Migrations manage their own BEGIN/COMMIT.
                db.isolation_level = None
                try:
                    _migrate(db, path)
                finally:
                    db.isolation_level = "DEFERRED"
                _initialized_paths.add(key)
            elif _schema_version(db) > SCHEMA_VERSION:
                raise NewerSchemaError(f"{path.name} was created by a newer version of Upload Assistant")
    except BaseException:
        db.close()
        raise
    return db
