import json
import sqlite3
from contextlib import closing

import pytest

from src import app_db, upload_history, webui_events
from src.meta import Meta

MIB = 1024 * 1024


class FictionalTracker:
    torrent_url = "https://fictional.example/torrents/"


@pytest.fixture(autouse=True)
def history_on(monkeypatch, tmp_path):
    database = tmp_path / "data" / app_db.DATABASE_FILENAME
    monkeypatch.setattr(upload_history, "database_path", lambda _state_dir=None: database)
    monkeypatch.setenv("UA_STATS_SOURCE", "cli")
    monkeypatch.setattr(webui_events, "_detail_listeners", [upload_history.observe_detail])
    upload_history.configure_history({"DEFAULT": {}})
    yield database
    upload_history.configure_history(None)
    upload_history._item = None


def _sized(path, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.truncate(size)
    return path


def _rows(database, query, *parameters):
    with closing(sqlite3.connect(database)) as db:
        return db.execute(query, parameters).fetchall()


def test_history_is_on_unless_explicitly_disabled():
    assert upload_history.history_enabled(None) is True
    assert upload_history.history_enabled({"DEFAULT": {}}) is True
    assert upload_history.history_enabled({"DEFAULT": {"history_enabled": True}}) is True
    assert upload_history.history_enabled({"DEFAULT": {"history_enabled": False}}) is False


def test_fingerprint_survives_folder_rename_and_ignores_small_sidecars(tmp_path):
    first = tmp_path / "Fictional.Show.S01"
    _sized(first / "Fictional.Show.S01E01.mkv", 2 * MIB)
    _sized(first / "Fictional.Show.S01E02.mkv", 3 * MIB)
    before = upload_history.content_fingerprint(first)
    (first / "fictional.nfo").write_text("notes", encoding="utf-8")
    renamed = first.rename(tmp_path / "Renamed Folder")

    assert before
    assert upload_history.content_fingerprint(renamed) == before
    _sized(renamed / "Fictional.Show.S01E03.mkv", 2 * MIB)
    assert upload_history.content_fingerprint(renamed) != before


def test_fingerprint_of_small_releases_and_unreadable_paths(tmp_path):
    book = tmp_path / "Fictional Book.epub"
    book.write_bytes(b"fictional")

    other = tmp_path / "other" / "Fictional Book.epub"
    other.parent.mkdir()
    other.write_bytes(b"fictional, second edition")

    assert upload_history.content_fingerprint(book)
    # A folder holding only the release identifies it the same way as the file itself.
    assert upload_history.content_fingerprint(other.parent) == upload_history.content_fingerprint(other)
    assert upload_history.content_fingerprint(book) != upload_history.content_fingerprint(other)
    assert upload_history.content_fingerprint(tmp_path / "missing") == ""


def test_external_ids_use_the_cli_formats():
    meta = Meta(category="TV", imdb_id=12345, tmdb_id=678, tvdb_id=9, mal_id=0, tvmaze_id="")

    assert upload_history.external_ids(meta) == {"imdb": "tt0012345", "tmdb": "tv/678", "tvdb": "9"}
    assert upload_history.external_ids(Meta(category="MUSIC", music_discogs_release_id="555")) == {"discogs_release": "555"}


def _finished_meta(tmp_path, **overrides):
    release = _sized(tmp_path / "media" / "Fictional.Movie.2020.mkv", 2 * MIB)
    values = {
        "path": str(release),
        "name": "Fictional Movie 2020 1080p WEB-DL-FICTIONALGROUP",
        "title": "Fictional Movie",
        "year": 2020,
        "category": "MOVIE",
        "type": "WEBDL",
        "resolution": "1080p",
        "tag": "-FICTIONALGROUP",
        "source_size": 2 * MIB,
        "imdb_id": 1234567,
        "tmdb_id": 42,
        "tracker_status": {
            "FICT": {"upload": True, "upload_success": True, "torrent_id": "77", "status_message": "data error: debug text"},
            "OTHER": {"upload": True, "upload_success": False, "status_message": "401 Unauthorized"},
            "DUPE": {"upload": False, "dupe": True},
            "MANUAL": {"upload": True},
        },
    }
    values.update(overrides)
    meta = Meta(**values)
    meta["FICT_upload_duration"] = 3.456
    return meta


@pytest.mark.asyncio
async def test_finished_item_is_recorded_with_ids_results_and_details(tmp_path, history_on):
    upload_history.begin_item()
    webui_events.stage("upload", "start")
    upload_history.observe_run_event("stage", {"key": "upload", "status": "start"})
    webui_events.dupes("DUPE", [{"name": "Fictional Movie 2020 720p", "link": "https://dupe.example/1"}])
    webui_events.slot("FICT", "allowed", "Slot available", "No release in this slot")
    webui_events.request_match("FICT", "Fictional Movie request", link="https://fictional.example/requests/5", reward="100 BP", exact=True)
    webui_events.request_match("FICT", "Fictional Movie request", link="https://fictional.example/requests/5", reward="100 BP", exact=True)

    await upload_history.record_item_async(_finished_meta(tmp_path), {"FICT": FictionalTracker})

    item = _rows(history_on, "SELECT id, name, title, year, category, release_group, outcome, source, size, fingerprint FROM history_items")
    assert len(item) == 1
    item_id, name, title, year, category, group, outcome, source, size, fingerprint = item[0]
    assert (name, title, year, category, group, outcome, source, size) == (
        "Fictional Movie 2020 1080p WEB-DL-FICTIONALGROUP",
        "Fictional Movie",
        2020,
        "MOVIE",
        "FICTIONALGROUP",
        "success",
        "cli",
        2 * MIB,
    )
    assert fingerprint
    assert dict(_rows(history_on, "SELECT provider, value FROM history_ids WHERE item_id = ?", item_id)) == {"imdb": "tt1234567", "tmdb": "movie/42"}
    trackers = {row[0]: row[1:] for row in _rows(history_on, "SELECT tracker, status, message, link, torrent_id, duration, dupes, slot FROM history_trackers")}
    assert set(trackers) == {"FICT", "OTHER", "DUPE"}
    assert trackers["FICT"][:5] == ("success", "", "https://fictional.example/torrents/77", "77", 3.46)
    assert json.loads(trackers["FICT"][6])["verdict"] == "allowed"
    assert trackers["OTHER"][:3] == ("failed", "401 Unauthorized", "")
    assert trackers["DUPE"][0] == "dupe"
    assert json.loads(trackers["DUPE"][5])["entries"][0]["link"] == "https://dupe.example/1"
    assert _rows(history_on, "SELECT tracker, name, link, reward, exact FROM history_requests") == [
        ("FICT", "Fictional Movie request", "https://fictional.example/requests/5", "100 BP", 1)
    ]
    assert upload_history._item is None


@pytest.mark.asyncio
async def test_debug_runs_and_disabled_history_are_not_recorded(tmp_path, history_on):
    upload_history.begin_item()
    await upload_history.record_item_async(_finished_meta(tmp_path, debug=True), {})
    upload_history.configure_history({"DEFAULT": {"history_enabled": False}})
    upload_history.begin_item()
    await upload_history.record_item_async(_finished_meta(tmp_path), {})

    assert not history_on.exists() or _rows(history_on, "SELECT COUNT(*) FROM history_items") == [(0,)]


@pytest.mark.asyncio
async def test_approved_upload_without_result_is_skipped_when_the_upload_stage_never_ran(tmp_path, history_on):
    upload_history.begin_item()
    meta = _finished_meta(tmp_path, tracker_status={"FICT": {"upload": True}})

    await upload_history.record_item_async(meta, {})

    assert _rows(history_on, "SELECT outcome FROM history_items") == [("no_upload",)]
    assert _rows(history_on, "SELECT status FROM history_trackers") == [("skipped",)]


@pytest.mark.asyncio
async def test_items_that_stop_early_keep_their_outcome_and_reason(tmp_path, history_on):
    upload_history.begin_item()
    meta = _finished_meta(tmp_path, name="", tracker_status={})

    await upload_history.record_item_async(meta, {}, outcome="skipped", reason="skipped_by_user")

    assert _rows(history_on, "SELECT name, outcome, reason FROM history_items") == [("Fictional.Movie.2020.mkv", "skipped", "skipped_by_user")]


@pytest.mark.asyncio
async def test_database_failure_never_breaks_the_upload(tmp_path, monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(upload_history, "connect_app_db", unavailable)
    upload_history.begin_item()

    await upload_history.record_item_async(_finished_meta(tmp_path), {})

    assert upload_history._item is None


def test_detail_events_reach_the_history_without_the_web_ui(monkeypatch):
    monkeypatch.delenv(webui_events.GUI_EVENTS_ENV, raising=False)
    upload_history.begin_item()

    webui_events.request_match("FICT", "Fictional request", link="https://fictional.example/requests/1")

    assert upload_history._item is not None
    assert list(upload_history._item.requests.values()) == [
        {"tracker": "FICT", "name": "Fictional request", "exact": False, "link": "https://fictional.example/requests/1"}
    ]
