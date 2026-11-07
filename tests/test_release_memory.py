import asyncio
import sqlite3
from contextlib import closing

import pytest

from src import app_db, upload_history
from src.meta import Meta

MIB = 1024 * 1024


@pytest.fixture(autouse=True)
def database(monkeypatch, tmp_path):
    path = tmp_path / "state" / "data" / app_db.DATABASE_FILENAME
    monkeypatch.setattr(upload_history, "database_path", lambda _state_dir=None: path)
    upload_history.configure_history({"DEFAULT": {}})
    yield path
    upload_history.configure_history(None)


def _release(tmp_path, folder="Fictional.Movie.2020"):
    root = tmp_path / folder
    root.mkdir()
    with (root / "Fictional.Movie.2020.mkv").open("wb") as handle:
        handle.truncate(2 * MIB)
    return root


def _confirm(meta):
    """Answer yes at "Is this correct?" for the IDs the release has now."""
    meta.ids_confirmed = True
    meta.confirmed_ids = upload_history.external_ids(meta)
    return meta


def _confirmed_meta(path, **values):
    meta = _confirm(Meta(path=str(path), category="MOVIE", imdb_id=1234567, tmdb_id=42, tvdb_id=0, **values))
    meta.manual_answers = {"xxx.tags": ["fictional tag"]}
    return meta


def _load(path, **values):
    meta = Meta(path=str(path), **values)
    asyncio.run(upload_history.load_release_memory(meta))
    return meta


def test_confirmed_ids_and_answers_are_reused_after_a_rename(tmp_path, caplog):
    release = _release(tmp_path)
    assert upload_history.remember_release(_confirmed_meta(release)) is True
    renamed = release.rename(tmp_path / "Renamed")

    meta = _load(renamed)
    meta.category = "MOVIE"
    applied = upload_history.apply_saved_ids(meta)

    assert meta.manual_answers == {"xxx.tags": ["fictional tag"]}
    assert (meta.imdb_manual, meta.tmdb_manual, meta.tmdb_manual_category) == ("tt1234567", 42, "MOVIE")
    assert applied == ["IMDb tt1234567", "TMDb movie/42"]


def test_unconfirmed_ids_are_not_remembered_but_answers_are(tmp_path):
    release = _release(tmp_path)
    meta = _confirmed_meta(release, debug=True)
    meta.ids_confirmed = False

    upload_history.remember_release(meta)
    loaded = _load(release)

    assert loaded.saved_ids == {}
    assert loaded.manual_answers == {"xxx.tags": ["fictional tag"]}


def test_a_successful_upload_confirms_ids_without_a_prompt(tmp_path):
    release = _release(tmp_path)
    meta = _confirmed_meta(release, tracker_status={"FICT": {"upload_success": True}})
    meta.ids_confirmed = False

    upload_history.remember_release(meta)

    assert _load(release).saved_ids == {"imdb": "tt1234567", "tmdb": "movie/42", "category": "MOVIE"}


def test_a_later_unconfirmed_run_keeps_the_confirmed_ids(tmp_path):
    release = _release(tmp_path)
    upload_history.remember_release(_confirmed_meta(release))
    later = Meta(path=str(release), category="MOVIE", imdb_id=7654321)
    later.manual_answers = {"game.platform": "PC"}

    upload_history.remember_release(later)
    loaded = _load(release)

    assert loaded.saved_ids["imdb"] == "tt1234567"
    assert loaded.manual_answers == {"game.platform": "PC"}


def test_any_id_given_on_the_command_line_disables_saved_ids_and_answer_wins(tmp_path):
    release = _release(tmp_path)
    upload_history.remember_release(_confirmed_meta(release))

    meta = _load(release, imdb_manual="tt0000009", manual_answers={"xxx.tags": ["from cli"]})
    meta.category = "MOVIE"
    applied = upload_history.apply_saved_ids(meta)

    # A corrected IMDb ID must not be paired with the TMDb ID saved for the old one.
    assert applied == []
    assert meta.imdb_manual == "tt0000009"
    assert not meta.tmdb_manual
    assert meta.manual_answers == {"xxx.tags": ["from cli"]}


@pytest.mark.parametrize(("category", "no_saved_ids"), [("TV", False), ("MOVIE", True)])
def test_saved_ids_are_skipped_for_another_category_or_when_disabled(tmp_path, category, no_saved_ids):
    release = _release(tmp_path)
    upload_history.remember_release(_confirmed_meta(release))

    meta = _load(release, no_saved_ids=no_saved_ids)
    meta.category = category

    assert upload_history.apply_saved_ids(meta) == []
    assert not meta.imdb_manual
    assert not meta.tmdb_manual


def test_tv_ids_fill_their_manual_fields(tmp_path):
    release = _release(tmp_path, "Fictional.Show.S01")
    meta = _confirm(Meta(path=str(release), category="TV", imdb_id=1, tmdb_id=2, tvdb_id=3, tvmaze_id=4, mal_id=5))
    upload_history.remember_release(meta)

    loaded = _load(release)
    loaded.category = "TV"
    upload_history.apply_saved_ids(loaded)

    assert (loaded.imdb_manual, loaded.tmdb_manual, loaded.tvdb_manual, loaded.tvmaze_manual, loaded.mal_manual) == ("tt0000001", 2, "3", 4, "5")


def test_nothing_is_written_for_a_release_with_nothing_to_remember(tmp_path, database):
    release = _release(tmp_path)

    assert upload_history.remember_release(Meta(path=str(release), category="MOVIE")) is False
    assert upload_history.remember_release(_confirm(Meta(path=str(tmp_path / "missing"), category="MOVIE", imdb_id=1))) is False
    assert not database.exists()


def test_release_memory_is_kept_for_debug_runs_and_with_history_off(tmp_path, database):
    release = _release(tmp_path)
    upload_history.configure_history({"DEFAULT": {"history_enabled": False}})
    upload_history.begin_item()

    asyncio.run(upload_history.record_item_async(_confirmed_meta(release, debug=True), {}))

    with closing(sqlite3.connect(database)) as db:
        assert db.execute("SELECT COUNT(*) FROM history_items").fetchone() == (0,)
        assert db.execute("SELECT category FROM release_memory").fetchall() == [("MOVIE",)]


def test_an_unreadable_database_leaves_the_release_unchanged(tmp_path, database):
    release = _release(tmp_path)
    database.parent.mkdir(parents=True)
    database.write_bytes(b"fictional invalid database")

    meta = _load(release)

    assert meta.release_fingerprint
    assert meta.saved_ids == {}
    assert meta.manual_answers == {}


def test_saved_ids_wait_until_the_category_is_known(tmp_path):
    release = _release(tmp_path)
    upload_history.remember_release(_confirmed_meta(release))
    meta = _load(release)

    assert upload_history.apply_saved_ids(meta) == []
    assert meta.saved_ids
    meta.category = "MOVIE"
    assert upload_history.apply_saved_ids(meta) == ["IMDb tt1234567", "TMDb movie/42"]
    assert meta.saved_ids == {}
    assert upload_history.apply_saved_ids(meta) == []


def test_book_ids_fill_their_manual_fields(tmp_path):
    release = _release(tmp_path, "Fictional Book")
    meta = _confirm(Meta(path=str(release), category="BOOK", openlibrary="OL1W", book_isbn="9780000000001"))
    upload_history.remember_release(meta)

    loaded = _load(release)
    loaded.category = "BOOK"
    applied = upload_history.apply_saved_ids(loaded)

    assert (loaded.openlibrary, loaded.book_isbn) == ("OL1W", "9780000000001")
    assert applied == ["ISBN 9780000000001", "Open Library OL1W"]


def test_ids_found_after_the_confirmation_are_not_remembered_without_an_upload(tmp_path):
    release = _release(tmp_path)
    meta = _confirmed_meta(release)
    meta.douban_id = 999

    upload_history.remember_release(meta)

    assert "douban" not in _load(release).saved_ids


def test_a_confirmed_run_without_ids_keeps_the_saved_ones(tmp_path):
    release = _release(tmp_path)
    upload_history.remember_release(_confirmed_meta(release))

    upload_history.remember_release(_confirm(Meta(path=str(release), category="MOVIE")))

    assert _load(release).saved_ids["imdb"] == "tt1234567"


def test_a_saved_tv_category_replaces_a_movie_guess_but_not_an_explicit_one(tmp_path):
    release = _release(tmp_path, "Fictional.Show.Complete")
    upload_history.remember_release(_confirm(Meta(path=str(release), category="TV", imdb_id=1, tmdb_id=2)))

    guessed = _load(release)
    guessed.category = "MOVIE"
    explicit = _load(release, manual_category="MOVIE")
    explicit.category = "MOVIE"

    assert upload_history.apply_saved_ids(guessed) == ["IMDb tt0000001", "TMDb tv/2"]
    assert (guessed.category, guessed.tmdb_manual_category) == ("TV", "TV")
    assert upload_history.apply_saved_ids(explicit) == []
    assert explicit.category == "MOVIE"


def test_confirmed_ids_replace_ids_found_automatically(tmp_path):
    release = _release(tmp_path)
    upload_history.remember_release(_confirmed_meta(release))

    meta = _load(release, imdb_id=7654321)
    meta.category = "MOVIE"
    applied = upload_history.apply_saved_ids(meta)

    assert applied == ["IMDb tt1234567", "TMDb movie/42"]
    assert meta.imdb_id is None
    assert meta.imdb_manual == "tt1234567"
