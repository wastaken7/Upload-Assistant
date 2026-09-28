import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from src import stats
from src.metadata_cache import cache_for, is_cache_miss
from src.meta import Meta


@pytest.fixture(autouse=True)
def reset_stats_configuration(monkeypatch):
    stats.configure_stats({"DEFAULT": {"stats_enabled": True}})
    stats.set_stats_context(debug=False, category="")
    monkeypatch.delenv("UA_STATS_SOURCE", raising=False)


def test_stats_aggregate_real_activity(tmp_path):
    stats.record_event("item", operation="completed", outcome="success", category="MOVIE", bytes_count=4_000, state_dir=tmp_path)
    stats.record_event(
        "upload",
        service="FICTIONAL",
        operation="torrent_tracker",
        outcome="success",
        category="MOVIE",
        duration_ms=1250,
        bytes_count=4_000,
        state_dir=tmp_path,
    )
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
        "uploaded_bytes": 4_000,
        "unique_uploaded_bytes": 4_000,
        "processed_bytes": 4_000,
        "average_item_bytes": 4_000,
        "duplicate_preventions": 1,
        "pioneering_rate": 50.0,
        "hashing_bytes_avoided": 0,
    }
    destination = result["uploads"]["by_destination"][0]
    assert destination["destination"] == "FICTIONAL"
    assert destination["skip_reasons"] == {"dupe": 1}
    assert destination["average_duration_ms"] == 1250
    assert destination["bytes"] == 4_000
    assert result["api"]["requests"] == 1


def test_unique_uploaded_bytes_counts_each_successful_item_once(tmp_path):
    item_size = 1_000_000_000
    stats.record_event("item", operation="completed", outcome="success", bytes_count=item_size, state_dir=tmp_path)
    for destination in range(10):
        stats.record_event(
            "upload",
            service=f"FICTIONAL{destination}",
            operation="torrent_tracker",
            outcome="success",
            bytes_count=item_size,
            state_dir=tmp_path,
        )

    result = stats.get_stats("all", "real", tmp_path)

    assert result["overview"]["uploaded_bytes"] == item_size * 10
    assert result["overview"]["unique_uploaded_bytes"] == item_size


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


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ({"upload_success": True}, "success"),
        ({"dupe": True, "upload_success": False}, "skipped:dupe"),
        ({"upload": True, "upload_success": False}, "error"),
        ({"status_message": "Skipped by a fictional rule"}, "skipped:no_upload"),
    ],
)
def test_tracker_route_outcome_has_stable_precedence(status, expected):
    assert stats.tracker_route_outcome(status) == expected


@pytest.mark.asyncio
async def test_completed_item_records_one_route_per_tracker_and_supports_filtering(monkeypatch, tmp_path):
    monkeypatch.setattr(stats, "_database_path", lambda _state_dir=None: tmp_path / "data" / "stats.sqlite3")

    class TorrentTracker:
        is_usenet = False

    meta = Meta(
        category="MOVIE",
        resolution="2160p",
        video_codec="HEVC",
        hdr="HDR10+",
        source_size=50_000,
        tracker_status={
            "FICTIONAL": {"upload_success": True},
            "IMAGINARY": {"dupe": True, "status_message": "Duplicate found"},
        },
    )
    await stats.record_completed_item_stats_async(meta, {"FICTIONAL": TorrentTracker, "IMAGINARY": TorrentTracker})
    stats.record_event("cache", service="imaginarydb", outcome="hit", state_dir=tmp_path)

    global_result = stats.get_stats("all", "real", tmp_path)
    filtered = stats.get_stats("all", "real", tmp_path, tracker="FICTIONAL")

    assert global_result["overview"]["items_completed"] == 1
    assert global_result["overview"]["uploads"] == 1
    assert global_result["overview"]["duplicate_preventions"] == 1
    assert global_result["overview"]["pioneering_rate"] == 50.0
    assert global_result["sankey"]["nodes"][0]["total"] == 2
    assert filtered["overview"]["items_completed"] == 1
    assert filtered["overview"]["processed_bytes"] == 50_000
    assert filtered["overview"]["uploaded_bytes"] == 50_000
    assert filtered["cache"]["hits"] == 1
    assert filtered["media"]["matrix"][0]["resolution"] == "2160p"
    assert filtered["uploads"]["by_destination"][0]["pioneering_rate"] == 100.0


@pytest.mark.asyncio
async def test_duplicate_only_item_is_not_classified_as_an_error(monkeypatch, tmp_path):
    monkeypatch.setattr(stats, "_database_path", lambda _state_dir=None: tmp_path / "data" / "stats.sqlite3")
    meta = Meta(
        category="TV",
        source_size=10_000,
        tracker_status={"FICTIONAL": {"dupe": True, "upload_success": False}},
    )

    await stats.record_completed_item_stats_async(meta, {"FICTIONAL": object})
    result = stats.get_stats("all", "real", tmp_path)

    assert result["items"] == {"success": 0, "no_upload": 1, "error": 0}
    assert result["overview"]["duplicate_preventions"] == 1


def test_schema_v2_recreates_unreleased_v1_aggregates(tmp_path):
    database = tmp_path / "data" / "stats.sqlite3"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE stats_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("INSERT INTO stats_meta VALUES ('schema_version', '1')")
        db.execute("CREATE TABLE stats_daily (legacy TEXT)")

    stats.record_event("item", operation="completed", state_dir=tmp_path)

    with sqlite3.connect(database) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(stats_daily)")}
        assert "destination" in columns
        assert db.execute("SELECT value FROM stats_meta WHERE key = 'schema_version'").fetchone() == ("2",)


def test_calendar_ranges_use_inclusive_utc_boundaries():
    today = stats.get_empty_stats("today", "real")
    this_month = stats.get_empty_stats("this_month", "real")
    last_month = stats.get_empty_stats("last_month", "real")

    assert today["period"]["from"] == today["period"]["to"]
    assert this_month["period"]["from"].endswith("-01")
    assert last_month["period"]["from"].endswith("-01")
    assert last_month["period"]["to"] < this_month["period"]["from"]
    assert today["period"]["timezone"] == "UTC"


def test_api_requests_fall_back_to_completed_operation_outcomes(tmp_path):
    stats.record_event("api", service="fictional-client", operation="search", outcome="success", duration_ms=20, bytes_count=2048, state_dir=tmp_path)
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
        "bytes": 2048,
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


@pytest.mark.asyncio
async def test_media_profile_records_category_appropriate_dimensions(monkeypatch, tmp_path):
    monkeypatch.setattr(stats, "_database_path", lambda _state_dir=None: tmp_path / "data" / "stats.sqlite3")
    meta = Meta(
        category="MOVIE",
        resolution="2160p",
        type="WEBDL",
        video_codec="HEVC",
        audio="TrueHD Atmos 7.1",
        hdr="DV HDR",
        service="NF",
        service_longname="Netflix",
        source_size=85_000,
    )

    await stats.record_media_profile_async(meta)
    result = stats.get_stats("all", "real", tmp_path)

    assert result["media"]["categories"] == ["MOVIE"]
    assert {(row["dimension"], row["value"]) for row in result["media"]["dimensions"]} == {
        ("resolution", "2160p"),
        ("release_type", "WEBDL"),
        ("video_codec", "HEVC"),
        ("audio_codec", "Dolby_Atmos"),
        ("hdr", "Dolby_Vision_-_profile_unknown_HDR10"),
        ("streaming_service", "Netflix"),
    }
    assert all(row["bytes"] == 85_000 for row in result["media"]["dimensions"])
    assert result["media"]["matrix"] == [
        {
            "category": "MOVIE",
            "resolution": "2160p",
            "profile": "HEVC · Dolby_Vision_-_profile_unknown_HDR10",
            "count": 1,
            "bytes": 85_000,
        }
    ]
    assert result["streaming"]["services"] == [{"service": "Netflix", "items": 1, "bytes": 85_000, "average_item_bytes": 85_000}]


def test_web_media_without_a_service_is_grouped_as_unknown():
    dimensions = stats.media_profile_dimensions(Meta(category="TV", type="WEBRIP"))

    assert ("streaming_service", "Unknown") in dimensions
    assert ("streaming_service", "Unknown") not in stats.media_profile_dimensions(Meta(category="MOVIE", type="REMUX"))


@pytest.mark.parametrize(
    ("hdr", "profile", "compatibility", "expected"),
    [
        ("DV", "dvhe.05.06", "", "Dolby Vision Profile 5"),
        ("DV HDR", "dvhe.07.06", "HDR10", "Dolby Vision Profile 7 + HDR10"),
        ("DV", "dvhe.08.06", "HDR10", "Dolby Vision Profile 8 + HDR10"),
        ("DV", "", "", "Dolby Vision - profile unknown"),
        ("HDR10+", "", "HDR10+ Profile B", "HDR10+"),
        ("HDR", "", "HDR10", "HDR10"),
        ("HLG", "", "HLG", "HLG"),
        ("", "", "", "SDR"),
    ],
)
def test_hdr_bucket_preserves_dolby_vision_depth(hdr, profile, compatibility, expected):
    meta = Meta(
        hdr=hdr,
        mediainfo={
            "media": {
                "track": [
                    {"@type": "General"},
                    {
                        "@type": "Video",
                        "HDR_Format_Profile": profile,
                        "HDR_Format_Compatibility": compatibility,
                    },
                ]
            }
        },
    )

    assert stats._hdr_bucket(meta) == expected


@pytest.mark.asyncio
async def test_release_profiles_aggregate_personal_results_without_group_names(monkeypatch, tmp_path):
    monkeypatch.setattr(stats, "_database_path", lambda _state_dir=None: tmp_path / "data" / "stats.sqlite3")
    personal = Meta(category="MOVIE", personalrelease=True, tag="-FICTIONALGROUP", source_size=75_000)
    standard = Meta(category="TV", personalrelease=False, source_size=25_000)

    await stats.record_release_profile_async(personal, "success")
    await stats.record_release_profile_async(standard, "error")
    result = stats.get_stats("all", "real", tmp_path)

    assert result["release_profiles"]["profiles"] == [
        {
            "profile": "personal",
            "items": 1,
            "successes": 1,
            "without_upload": 0,
            "errors": 0,
            "bytes": 75_000,
            "success_rate": 100.0,
        },
        {
            "profile": "standard",
            "items": 1,
            "successes": 0,
            "without_upload": 0,
            "errors": 1,
            "bytes": 25_000,
            "success_rate": 0.0,
        },
    ]
    assert result["release_profiles"]["by_category"][0]["category"] == "MOVIE"
    assert b"FICTIONALGROUP" not in (tmp_path / "data" / "stats.sqlite3").read_bytes()


def test_reused_torrent_reports_media_volume_as_hashing_io_avoided(tmp_path):
    stats.record_event(
        "artifact",
        service="torrent",
        operation="reused",
        outcome="success",
        category="base",
        bytes_count=64_000,
        state_dir=tmp_path,
    )

    result = stats.get_stats("all", "real", tmp_path)

    assert result["overview"]["hashing_bytes_avoided"] == 64_000
    assert result["artifacts"] == [{"type": "torrent", "operation": "reused", "variant": "base", "count": 1, "bytes": 64_000}]


def test_stats_reports_heatmap_and_previous_period_comparison(tmp_path):
    stats.record_event("item", operation="completed", outcome="success", state_dir=tmp_path)
    stats.record_event("upload", service="FICTIONAL", operation="tracker", outcome="success", state_dir=tmp_path)
    stats.record_event("cache", service="fictional", operation="title", outcome="hit", state_dir=tmp_path)
    database = tmp_path / "data" / "stats.sqlite3"
    prior_day = (datetime.now(UTC).date() - timedelta(days=7)).isoformat()
    with sqlite3.connect(database) as db:
        db.execute("UPDATE stats_daily SET day = ?", (prior_day,))
    for _ in range(2):
        stats.record_event("item", operation="completed", outcome="success", state_dir=tmp_path)
        stats.record_event("upload", service="FICTIONAL", operation="tracker", outcome="success", state_dir=tmp_path)
    stats.record_event("cache", service="fictional", operation="title", outcome="miss", state_dir=tmp_path)

    result = stats.get_stats("7d", "real", tmp_path)

    assert result["comparison"] == {
        "items_completed_pct": 100.0,
        "uploads_pct": 100.0,
        "cache_hit_rate_delta": -100.0,
    }
    assert result["heatmap"][-1]["count"] == 2


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
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        stats.get_stats("custom", "real", tmp_path, date_from="bad", date_to="2026-01-01")
    with pytest.raises(ValueError, match="on or before"):
        stats.get_stats("custom", "real", tmp_path, date_from="2026-01-02", date_to="2026-01-01")


def test_one_year_range_contains_365_inclusive_days():
    result = stats.get_empty_stats("1y", "real")

    first_day = datetime.fromisoformat(result["period"]["from"]).date()
    last_day = datetime.fromisoformat(result["period"]["to"]).date()
    assert (last_day - first_day).days == 364
    assert result["streaming"] == {"services": []}
    assert result["release_profiles"] == {"profiles": [], "by_category": []}


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
