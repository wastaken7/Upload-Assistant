import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime

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
async def test_an_error_after_the_uploads_keeps_them_and_otherwise_is_an_error(tmp_path, history_on):
    for tracker_status, outcome in (({"FICT": {"upload_success": True}}, "success"), ({}, "error")):
        upload_history.begin_item()
        assert upload_history.item_active()
        await upload_history.record_item_async(_finished_meta(tmp_path, tracker_status=tracker_status), {}, reason="exception")
        assert not upload_history.item_active()
        assert _rows(history_on, "SELECT outcome, reason FROM history_items ORDER BY id DESC LIMIT 1") == [(outcome, "exception")]


def test_fingerprint_skips_broken_symlinks(tmp_path):
    release = tmp_path / "Fictional.Show.S01"
    _sized(release / "Fictional.Show.S01E01.mkv", 2 * MIB)
    before = upload_history.content_fingerprint(release)
    try:
        (release / "missing.mkv").symlink_to(tmp_path / "nowhere.mkv")
    except OSError:
        pytest.skip("symlinks cannot be created here")

    assert before
    assert upload_history.content_fingerprint(release) == before


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


def _tracker(tracker, status, **values):
    return {"tracker": tracker, "status": status, "message": "", "link": "", "torrent_id": "", "duration": None, "dupes": None, "slot": None, **values}


def _record(history_database, **overrides):
    record = {
        "started_at": "2026-03-01T10:00:00+00:00",
        "finished_at": "2026-03-01T10:05:00+00:00",
        "source": "webui",
        "path": "/media/Fictional.Movie.2020",
        "name": "Fictional Movie 2020 1080p WEB-DL-FICTIONALGROUP",
        "title": "Fictional Movie",
        "year": 2020,
        "category": "MOVIE",
        "release_type": "WEBDL",
        "resolution": "1080p",
        "release_group": "FICTIONALGROUP",
        "season": "",
        "episode": "",
        "size": 5 * MIB,
        "fingerprint": "fictional-fingerprint",
        "infohash": "",
        "outcome": "success",
        "reason": "",
        "duration_ms": 1200,
        "site_check": False,
        "personal_release": False,
        "artwork_url": "",
        "ids": {"imdb": "tt0000001", "tmdb": "movie/1"},
        "trackers": [
            _tracker("FICT", "success", link="https://fictional.example/t/1", torrent_id="1", duration=2.0),
            _tracker("OTHER", "dupe", message="Possible dupe", dupes={"entries": [{"name": "Older copy"}]}),
        ],
        "requests": [{"tracker": "FICT", "name": "Fictional Movie request", "link": "https://fictional.example/r/1", "reward": "50 BP", "status": "", "exact": True}],
    }
    record.update(overrides)
    return upload_history.record_item(record, history_database.parent.parent)


def test_listing_filters_paginates_and_counts(history_on):
    _record(history_on)
    _record(
        history_on,
        name="Fictional Show S01 720p HDTV-OTHERGROUP",
        title="Fictional Show",
        category="TV",
        outcome="error",
        finished_at="2026-03-02T10:00:00+00:00",
        trackers=[_tracker("FICT", "failed", message="Timeout")],
        requests=[],
    )
    _record(
        history_on,
        name="Fictional Album 2021 FLAC",
        title="Fictional Album",
        category="MUSIC",
        outcome="no_upload",
        finished_at="2026-03-03T10:00:00+00:00",
        trackers=[],
        requests=[],
        ids={},
    )
    state_dir = history_on.parent.parent

    everything = upload_history.list_items(state_dir)
    assert [item["category"] for item in everything["items"]] == ["MUSIC", "TV", "MOVIE"]
    assert everything["counts"] == {"success": 1, "error": 1, "no_upload": 1, "skipped": 0}
    assert everything["facets"] == {"categories": ["MOVIE", "MUSIC", "TV"], "trackers": ["FICT", "OTHER"]}
    movie = everything["items"][2]
    assert movie["ids"] == {"imdb": "tt0000001", "tmdb": "movie/1"}
    assert movie["request_count"] == 1
    assert [tracker["status"] for tracker in movie["trackers"]] == ["success", "dupe"]

    assert [item["title"] for item in upload_history.list_items(state_dir, search="fictional show")["items"]] == ["Fictional Show"]
    assert upload_history.list_items(state_dir, search="100%")["total"] == 0
    assert [item["title"] for item in upload_history.list_items(state_dir, tracker="fict", tracker_status="failed")["items"]] == ["Fictional Show"]
    assert [item["title"] for item in upload_history.list_items(state_dir, has_requests=True)["items"]] == ["Fictional Movie"]
    errors = upload_history.list_items(state_dir, outcome="error")
    assert errors["total"] == 1
    assert errors["counts"]["success"] == 1
    window = upload_history.list_items(state_dir, after="2026-03-02", before="2026-03-03T00:00:00Z")
    assert [item["title"] for item in window["items"]] == ["Fictional Show"]
    second_page = upload_history.list_items(state_dir, limit=1, offset=1)
    assert second_page["total"] == 3
    assert [item["title"] for item in second_page["items"]] == ["Fictional Show"]


def _titles(state_dir, search):
    return sorted(item["title"] for item in upload_history.list_items(state_dir, search=search)["items"])


def test_search_finds_entries_by_their_external_ids(history_on):
    _record(history_on, title="Fictional Movie", ids={"imdb": "tt0123456", "tmdb": "movie/42", "tvdb": "2020"})
    _record(history_on, name="Fictional Show S01", path="/media/show", title="Fictional Show", category="TV", ids={"tmdb": "tv/42", "tvdb": "777"})
    _record(history_on, name="Fictional Book", path="/media/book", title="Fictional Book", category="BOOK", ids={"isbn": "978-0-00-000000-1", "asin": "B000FICT01", "openlibrary": "OL1W"})
    _record(history_on, name="Fictional Album FLAC", path="/media/album", title="Fictional Album", category="MUSIC", ids={"discogs_release": "123", "discogs_master": "45"})
    state_dir = history_on.parent.parent

    # Distinctive IDs match without a prefix, in any case and with or without padding or hyphens.
    assert _titles(state_dir, "TT0123456") == _titles(state_dir, "tt123456") == ["Fictional Movie"]
    assert _titles(state_dir, "movie/42") == ["Fictional Movie"]
    assert _titles(state_dir, "9780000000001") == _titles(state_dir, "b000fict01") == _titles(state_dir, "ol1w") == ["Fictional Book"]
    # Bare numbers stay text searches: 2020 is the movie's year in its name, not its TVDB ID.
    assert _titles(state_dir, "777") == []
    assert _titles(state_dir, "2020") == ["Fictional Movie"]
    # A prefix matches any provider, and narrows TMDb to the kind given.
    assert _titles(state_dir, "tvdb:777") == ["Fictional Show"]
    assert _titles(state_dir, "TMDB:42") == ["Fictional Movie", "Fictional Show"]
    assert _titles(state_dir, "tmdb:tv/42") == ["Fictional Show"]
    assert _titles(state_dir, "imdb:123456") == ["Fictional Movie"]
    assert _titles(state_dir, "isbn:978-0000000001") == ["Fictional Book"]
    assert _titles(state_dir, "discogs:45") == _titles(state_dir, "discogs_release:https://www.discogs.com/release/123") == ["Fictional Album"]
    # Prefixed IDs combine with text terms; a malformed ID matches nothing.
    assert _titles(state_dir, "fictional tmdb:42") == ["Fictional Movie", "Fictional Show"]
    assert _titles(state_dir, "imdb:fictional") == []
    # An unknown prefix is ordinary text.
    assert _titles(state_dir, "movie:42") == []
    assert upload_history.export_items(state_dir, search="tvdb:777")[0]["title"] == "Fictional Show"
    # The Discogs kind in the value is kept; one contradicting the prefix matches nothing.
    _record(history_on, name="Other Album FLAC", path="/media/other", title="Other Album", category="MUSIC", ids={"discogs_release": "45"})
    assert _titles(state_dir, "discogs:45") == ["Fictional Album", "Other Album"]
    assert _titles(state_dir, "discogs:master/45") == _titles(state_dir, "discogs_master:45") == ["Fictional Album"]
    assert _titles(state_dir, "discogs:https://www.discogs.com/release/45-Other") == ["Other Album"]
    assert _titles(state_dir, "discogs_release:https://www.discogs.com/master/45") == []
    # Digits that are not ASCII never reach int().
    assert _titles(state_dir, "tmdb:²") == _titles(state_dir, "tmdb:tv/²") == []


def test_listing_rejects_unknown_filters(history_on):
    with pytest.raises(ValueError, match="outcome"):
        upload_history.list_items(history_on.parent.parent, outcome="maybe")
    with pytest.raises(ValueError, match="tracker_status"):
        upload_history.list_items(history_on.parent.parent, tracker_status="maybe")
    with pytest.raises(ValueError, match="after"):
        upload_history.list_items(history_on.parent.parent, after="yesterday")


def test_listing_an_empty_installation_does_not_create_the_database(tmp_path):
    page = upload_history.list_items(tmp_path)

    assert page["items"] == []
    assert page["total"] == 0
    assert not (tmp_path / "data").exists()


def test_entry_details_delete_and_clear(history_on):
    state_dir = history_on.parent.parent
    first = _record(history_on)
    second = _record(history_on)

    item = upload_history.get_item(first, state_dir)
    assert item["ids"] == [
        {"provider": "imdb", "value": "tt0000001", "link": "https://www.imdb.com/title/tt0000001/"},
        {"provider": "tmdb", "value": "movie/1", "link": "https://www.themoviedb.org/movie/1"},
    ]
    assert item["trackers"][1]["dupes"] == {"entries": [{"name": "Older copy"}]}
    assert item["requests"][0]["reward"] == "50 BP"
    assert upload_history.get_item(9999, state_dir) is None

    assert upload_history.delete_item(first, state_dir) is True
    assert upload_history.delete_item(first, state_dir) is False
    assert _rows(history_on, "SELECT COUNT(*) FROM history_trackers WHERE item_id = ?", first) == [(0,)]
    assert upload_history.clear_history(state_dir) == 1
    assert upload_history.get_item(second, state_dir) is None


def test_clearing_history_keeps_statistics(history_on):
    from src import stats

    state_dir = history_on.parent.parent
    stats.configure_stats({"DEFAULT": {"stats_enabled": True}})
    try:
        stats.record_event("item", operation="completed", state_dir=state_dir)
        _record(history_on)
        upload_history.clear_history(state_dir)
        assert stats.get_stats("all", "real", state_dir)["overview"]["items_completed"] == 1
    finally:
        stats.configure_stats(None)


@pytest.mark.parametrize(
    ("provider", "value", "link"),
    [
        ("imdb", "tt0000001", "https://www.imdb.com/title/tt0000001/"),
        ("imdb", "0000001", ""),
        ("tmdb", "tv/5", "https://www.themoviedb.org/tv/5"),
        ("tmdb", "person/5", ""),
        ("tvdb", "7", "https://thetvdb.com/dereferrer/series/7"),
        ("discogs_master", "8", "https://www.discogs.com/master/8"),
        ("isbn", "9780000000000", ""),
        ("openlibrary", "OL45883W", "https://openlibrary.org/works/OL45883W"),
        ("openlibrary", "OL7353617M", "https://openlibrary.org/books/OL7353617M"),
        ("openlibrary", "OL/../W", ""),
        ("tvdb", "../7", ""),
    ],
)
def test_id_links_only_for_well_formed_ids(provider, value, link):
    assert upload_history.id_link(provider, value) == link


def test_export_includes_every_matching_entry_with_its_details(history_on):
    state_dir = history_on.parent.parent
    _record(history_on)
    _record(history_on, name="Fictional Show S01", title="Fictional Show", category="TV", outcome="error", trackers=[], requests=[], ids={})

    movies = upload_history.export_items(state_dir, category="movie")
    everything = upload_history.export_items(state_dir)

    assert [item["title"] for item in movies] == ["Fictional Movie"]
    assert movies[0]["ids"] == {"imdb": "tt0000001", "tmdb": "movie/1"}
    assert movies[0]["trackers"][0]["link"] == "https://fictional.example/t/1"
    assert movies[0]["requests"][0]["reward"] == "50 BP"
    assert len(everything) == 2
    with pytest.raises(ValueError, match="outcome"):
        upload_history.export_items(state_dir, outcome="maybe")


def test_csv_export_flattens_details_and_neutralizes_formulas(history_on):
    _record(history_on, name="=HYPERLINK(\"https://fictional.example\")", trackers=[_tracker("FICT", "failed", message="-1 error")])

    text = upload_history.export_csv(upload_history.export_items(history_on.parent.parent))
    header, row = text.splitlines()

    assert header.split(",")[:3] == ["finished_at", "name", "title"]
    assert row.split(",")[1].startswith("\"'=HYPERLINK")
    assert "FICT=failed" in row
    assert "imdb=tt0000001; tmdb=movie/1" in row
    assert "FICT: Fictional Movie request (50 BP)" in row


@pytest.mark.parametrize(("value", "days"), [(30, 30), ("7", 7), (0, 0), (-5, 0), ("soon", 0), (True, 0), (None, 0)])
def test_retention_setting_is_a_non_negative_number_of_days(value, days):
    assert upload_history.history_retention_days({"DEFAULT": {"history_retention_days": value}}) == days
    assert upload_history.history_retention_days({"DEFAULT": {}}) == 0


@pytest.mark.parametrize(
    ("value", "neutralized"),
    [("=1+1", True), (" =1+1", True), ("\t@SUM(A1)", True), ("\n-2", True), ("Fictional = name", False), ("", False)],
)
def test_csv_cells_that_a_spreadsheet_could_run_are_neutralized(value, neutralized):
    assert upload_history._csv_cell(value) == (f"'{value}" if neutralized else value)


@pytest.mark.parametrize(
    ("value", "warns"), [(30, False), ("30", False), (30.0, False), (0, False), (True, True), (-1, True), ("soon", True), ("30.5", True), (float("inf"), True)]
)
def test_retention_setting_warnings_match_how_it_is_read(value, warns):
    from src.configvalidator import _validate_default_section

    _errors, warnings = _validate_default_section({"tmdb_api": "test", "history_retention_days": value})

    assert any(warning.key == "history_retention_days" for warning in warnings) is warns
    assert (upload_history.history_retention_days({"DEFAULT": {"history_retention_days": value}}) > 0) is (not warns and int(value) > 0)


def test_retention_removes_only_entries_older_than_the_limit(history_on):
    state_dir = history_on.parent.parent
    _record(history_on, finished_at="2000-01-01T00:00:00+00:00", title="Old")
    _record(history_on, finished_at=datetime.now(UTC).isoformat(), title="Recent")

    assert upload_history.prune_history(0, state_dir) == 0
    assert upload_history.prune_history(999_999, state_dir) == 0
    assert upload_history.prune_history(30, state_dir) == 1
    assert [item["title"] for item in upload_history.list_items(state_dir)["items"]] == ["Recent"]
    assert _rows(history_on, "SELECT COUNT(*) FROM history_trackers") == [(2,)]


@pytest.mark.asyncio
async def test_recording_applies_the_configured_retention(tmp_path, history_on):
    _record(history_on, finished_at="2000-01-01T00:00:00+00:00", title="Old")
    upload_history.configure_history({"DEFAULT": {"history_retention_days": 30}})
    upload_history.begin_item()

    await upload_history.record_item_async(_finished_meta(tmp_path), {})

    assert [row[0] for row in _rows(history_on, "SELECT title FROM history_items")] == ["Fictional Movie"]


def test_fingerprint_is_empty_when_a_subfolder_cannot_be_listed(tmp_path, monkeypatch):
    _sized(tmp_path / "release" / "Fictional.mkv", 2 * MIB)

    def walk(_top, onerror=None):
        yield str(tmp_path / "release"), [], ["Fictional.mkv"]
        onerror(PermissionError("fictional denied"))

    monkeypatch.setattr(upload_history.os, "walk", walk)

    assert upload_history.content_fingerprint(tmp_path / "release") == ""


@pytest.mark.asyncio
async def test_bracketed_names_openlibrary_ids_and_published_links_are_kept(tmp_path, history_on):
    class InstanceUrlTracker:
        pass

    upload_history.begin_item()
    webui_events.tracker_result("FICT", "success", link="https://fictional.example/details/9", torrent_id="9")
    meta = _finished_meta(
        tmp_path,
        name="Fictional Artist - Fictional Album [b] [FLAC]",
        category="BOOK",
        openlibrary="OL45883W",
        tracker_status={"FICT": {"upload": True, "upload_success": True, "torrent_id": "9"}},
    )

    await upload_history.record_item_async(meta, {"FICT": InstanceUrlTracker})

    assert _rows(history_on, "SELECT name FROM history_items") == [("Fictional Artist - Fictional Album [b] [FLAC]",)]
    assert ("openlibrary", "OL45883W") in _rows(history_on, "SELECT provider, value FROM history_ids")
    assert _rows(history_on, "SELECT link, torrent_id FROM history_trackers") == [("https://fictional.example/details/9", "9")]


@pytest.mark.parametrize(("nzb_path", "upload_started", "expected"), [("/out/fictional.nzb", False, ("success", "Posted to Usenet")), ("", True, ("failed", "Usenet upload failed"))])
def test_a_requested_usenet_post_has_its_own_result(tmp_path, nzb_path, upload_started, expected):
    upload_history.begin_item()
    if upload_started:
        upload_history.observe_run_event("stage", {"key": "upload", "status": "start"})
    meta = _finished_meta(tmp_path, trackers=["USENET"], nzb_path=nzb_path, tracker_status={})

    record = upload_history.build_item_record(meta, {})

    assert [(row["tracker"], row["status"], row["message"]) for row in record["trackers"]] == [("USENET", *expected)]
    assert record["outcome"] == ("success" if nzb_path else "error")


def test_the_database_is_private_to_its_owner(history_on):
    if upload_history.os.name == "nt":
        pytest.skip("Windows relies on the per-user profile folder's permissions")
    history_on.parent.mkdir(parents=True)
    history_on.touch(mode=0o644)
    history_on.chmod(0o644)

    with closing(app_db.connect(history_on)):
        pass

    assert history_on.stat().st_mode & 0o777 == 0o600
