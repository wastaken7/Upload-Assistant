import os
import asyncio
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from src import stats
from src.metadata_cache import cache_for, is_cache_miss


@pytest.fixture(autouse=True)
def reset_stats_configuration(monkeypatch):
    stats.configure_stats({"DEFAULT": {"stats_enabled": True}})
    stats.set_stats_context(debug=False, category="")
    monkeypatch.delenv("UA_STATS_SOURCE", raising=False)


def test_stats_aggregate_real_activity(tmp_path):
    stats.record_event("item", operation="completed", outcome="success", category="MOVIE", state_dir=tmp_path)
    stats.record_event("upload", service="FICTIONAL", operation="torrent_tracker", outcome="success", category="MOVIE", duration_ms=1250, state_dir=tmp_path)
    stats.record_event("upload", service="FICTIONAL", operation="torrent_tracker", outcome="skipped:dupe", category="MOVIE", state_dir=tmp_path)
    stats.record_event("artifact", service="torrent", operation="created", category="base", state_dir=tmp_path)
    stats.record_event("cache", service="imaginarydb", operation="title", outcome="hit", state_dir=tmp_path)
    stats.record_event("cache", service="imaginarydb", operation="title", outcome="miss", state_dir=tmp_path)
    stats.record_event("api", service="imaginarydb", operation="title", outcome="request", state_dir=tmp_path)

    result = stats.get_stats("30d", "real", tmp_path)

    assert result["overview"] == {
        "items_completed": 1,
        "uploads": 1,
        "upload_attempts": 1,
        "upload_success_rate": 100.0,
        "torrents_created": 1,
        "nzbs_created": 0,
        "api_operations": 1,
        "cache_hit_rate": 50.0,
    }
    destination = result["uploads"]["by_destination"][0]
    assert destination["destination"] == "FICTIONAL"
    assert destination["skip_reasons"] == {"dupe": 1}
    assert destination["average_duration_ms"] == 1250
    assert result["api"]["requests"] == 1


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ([{"upload_success": True}, {"upload_success": False}], "success"),
        ([{"upload_success": False}], "error"),
        ([{"upload": False, "skipped": True}], "no_upload"),
    ],
)
def test_completed_item_outcome_uses_definitive_upload_results(statuses, expected):
    assert stats.completed_item_outcome(statuses) == expected


def test_api_requests_fall_back_to_completed_operation_outcomes(tmp_path):
    stats.record_event("api", service="fictional-client", operation="search", outcome="success", duration_ms=20, state_dir=tmp_path)
    stats.record_event("api", service="fictional-client", operation="search", outcome="error", duration_ms=10, state_dir=tmp_path)
    stats.record_event("api", service="less-active-client", operation="add", outcome="success", state_dir=tmp_path)

    result = stats.get_stats("all", "real", tmp_path)

    assert result["overview"]["api_operations"] == 3
    assert result["api"]["requests"] == 3
    assert result["api"]["by_service"][0] == {
        "service": "fictional-client",
        "operation": "search",
        "requests": 2,
        "successes": 1,
        "errors": 1,
        "average_duration_ms": 15,
        "bytes": 0,
    }


def test_stats_separate_debug_and_webui(monkeypatch, tmp_path):
    monkeypatch.setenv("UA_STATS_SOURCE", "webui")
    stats.set_stats_context(debug=True, category="BOOK")
    stats.record_event("item", operation="completed", outcome="success", state_dir=tmp_path)
    stats.record_event("artifact", service="nzb", operation="created", state_dir=tmp_path)

    assert stats.get_stats("all", "real", tmp_path)["overview"]["items_completed"] == 0
    debug = stats.get_stats("all", "debug", tmp_path)
    assert debug["overview"]["items_completed"] == 1
    assert debug["overview"]["nzbs_created"] == 1
    assert debug["sources"] == [{"source": "webui", "count": 1}]


def test_stats_can_be_disabled_without_hiding_existing_data(tmp_path):
    stats.record_event("item", operation="completed", state_dir=tmp_path)
    stats.configure_stats({"DEFAULT": {"stats_enabled": False}})
    stats.record_event("item", operation="completed", state_dir=tmp_path)

    assert stats.get_stats("all", "real", tmp_path)["overview"]["items_completed"] == 1


def test_stats_collection_is_disabled_when_setting_is_missing(tmp_path):
    stats.configure_stats({"DEFAULT": {}})
    stats.record_event("item", operation="completed", state_dir=tmp_path)

    assert stats.get_stats("all", "real", tmp_path)["overview"]["items_completed"] == 0


def test_stats_collection_requires_explicit_boolean_opt_in():
    assert stats.stats_collection_enabled({"DEFAULT": {"stats_enabled": True}}) is True
    assert stats.stats_collection_enabled({"DEFAULT": {"stats_enabled": False}}) is False
    assert stats.stats_collection_enabled({"DEFAULT": {}}) is False
    assert stats.stats_collection_enabled({"DEFAULT": {"stats_enabled": "true"}}) is False


def test_stats_reset_only_removes_aggregates(tmp_path):
    stats.record_event("item", operation="completed", state_dir=tmp_path)
    reset_at = stats.reset_stats(tmp_path)

    assert reset_at.endswith("+00:00")
    assert stats.get_stats("all", "real", tmp_path)["overview"]["items_completed"] == 0
    with sqlite3.connect(tmp_path / "data" / "stats.sqlite3") as db:
        assert db.execute("SELECT value FROM stats_meta WHERE key = 'reset_at'").fetchone() == (reset_at,)


def test_stats_reset_establishes_a_boundary_before_the_first_event(tmp_path):
    reset_at = stats.reset_stats(tmp_path)

    with sqlite3.connect(tmp_path / "data" / "stats.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM stats_daily").fetchone() == (0,)
        assert db.execute("SELECT value FROM stats_meta WHERE key = 'reset_at'").fetchone() == (reset_at,)


def test_stats_upserts_are_thread_safe(tmp_path):
    def record_many(_worker):
        for _ in range(10):
            stats.record_event("api", service="fictional", operation="lookup", outcome="success", state_dir=tmp_path)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(record_many, range(4)))

    assert stats.get_stats("all", "real", tmp_path)["overview"]["api_operations"] == 40


def test_stats_upserts_are_process_safe(tmp_path):
    script = (
        "import sys; from src.stats import configure_stats, record_event; "
        "configure_stats({'DEFAULT': {'stats_enabled': True}}); "
        "[record_event('api', service='fictional', operation='lookup', outcome='success', state_dir=sys.argv[1]) for _ in range(10)]"
    )
    environment = os.environ | {"PYTHONPATH": os.getcwd()}
    processes = [subprocess.Popen([sys.executable, "-c", script, str(tmp_path)], env=environment) for _ in range(4)]

    assert [process.wait(timeout=20) for process in processes] == [0, 0, 0, 0]
    assert stats.get_stats("all", "real", tmp_path)["overview"]["api_operations"] == 40


def test_stats_retries_transient_sqlite_lock(monkeypatch, tmp_path):
    real_connect = stats._connect
    attempts = 0

    def intermittently_locked(path):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise sqlite3.OperationalError("database is locked")
        return real_connect(path)

    monkeypatch.setattr(stats, "_connect", intermittently_locked)

    stats.record_event("api", service="fictional", operation="lookup", state_dir=tmp_path)

    assert attempts == 2
    assert stats.get_stats("all", "real", tmp_path)["overview"]["api_operations"] == 1


@pytest.mark.asyncio
async def test_record_event_async_offloads_the_sqlite_write(monkeypatch):
    calls = []

    async def fake_to_thread(function, *args, **kwargs):
        calls.append((function, args, kwargs))

    monkeypatch.setattr(stats.asyncio, "to_thread", fake_to_thread)

    await stats.record_event_async("api", service="fictional", operation="lookup")

    assert calls == [
        (
            stats.record_event,
            ("api",),
            {"service": "fictional", "operation": "lookup"},
        )
    ]


def test_corrupt_database_never_breaks_recording_or_reading(tmp_path):
    database = tmp_path / "data" / "stats.sqlite3"
    database.parent.mkdir(parents=True)
    database.write_bytes(b"not a sqlite database")

    stats.record_event("item", operation="completed", state_dir=tmp_path)
    result = stats.get_stats("all", "real", tmp_path)

    assert result["success"] is True
    assert result["overview"]["items_completed"] == 0


def test_invalid_filters_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="range"):
        stats.get_stats("yesterday", "real", tmp_path)
    with pytest.raises(ValueError, match="mode"):
        stats.get_stats("7d", "combined", tmp_path)


@pytest.mark.asyncio
async def test_metadata_cache_does_not_infer_api_calls_from_cache_activity(monkeypatch, tmp_path):
    monkeypatch.setattr(stats, "_database_path", lambda _state_dir=None: tmp_path / "data" / "stats.sqlite3")
    cache = cache_for(tmp_path, {"DEFAULT": {"metadata_cache_dir": "cache"}})

    assert is_cache_miss(await cache.get("imaginarydb", "title", "fictional-key"))
    await cache.set("imaginarydb", "title", "fictional-key", {"title": "Fictional Work"})
    assert await cache.get("imaginarydb", "title", "fictional-key") == {"title": "Fictional Work"}

    result = stats.get_stats("all", "real", tmp_path)
    assert result["cache"]["misses"] == 1
    assert result["cache"]["writes"] == 1
    assert result["cache"]["hits"] == 1
    assert result["api"]["total"] == 0
    assert b"Fictional Work" not in (tmp_path / "data" / "stats.sqlite3").read_bytes()
