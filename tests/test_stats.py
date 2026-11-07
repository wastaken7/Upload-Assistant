import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from torf import Torrent

from src import app_db, stats, webui_events
from src.meta import Meta
from src.metadata_cache import cache_for, is_cache_miss
from src.torrent_manifest import TorrentManifest


@pytest.fixture(autouse=True)
def reset_stats_configuration(monkeypatch):
    stats.configure_stats({"DEFAULT": {"stats_enabled": True}})
    stats.set_stats_context(debug=False, category="")
    monkeypatch.delenv("UA_STATS_SOURCE", raising=False)
    yield
    # Leave collection off so later test modules never record by accident.
    stats.configure_stats(None)


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
    stats.record_event("artifact", service="screenshot", operation="created", category="standard", count=5, state_dir=tmp_path)
    stats.record_event("artifact", service="screenshot", operation="created", category="menu", count=2, state_dir=tmp_path)
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
        "screenshots_created": 7,
        "api_operations": 1,
        "cache_hit_rate": 50.0,
        "uploaded_bytes": 4_000,
        "unique_uploaded_bytes": 4_000,
        "processed_bytes": 4_000,
        "average_item_bytes": 4_000,
        "duplicate_preventions": 1,
        "pioneering_rate": 50.0,
        "hashing_bytes_avoided": 0,
        "hashed_bytes": 0,
        "hashing_bytes_per_second": 0,
        "hashing_seconds_saved": 0,
        "average_item_seconds": 0.0,
    }
    destination = result["uploads"]["by_destination"][0]
    assert destination["destination"] == "FICTIONAL"
    assert destination["skip_reasons"] == {"dupe": 1}
    assert destination["average_duration_ms"] == 1250
    assert destination["bytes"] == 4_000
    assert result["api"]["requests"] == 1
    assert {(row["type"], row["operation"], row["variant"], row["count"]) for row in result["artifacts"] if row["type"] == "screenshot"} == {
        ("screenshot", "created", "menu", 2),
        ("screenshot", "created", "standard", 5),
    }


def test_screenshot_manifest_only_publishes_existing_screenshots(tmp_path):
    from src import screenshot_manifest

    source = tmp_path / "Celestial.Harbor-frame.png"
    source.write_bytes(b"fictional screenshot")

    published = screenshot_manifest.register(tmp_path, "fictional-release", [source, tmp_path / "missing.png"], "main")

    assert len(published) == 1


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
        ({"status_message": "Skipped by a fictional rule"}, "skipped:rules"),
        ({"banned": True, "upload": False}, "skipped:banned"),
        ({"skipped": True, "status_message": "Claimed release found on this tracker"}, "skipped:claimed"),
        ({"upload": False, "status_message": "Skipped: no policy-compliant torrent is available and hashing is disabled"}, "skipped:torrent_policy"),
        ({"skipped": True, "skip_reason": "missing_fields"}, "skipped:missing_fields"),
        ({"banned": False, "skipped": False, "dupe": False, "upload": False}, "skipped:declined"),
        ({"status_message": "Skipped: Error redoing dupe check after bandwidth wait: boom"}, "skipped:search_error"),
        ({}, "skipped:no_upload"),
    ],
)
def test_tracker_route_outcome_has_stable_precedence(status, expected):
    assert stats.tracker_route_outcome(status) == expected


def test_approved_routes_are_skipped_when_the_upload_stage_never_started():
    assert stats.tracker_route_outcome({"upload": True}, upload_started=False) == "skipped:too_few_trackers"
    assert stats.tracker_route_outcome({"upload": True}, upload_started=True) == "error"
    # A site check never reaches the upload stage, so its routes are not "too few trackers".
    assert stats.tracker_route_outcome({"upload": True}, upload_started=False, site_check=True) == "skipped:site_check"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ({"status_message": "Error: 401 Unauthorized"}, "auth"),
        ({"status_message": {"message": "Invalid API key provided"}}, "auth"),
        ({"status_message": "HTTP 429 Too Many Requests"}, "rate_limit"),
        ({"status_message": "Request timed out"}, "timeout"),
        ({"status_message": "502 Bad Gateway"}, "server"),
        ({"status_message": "data error: unexpected response"}, "invalid_response"),
        ({"status_message": "Upload rejected: resolution not allowed"}, "rejected"),
        ({"status_message": "Release is 1500 MB"}, "other"),
        ({}, "unknown"),
        ({"error_reason": "timeout", "status_message": "401"}, "timeout"),
    ],
)
def test_upload_error_reason_is_a_short_category(status, expected):
    assert stats.upload_error_reason(status) == expected


def test_exception_error_reason_uses_type_and_status_code():
    class FictionalResponse:
        status_code = 503

    class FictionalHTTPError(Exception):
        response = FictionalResponse()

    assert stats.exception_error_reason(TimeoutError()) == "timeout"
    assert stats.exception_error_reason(ConnectionResetError()) == "network"
    assert stats.exception_error_reason(FictionalHTTPError("boom")) == "server"
    assert stats.exception_error_reason(ValueError("plain failure")) == "exception"


@pytest.mark.asyncio
async def test_completed_item_records_one_route_per_tracker_and_supports_filtering(monkeypatch, tmp_path):
    monkeypatch.setattr(stats, "_database_path", lambda _state_dir=None: tmp_path / "data" / "upload_assistant.sqlite3")

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
async def test_completed_item_keeps_upload_durations_from_flow_copies(monkeypatch, tmp_path):
    monkeypatch.setattr(stats, "_database_path", lambda _state_dir=None: tmp_path / "data" / "upload_assistant.sqlite3")

    class TorrentTracker:
        is_usenet = False

    class UsenetIndexer:
        is_usenet = True

    meta = Meta(
        category="MOVIE",
        tracker_status={"FICTIONAL": {"upload_success": True}, "IMAGINARY": {"upload_success": True}},
    )
    torrent_flow = meta.copy()
    torrent_flow["FICTIONAL_upload_duration"] = 1.25
    stats.accumulate_upload_durations(meta, torrent_flow, ["FICTIONAL"])

    for duration in (0.5, 0.75):
        usenet_submission = meta.copy()
        usenet_submission["IMAGINARY_upload_duration"] = duration
        stats.accumulate_upload_durations(meta, usenet_submission, ["IMAGINARY"])

    await stats.record_completed_item_stats_async(meta, {"FICTIONAL": TorrentTracker, "IMAGINARY": UsenetIndexer})
    destinations = {row["destination"]: row for row in stats.get_stats("all", "real", tmp_path)["uploads"]["by_destination"]}

    assert destinations["FICTIONAL"]["average_duration_ms"] == 1250
    assert destinations["IMAGINARY"]["average_duration_ms"] == 1250


@pytest.mark.asyncio
async def test_duplicate_only_item_is_not_classified_as_an_error(monkeypatch, tmp_path):
    monkeypatch.setattr(stats, "_database_path", lambda _state_dir=None: tmp_path / "data" / "upload_assistant.sqlite3")
    meta = Meta(
        category="TV",
        source_size=10_000,
        tracker_status={"FICTIONAL": {"dupe": True, "upload_success": False}},
    )

    await stats.record_completed_item_stats_async(meta, {"FICTIONAL": object})
    result = stats.get_stats("all", "real", tmp_path)

    assert result["items"] == {"success": 0, "no_upload": 1, "error": 0}
    assert result["overview"]["duplicate_preventions"] == 1


def test_legacy_v1_statistics_file_is_not_imported(tmp_path):
    legacy = tmp_path / "data" / "stats.sqlite3"
    legacy.parent.mkdir(parents=True)
    with closing(sqlite3.connect(legacy)) as db, db:
        db.execute("CREATE TABLE stats_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("INSERT INTO stats_meta VALUES ('schema_version', '1')")
        db.execute("CREATE TABLE stats_daily (legacy TEXT)")

    stats.record_event("item", operation="completed", state_dir=tmp_path)

    assert stats.get_stats("all", "real", tmp_path)["overview"]["items_completed"] == 1


def test_newer_schema_is_preserved_instead_of_reset(tmp_path):
    stats.record_event("item", operation="completed", count=3, state_dir=tmp_path)
    database = tmp_path / "data/upload_assistant.sqlite3"
    with closing(sqlite3.connect(database)) as db:
        db.execute("PRAGMA user_version = 999")

    assert stats.get_stats("all", "real", tmp_path)["success"] is False
    stats.record_event("item", operation="completed", state_dir=tmp_path)
    with pytest.raises(sqlite3.DatabaseError):
        stats.reset_stats(tmp_path)

    with closing(sqlite3.connect(database)) as db:
        assert db.execute("SELECT SUM(count) FROM stats_daily").fetchone() == (3,)
        assert db.execute("PRAGMA user_version").fetchone() == (999,)


def test_legacy_content_time_is_preserved(tmp_path):
    legacy = tmp_path / "data" / app_db.LEGACY_STATS_FILENAME
    legacy.parent.mkdir(parents=True)
    with closing(sqlite3.connect(legacy)) as db, db:
        db.execute("CREATE TABLE stats_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("INSERT INTO stats_meta VALUES ('schema_version', '2')")
        db.execute(
            """
            CREATE TABLE stats_daily (
                day TEXT NOT NULL, family TEXT NOT NULL, service TEXT NOT NULL,
                operation TEXT NOT NULL, outcome TEXT NOT NULL, category TEXT NOT NULL,
                source TEXT NOT NULL, mode TEXT NOT NULL, destination TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0, duration_ms INTEGER NOT NULL DEFAULT 0,
                content_seconds INTEGER NOT NULL DEFAULT 0, bytes INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (day, family, service, operation, outcome, category, source, mode, destination)
            )
            """
        )
        db.execute(
            "INSERT INTO stats_daily VALUES (?, 'content', '', 'uploaded', 'success', 'movie', 'cli', 'real', '', 1, 0, 5400, 0)",
            (datetime.now(UTC).date().isoformat(),),
        )

    stats.get_stats("all", "real", tmp_path)

    with closing(sqlite3.connect(app_db.database_path(tmp_path))) as db:
        assert db.execute("SELECT content_seconds FROM stats_daily WHERE family = 'content'").fetchone() == (5400,)


def test_legacy_statistics_file_is_imported_once_and_left_unchanged(tmp_path):
    legacy = tmp_path / "data" / "stats.sqlite3"
    legacy.parent.mkdir(parents=True)
    with closing(sqlite3.connect(legacy)) as db, db:
        db.execute("CREATE TABLE stats_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("INSERT INTO stats_meta VALUES ('schema_version', '2')")
        db.execute("INSERT INTO stats_meta VALUES ('reset_at', '2026-01-01T00:00:00+00:00')")
        db.execute(
            """
            CREATE TABLE stats_daily (
                day TEXT NOT NULL, family TEXT NOT NULL, service TEXT NOT NULL,
                operation TEXT NOT NULL, outcome TEXT NOT NULL, category TEXT NOT NULL,
                source TEXT NOT NULL, mode TEXT NOT NULL, destination TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0, duration_ms INTEGER NOT NULL DEFAULT 0,
                bytes INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (day, family, service, operation, outcome, category, source, mode, destination)
            )
            """
        )
        db.execute(
            "INSERT INTO stats_daily VALUES (?, 'item', '', 'completed', 'success', 'MOVIE', 'cli', 'real', '', 3, 0, 12000)",
            (datetime.now(UTC).date().isoformat(),),
        )
    legacy_bytes = legacy.read_bytes()

    result = stats.get_stats("all", "real", tmp_path)
    stats.record_event("item", operation="completed", state_dir=tmp_path)

    assert result["overview"]["items_completed"] == 3
    assert stats.get_stats("all", "real", tmp_path)["overview"]["items_completed"] == 4
    assert legacy.read_bytes() == legacy_bytes
    with closing(sqlite3.connect(tmp_path / "data" / "upload_assistant.sqlite3")) as db:
        assert db.execute("SELECT count, bytes, content_seconds FROM stats_daily WHERE count = 3").fetchone() == (3, 12_000, 0)
        assert db.execute("SELECT value FROM stats_meta WHERE key = 'reset_at'").fetchone() == ("2026-01-01T00:00:00+00:00",)


@pytest.mark.asyncio
async def test_successful_content_time_counts_once_globally_and_per_destination(monkeypatch, tmp_path):
    monkeypatch.setattr(stats, "_database_path", lambda _state_dir=None: tmp_path / "data" / "upload_assistant.sqlite3")

    class TorrentTracker:
        is_usenet = False

    meta = Meta(
        category="MOVIE",
        content_duration_category="Movie",
        content_duration_seconds=7_200.4,
        tracker_status={
            "FICTIONAL": {"upload_success": True},
            "IMAGINARY": {"upload_success": True},
            "EXAMPLE": {"dupe": True, "upload_success": False},
        },
    )

    await stats.record_completed_item_stats_async(
        meta,
        {"FICTIONAL": TorrentTracker, "IMAGINARY": TorrentTracker, "EXAMPLE": TorrentTracker},
    )

    global_result = stats.get_stats("all", "real", tmp_path)
    fictional = stats.get_stats("all", "real", tmp_path, tracker="FICTIONAL")
    duplicate = stats.get_stats("all", "real", tmp_path, tracker="EXAMPLE")

    assert global_result["content_time"] == {
        "total_seconds": 7_200,
        "by_category": [{"category": "Movie", "items": 1, "seconds": 7_200}],
    }
    assert fictional["content_time"] == global_result["content_time"]
    assert duplicate["content_time"] == {"total_seconds": 0, "by_category": []}


@pytest.mark.asyncio
async def test_failed_prepared_pack_duration_does_not_fall_back_to_representative_mediainfo(monkeypatch, tmp_path):
    monkeypatch.setattr(stats, "_database_path", lambda _state_dir=None: tmp_path / "data" / "upload_assistant.sqlite3")
    meta = Meta(
        category="TV",
        content_duration_category="TV",
        content_duration_seconds=None,
        mediainfo={"media": {"track": [{"@type": "General", "Duration": "1200"}]}},
        tracker_status={"FICTIONAL": {"upload_success": True}},
    )

    await stats.record_completed_item_stats_async(meta, {"FICTIONAL": object})

    assert stats.get_stats("all", "real", tmp_path)["content_time"] == {"total_seconds": 0, "by_category": []}


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
    monkeypatch.setattr(stats, "_database_path", lambda _state_dir=None: tmp_path / "data" / "upload_assistant.sqlite3")
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
    assert not any(name == "streaming_service" for name, _value in stats.media_profile_dimensions(Meta(category="BOOK", audiobook=True)))  # noqa: S101


@pytest.mark.asyncio
@pytest.mark.parametrize(("service", "name"), [("audible", "Audible"), ("ubook", "Ubook")])
async def test_book_streaming_service_appears_in_stats(monkeypatch, tmp_path, service, name):
    monkeypatch.setattr(stats, "_database_path", lambda _state_dir=None: tmp_path / "data" / "upload_assistant.sqlite3")
    meta = Meta(category="BOOK", audiobook=True, service=service, service_longname=name, source_size=12_000)

    await stats.record_media_profile_async(meta)
    result = stats.get_stats("all", "real", tmp_path)

    assert ("streaming_service", name) in stats.media_profile_dimensions(meta)  # noqa: S101
    assert result["streaming"]["services"] == [{"service": name, "items": 1, "bytes": 12_000, "average_item_bytes": 12_000}]  # noqa: S101


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
    monkeypatch.setattr(stats, "_database_path", lambda _state_dir=None: tmp_path / "data" / "upload_assistant.sqlite3")
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
    assert b"FICTIONALGROUP" not in (tmp_path / "data" / "upload_assistant.sqlite3").read_bytes()


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


def _write_torrent(path, size):
    piece_size = 16_384
    torrent = Torrent()
    torrent.metainfo["info"] = {"name": "fictional.mkv", "length": size, "piece length": piece_size, "pieces": b"x" * (20 * -(-size // piece_size))}
    torrent.write(path, overwrite=True)


class _TorrentTracker:
    is_usenet = False


def _completed_meta(tmp_path):
    return Meta(
        base_dir=str(tmp_path),
        uuid="fictional-release",
        category="MOVIE",
        source_size=70_000,
        tracker_status={"FICTIONAL": {"upload_success": True}},
    )


@pytest.mark.asyncio
async def test_client_torrent_registered_by_the_prep_search_counts_as_hashing_io_avoided(monkeypatch, tmp_path):
    monkeypatch.setattr(stats, "_database_path", lambda _state_dir=None: tmp_path / "data" / "upload_assistant.sqlite3")
    source = tmp_path / "client.torrent"
    _write_torrent(source, 64_000)
    manifest = TorrentManifest(tmp_path, "fictional-release")
    # The prep-stage client search registers candidates as "client:<name>" and
    # later re-registrations of the managed copy keep that origin.
    entry = manifest.register(source, "base", "client:fictional-qbit")
    manifest.register(manifest.entry_path(entry), "base", "client")
    manifest.select("FICTIONAL", "base")
    (manifest.root / "[FICTIONAL].torrent").write_bytes(manifest.entry_path(entry).read_bytes())

    await stats.record_completed_item_stats_async(_completed_meta(tmp_path), {"FICTIONAL": _TorrentTracker})

    global_result = stats.get_stats("all", "real", tmp_path)
    filtered = stats.get_stats("all", "real", tmp_path, tracker="FICTIONAL")
    assert global_result["overview"]["hashing_bytes_avoided"] == 64_000
    assert global_result["overview"]["torrents_created"] == 0
    assert filtered["overview"]["hashing_bytes_avoided"] == 64_000
    # The tracker's copy of a reused base is not a newly hashed torrent.
    assert filtered["overview"]["torrents_created"] == 0


@pytest.mark.asyncio
async def test_tracker_view_counts_a_generated_base_as_created_not_reused(monkeypatch, tmp_path):
    monkeypatch.setattr(stats, "_database_path", lambda _state_dir=None: tmp_path / "data" / "upload_assistant.sqlite3")
    source = tmp_path / "generated.torrent"
    _write_torrent(source, 64_000)
    manifest = TorrentManifest(tmp_path, "fictional-release")
    manifest.register(source, "base", "generated")
    manifest.select("FICTIONAL", "base")

    await stats.record_completed_item_stats_async(_completed_meta(tmp_path), {"FICTIONAL": _TorrentTracker})

    filtered = stats.get_stats("all", "real", tmp_path, tracker="FICTIONAL")
    assert filtered["overview"]["torrents_created"] == 1
    assert filtered["overview"]["hashing_bytes_avoided"] == 0
    assert stats.get_stats("all", "real", tmp_path)["overview"]["hashing_bytes_avoided"] == 0


def test_tracker_view_reports_global_screenshots_without_mixing_them_into_artifacts(tmp_path):
    stats.record_event("artifact", service="screenshot", operation="created", category="standard", count=5, state_dir=tmp_path)
    stats.record_event("upload", service="FICTIONAL", operation="torrent_tracker", outcome="success", destination="FICTIONAL", state_dir=tmp_path)

    filtered = stats.get_stats("all", "real", tmp_path, tracker="FICTIONAL")

    assert filtered["overview"]["screenshots_created"] == 5
    assert filtered["artifacts"] == []


def test_stats_reports_heatmap_and_previous_period_comparison(tmp_path):
    stats.record_event("item", operation="started", outcome="success", state_dir=tmp_path)
    stats.record_event("item", operation="completed", outcome="success", state_dir=tmp_path)
    stats.record_event("upload", service="FICTIONAL", operation="tracker", outcome="success", state_dir=tmp_path)
    stats.record_event("cache", service="fictional", operation="title", outcome="hit", state_dir=tmp_path)
    database = tmp_path / "data" / "upload_assistant.sqlite3"
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
    with sqlite3.connect(tmp_path / "data" / "upload_assistant.sqlite3") as db:
        assert db.execute("SELECT value FROM stats_meta WHERE key = 'reset_at'").fetchone() == (reset_at,)


def test_stats_reset_establishes_a_boundary_before_the_first_event(tmp_path):
    reset_at = stats.reset_stats(tmp_path)

    with sqlite3.connect(tmp_path / "data" / "upload_assistant.sqlite3") as db:
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


def test_corrupt_database_does_not_break_recording_and_reports_read_failure(tmp_path):
    database = tmp_path / "data" / "upload_assistant.sqlite3"
    database.parent.mkdir(parents=True)
    database.write_bytes(b"not a sqlite database")

    stats.record_event("item", operation="completed", state_dir=tmp_path)
    result = stats.get_stats("all", "real", tmp_path)

    assert result["success"] is False
    assert "Unable to read statistics" in result["error"]
    assert result["overview"]["items_completed"] == 0


def test_api_timeline_and_totals_count_operations_once_per_day(tmp_path):
    for outcome in ("request", "success"):
        stats.record_event("api", service="fictional", operation="lookup", outcome=outcome, count=3, state_dir=tmp_path)
    stats.record_event("api", service="imaginary", operation="search", outcome="error", state_dir=tmp_path)
    prior_day = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    with sqlite3.connect(tmp_path / "data/upload_assistant.sqlite3") as db:
        db.execute("UPDATE stats_daily SET day = ? WHERE outcome = 'request'", (prior_day,))
    stats.record_event("api", service="fictional", operation="lookup", outcome="request", count=3, state_dir=tmp_path)

    result = stats.get_stats("7d", "real", tmp_path)

    assert result["overview"]["api_operations"] == 7
    assert sum(row["api"] for row in result["timeline"]) == 7
    assert sum(row["requests"] for row in result["api"]["by_service"]) == 7
    assert result["timeline"][-1]["api"] == 4


def test_empty_period_reports_decline_from_previous_activity(tmp_path):
    stats.record_event("item", operation="completed", state_dir=tmp_path)
    stats.record_event("upload", service="FICTIONAL", operation="tracker", state_dir=tmp_path)
    prior_day = (datetime.now(UTC).date() - timedelta(days=7)).isoformat()
    with sqlite3.connect(tmp_path / "data/upload_assistant.sqlite3") as db:
        db.execute("UPDATE stats_daily SET day = ?", (prior_day,))

    result = stats.get_stats("7d", "real", tmp_path)

    assert result["comparison"]["items_completed_pct"] == -100.0
    assert result["comparison"]["uploads_pct"] == -100.0
    assert len(result["timeline"]) == 7
    assert all(row["items"] == row["uploads"] == 0 for row in result["timeline"])


def test_invalid_filters_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="range"):
        stats.get_stats("yesterday", "real", tmp_path)
    with pytest.raises(ValueError, match="mode"):
        stats.get_stats("7d", "combined", tmp_path)
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        stats.get_stats("custom", "real", tmp_path, date_from="bad", date_to="2026-01-01")
    with pytest.raises(ValueError, match="on or before"):
        stats.get_stats("custom", "real", tmp_path, date_from="2026-01-02", date_to="2026-01-01")
    with pytest.raises(ValueError, match="timezone must be one of"):
        stats.get_stats("today", "real", tmp_path, time_basis="server")


def test_stats_can_resolve_periods_from_the_browser_local_date():
    result = stats.get_empty_stats("today", time_basis="browser", local_date="2026-09-27")

    assert result["time_context"]["basis"] == "browser"
    assert result["time_context"]["today"] == result["period"]["to"]
    assert result["period"]["from"] == result["period"]["to"] == "2026-09-27"
    assert result["period"]["timezone"] == "Browser local time"


def test_one_year_range_contains_365_inclusive_days():
    result = stats.get_empty_stats("1y", "real")

    first_day = datetime.fromisoformat(result["period"]["from"]).date()
    last_day = datetime.fromisoformat(result["period"]["to"]).date()
    assert (last_day - first_day).days == 364
    assert result["streaming"] == {"services": []}
    assert result["release_profiles"] == {"profiles": [], "by_category": []}


@pytest.mark.asyncio
async def test_metadata_cache_does_not_infer_api_calls_from_cache_activity(monkeypatch, tmp_path):
    monkeypatch.setattr(stats, "_database_path", lambda _state_dir=None: tmp_path / "data" / "upload_assistant.sqlite3")
    cache = cache_for(tmp_path, {"DEFAULT": {"metadata_cache_dir": "cache"}})

    assert is_cache_miss(await cache.get("imaginarydb", "title", "fictional-key"))
    await cache.set("imaginarydb", "title", "fictional-key", {"title": "Fictional Work"})
    assert await cache.get("imaginarydb", "title", "fictional-key") == {"title": "Fictional Work"}

    result = stats.get_stats("all", "real", tmp_path)
    assert result["cache"]["misses"] == 1
    assert result["cache"]["writes"] == 1
    assert result["cache"]["hits"] == 1
    assert result["api"]["total"] == 0
    assert b"Fictional Work" not in (tmp_path / "data" / "upload_assistant.sqlite3").read_bytes()


@pytest.mark.asyncio
async def test_stage_times_item_time_and_request_matches_are_recorded_when_the_item_completes(monkeypatch, tmp_path):
    monkeypatch.setattr(stats, "_database_path", lambda _state_dir=None: tmp_path / "data" / "upload_assistant.sqlite3")
    now = {"value": 100.0}
    monkeypatch.setattr(stats.time, "monotonic", lambda: now["value"])
    stats.begin_item_timing()
    stats.observe_run_event("stage", {"key": "prep", "status": "start"})
    now["value"] = 103.0
    stats.observe_run_event("stage", {"key": "prep", "status": "done"})
    stats.observe_run_event("stage", {"key": "upload", "status": "start"})
    now["value"] = 104.5
    stats.observe_run_event("stage", {"key": "upload", "status": "fail"})
    stats.observe_run_event("request", {"tracker": "fictional", "exact": True})
    stats.observe_run_event("request", {"tracker": "fictional", "exact": False})
    stats.observe_run_event("request", {"tracker": "imaginary", "exact": False})
    now["value"] = 110.0

    await stats.record_completed_item_stats_async(Meta(category="MOVIE", tracker_status={"FICTIONAL": {"upload_success": True}}), {})

    result = stats.get_stats("all", "real", tmp_path)
    assert result["stages"] == [
        {"stage": "prep", "items": 1, "failures": 0, "total_ms": 3000, "average_ms": 3000},
        {"stage": "upload", "items": 1, "failures": 1, "total_ms": 1500, "average_ms": 1500},
    ]
    assert result["overview"]["average_item_seconds"] == 10.0
    assert result["post_upload"]["requests_exact"] == 1
    assert result["post_upload"]["requests_partial"] == 2
    filtered = stats.get_stats("all", "real", tmp_path, tracker="FICTIONAL")
    assert filtered["post_upload"]["requests_partial"] == 1
    # Stage times describe the whole run, so a tracker view keeps them.
    assert len(filtered["stages"]) == 2


def test_webui_events_notify_listeners_in_cli_runs(monkeypatch):
    seen = []
    monkeypatch.setattr(webui_events, "_listeners", [])
    monkeypatch.delenv(webui_events.GUI_EVENTS_ENV, raising=False)
    webui_events.add_listener(lambda kind, payload: seen.append((kind, dict(payload))))

    webui_events.stage("prep", "start")
    webui_events.request_match("FICTIONAL", "Fictional Request", exact=True)

    assert seen == [("stage", {"key": "prep", "status": "start"}), ("request", {"tracker": "FICTIONAL", "exact": True})]


def test_hashing_speed_estimates_time_saved_by_reused_torrents(tmp_path):
    stats.record_event("artifact", service="torrent", operation="created", category="base", bytes_count=8_000_000, duration_ms=2_000, state_dir=tmp_path)
    stats.record_event("artifact", service="torrent", operation="reused", category="base", bytes_count=40_000_000, state_dir=tmp_path)

    overview = stats.get_stats("all", "real", tmp_path)["overview"]

    assert overview["hashed_bytes"] == 8_000_000
    assert overview["hashing_bytes_per_second"] == 4_000_000
    assert overview["hashing_seconds_saved"] == 10


@pytest.mark.asyncio
async def test_failed_routes_record_an_error_category_per_destination(monkeypatch, tmp_path):
    monkeypatch.setattr(stats, "_database_path", lambda _state_dir=None: tmp_path / "data" / "upload_assistant.sqlite3")
    meta = Meta(
        category="MOVIE",
        tracker_status={
            "FICTIONAL": {"upload": True, "upload_success": False, "status_message": "401 Unauthorized"},
            "IMAGINARY": {"upload": True, "error_reason": "timeout"},
        },
    )

    await stats.record_completed_item_stats_async(meta, {})

    rows = {row["destination"]: row for row in stats.get_stats("all", "real", tmp_path)["uploads"]["by_destination"]}
    assert rows["FICTIONAL"]["error_reasons"] == {"auth": 1}
    assert rows["IMAGINARY"]["error_reasons"] == {"timeout": 1}
    filtered = stats.get_stats("all", "real", tmp_path, tracker="IMAGINARY")["uploads"]["by_destination"]
    assert [row["error_reasons"] for row in filtered] == [{"timeout": 1}]
    assert b"Unauthorized" not in (tmp_path / "data" / "upload_assistant.sqlite3").read_bytes()


def test_post_upload_activity_is_aggregated_per_destination(tmp_path):
    stats.record_event("post_upload", service="cross_seed", operation="injected", destination="FICTIONAL", state_dir=tmp_path)
    stats.record_event("post_upload", service="trump_report", operation="submitted", destination="FICTIONAL", state_dir=tmp_path)
    stats.record_event("post_upload", service="trump_report", operation="submitted", outcome="error", destination="IMAGINARY", state_dir=tmp_path)

    post_upload = stats.get_stats("all", "real", tmp_path)["post_upload"]

    assert post_upload["cross_seeds"] == 1
    assert post_upload["trump_reports"] == 1
    assert post_upload["trump_report_errors"] == 1
    assert [row["destination"] for row in post_upload["by_destination"]] == ["FICTIONAL", "IMAGINARY"]


def test_image_hosts_report_reliability_and_fallbacks(tmp_path):
    stats.record_event("api", service="fictionalhost", operation="image_upload", count=3, duration_ms=300, bytes_count=900, state_dir=tmp_path)
    stats.record_event("api", service="fictionalhost", operation="image_upload", outcome="error", count=1, duration_ms=100, state_dir=tmp_path)
    stats.record_event("image_fallback", service="fictionalhost", operation="imaginaryhost", state_dir=tmp_path)

    image_hosts = stats.get_stats("all", "real", tmp_path)["image_hosts"]

    assert image_hosts["hosts"] == [
        {"host": "fictionalhost", "uploads": 3, "failures": 1, "success_rate": 75.0, "average_duration_ms": 100, "bytes": 900, "fallbacks_from": 1}
    ]
    assert image_hosts["fallbacks"] == [{"from": "fictionalhost", "to": "imaginaryhost", "count": 1}]


@pytest.fixture
def metadata_tracking(monkeypatch, tmp_path):
    """Install the httpx wrapper for one test and restore the original methods afterwards."""
    monkeypatch.setattr(httpx.AsyncClient, "send", httpx.AsyncClient.send)
    monkeypatch.setattr(httpx.Client, "send", httpx.Client.send)
    monkeypatch.setattr(stats, "_metadata_tracking_installed", False)
    monkeypatch.setattr(stats, "_database_path", lambda _state_dir=None: tmp_path / "data" / "upload_assistant.sqlite3")
    stats.install_metadata_api_tracking()
    return tmp_path


@pytest.mark.asyncio
async def test_metadata_provider_requests_count_as_external_operations(metadata_tracking):
    statuses = {"/3/movie/1": 200, "/3/movie/2": 404, "/3/movie/3": 500}

    def handler(request):
        return httpx.Response(statuses.get(request.url.path, 200))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        for path in statuses:
            await client.get(f"https://api.themoviedb.org{path}")
        await client.get("https://tracker.example/api/torrents")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        client.get("https://api.tvmaze.com/shows/1")

    services = {(row["service"], row["operation"]): row for row in stats.get_stats("all", "real", metadata_tracking)["api"]["by_service"]}
    assert set(services) == {("tmdb", "metadata"), ("tvmaze", "metadata")}
    assert services[("tmdb", "metadata")]["successes"] == 2
    assert services[("tmdb", "metadata")]["errors"] == 1
    assert services[("tvmaze", "metadata")]["requests"] == 1


@pytest.mark.asyncio
async def test_metadata_tracking_records_nothing_while_collection_is_disabled(metadata_tracking):
    stats.configure_stats(None)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: httpx.Response(200))) as client:
        await client.get("https://api.themoviedb.org/3/movie/1")

    assert not (metadata_tracking / "data" / "upload_assistant.sqlite3").exists()


def test_metadata_service_names_only_known_provider_hosts():
    assert stats.metadata_api_service(httpx.URL("https://www.googleapis.com/books/v1/volumes")) == "google_books"
    assert stats.metadata_api_service(httpx.URL("https://www.googleapis.com/drive/v3/files")) == ""
    assert stats.metadata_api_service(httpx.URL("https://api.audible.co.uk/1.0/catalog")) == "audible"
    assert stats.metadata_api_service(httpx.URL("https://image.tmdb.org/t/p/w500/poster.jpg")) == ""
