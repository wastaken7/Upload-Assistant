import sqlite3
from contextlib import closing

import pytest

from src import app_db


def test_new_database_has_the_latest_schema(tmp_path):
    path = app_db.database_path(tmp_path)

    with closing(app_db.connect(path)) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert db.execute("PRAGMA user_version").fetchone() == (app_db.SCHEMA_VERSION,)
        assert db.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    assert {"stats_daily", "stats_meta", "api_key_expiry"} <= tables
    assert path == tmp_path / "data" / app_db.DATABASE_FILENAME


def test_reopening_does_not_apply_migrations_again(tmp_path, monkeypatch):
    path = app_db.database_path(tmp_path)
    app_db.connect(path).close()

    def unexpected(*_args):
        raise AssertionError("migration applied twice")

    monkeypatch.setattr(app_db, "MIGRATIONS", (unexpected,) * app_db.SCHEMA_VERSION)
    with closing(app_db.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone() == (app_db.SCHEMA_VERSION,)


def test_newer_database_is_refused_and_left_unchanged(tmp_path):
    path = app_db.database_path(tmp_path)
    path.parent.mkdir(parents=True)
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA user_version = 999")

    with pytest.raises(app_db.NewerSchemaError):
        app_db.connect(path)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone() == (999,)
        assert db.execute("PRAGMA journal_mode").fetchone() == ("delete",)


def test_a_database_replaced_while_running_is_migrated_again(tmp_path):
    path = app_db.database_path(tmp_path)
    app_db.connect(path).close()
    for leftover in path.parent.glob(f"{path.name}*"):
        leftover.unlink()

    with closing(app_db.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone() == (app_db.SCHEMA_VERSION,)
        assert db.execute("SELECT COUNT(*) FROM stats_daily").fetchone() == (0,)


def test_a_busy_legacy_file_postpones_the_migration_until_it_can_be_read(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    legacy = data_dir / app_db.LEGACY_API_KEY_EXPIRY_FILENAME
    with closing(sqlite3.connect(legacy)) as db, db:
        db.execute("CREATE TABLE api_key_expiry (identity TEXT PRIMARY KEY, expires_at TEXT, checked_at TEXT NOT NULL)")
        db.execute("INSERT INTO api_key_expiry VALUES ('fictional-hash', NULL, '2026-01-01T00:00:00+00:00')")
    real_connect = sqlite3.connect
    busy = True

    def connect(database, *args, **kwargs):
        if busy and kwargs.get("uri"):
            raise sqlite3.OperationalError("database is locked")
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(app_db.sqlite3, "connect", connect)
    path = app_db.database_path(tmp_path)

    with pytest.raises(sqlite3.OperationalError, match="locked"):
        app_db.connect(path)
    with closing(real_connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone() == (0,)
    busy = False
    with closing(app_db.connect(path)) as db:
        assert db.execute("SELECT identity FROM api_key_expiry").fetchall() == [("fictional-hash",)]


def test_failed_migration_is_rolled_back(tmp_path, monkeypatch):
    path = app_db.database_path(tmp_path)

    def broken(db, _data_dir):
        db.execute("CREATE TABLE half_done (value TEXT)")
        raise sqlite3.OperationalError("fictional failure")

    monkeypatch.setattr(app_db, "MIGRATIONS", (broken,))
    monkeypatch.setattr(app_db, "SCHEMA_VERSION", 1)
    with pytest.raises(sqlite3.OperationalError):
        app_db.connect(path)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone() == (0,)
        assert db.execute("SELECT name FROM sqlite_master WHERE name = 'half_done'").fetchone() is None


def test_legacy_api_key_expiry_rows_are_imported(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    legacy = data_dir / app_db.LEGACY_API_KEY_EXPIRY_FILENAME
    with closing(sqlite3.connect(legacy)) as db, db:
        db.execute("CREATE TABLE api_key_expiry (identity TEXT PRIMARY KEY, expires_at TEXT, checked_at TEXT NOT NULL)")
        db.execute("INSERT INTO api_key_expiry VALUES ('fictional-hash', NULL, '2026-01-01T00:00:00+00:00')")

    assert app_db.database_available(app_db.database_path(tmp_path)) is True
    with closing(app_db.connect(app_db.database_path(tmp_path))) as db:
        assert db.execute("SELECT identity, expires_at FROM api_key_expiry").fetchall() == [("fictional-hash", None)]
    assert legacy.is_file()


def test_unreadable_legacy_file_does_not_block_a_new_database(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / app_db.LEGACY_STATS_FILENAME).write_bytes(b"fictional invalid database")

    with closing(app_db.connect(app_db.database_path(tmp_path))) as db:
        assert db.execute("SELECT COUNT(*) FROM stats_daily").fetchone() == (0,)


def test_database_available_ignores_unrelated_files(tmp_path):
    path = app_db.database_path(tmp_path)
    path.parent.mkdir(parents=True)
    (path.parent / "config.py").write_text("", encoding="utf-8")

    assert app_db.database_available(path) is False
