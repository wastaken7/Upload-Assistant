import asyncio
import sqlite3
from contextlib import closing
from types import SimpleNamespace

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
    later = _load(release)
    later.category, later.imdb_id = "MOVIE", 7654321
    # A saved answer that no longer fits is dropped when the question is asked.
    later.manual_answers = {"game.platform": "PC"}

    upload_history.remember_release(later)
    loaded = _load(release)

    assert loaded.saved_ids["imdb"] == "tt1234567"
    assert loaded.manual_answers == {"game.platform": "PC"}


def test_answers_survive_an_item_that_stops_before_reading_them(tmp_path):
    release = _release(tmp_path)
    upload_history.remember_release(_confirmed_meta(release))
    stopped = Meta(path=str(release), category="MOVIE")
    stopped.manual_answers = {"game.platform": "PC"}

    upload_history.remember_release(stopped)
    upload_history.remember_release(Meta(path=str(release), category="MOVIE"))

    assert _load(release).manual_answers == {"xxx.tags": ["fictional tag"], "game.platform": "PC"}


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


def _confirmation_edit(meta, **edits):
    """Re-parse at "Is this correct?" as Args.parse does, then prepare the release again."""
    meta.tmdb_manual = meta.tmdb_id = meta.imdb_id = None
    meta.tmdb_manual_category = ""
    for key, value in edits.items():
        setattr(meta, key, value)
    asyncio.run(upload_history.load_release_memory(meta))
    return upload_history.apply_saved_ids(meta)


def _tv_meta_with_saved_ids(tmp_path):
    release = _release(tmp_path, "Fictional.Show.S01")
    upload_history.remember_release(_confirm(Meta(path=str(release), category="TV", imdb_id=1, tmdb_id=2, tvdb_id=3)))
    meta = _load(release)
    meta.category = "TV"
    upload_history.apply_saved_ids(meta)
    # The metadata search copies the manual TVDB ID.
    meta.tvdb_id = int(meta.tvdb_manual)
    return meta


def test_an_edit_without_ids_applies_the_saved_ids_again(tmp_path):
    meta = _tv_meta_with_saved_ids(tmp_path)

    assert _confirmation_edit(meta, tag="-FICT") == ["IMDb tt0000001", "TMDb tv/2", "TVDB 3"]
    assert (meta.imdb_manual, meta.tmdb_manual, meta.tvdb_manual) == ("tt0000001", 2, "3")


@pytest.mark.parametrize("edits", [{"tmdb_manual": 99, "tmdb_manual_category": "TV"}, {"no_saved_ids": True}])
def test_an_id_or_no_saved_ids_in_an_edit_drops_the_saved_ids(tmp_path, edits):
    meta = _tv_meta_with_saved_ids(tmp_path)
    expected_tmdb = edits.get("tmdb_manual")

    assert _confirmation_edit(meta, **edits) == []
    assert (meta.imdb_manual, meta.tvdb_manual, meta.tvdb_id) == (None, None, None)
    assert meta.tmdb_manual == expected_tmdb


def test_an_edit_keeps_an_id_given_in_place_of_a_saved_one(tmp_path):
    meta = _tv_meta_with_saved_ids(tmp_path)

    assert _confirmation_edit(meta, tvdb_manual="77") == []
    assert (meta.tvdb_manual, meta.imdb_manual) == ("77", None)


def test_a_steam_id_given_disables_the_saved_igdb_id(tmp_path):
    release = _release(tmp_path, "Fictional Game")
    upload_history.remember_release(_confirm(Meta(path=str(release), category="GAME", igdb_id=12)))

    meta = _load(release, steam_manual="34")
    meta.category = "GAME"

    assert upload_history.apply_saved_ids(meta) == []
    assert not meta.igdb_manual


def test_saved_book_ids_reach_the_isbn_and_asin_lookups(tmp_path):
    release = _release(tmp_path, "Fictional Audiobook")
    upload_history.remember_release(_confirm(Meta(path=str(release), category="BOOK", isbn="9780000000002", asin="B000000000")))

    meta = _load(release)
    meta.category = "BOOK"
    upload_history.apply_saved_ids(meta)

    assert (meta.book_isbn, meta.isbn, meta.book_asin, meta.asin) == ("9780000000002", "9780000000002", "B000000000", "B000000000")


def test_discogs_ids_come_from_the_music_release_or_normalized_arguments():
    matched = Meta(category="MUSIC", music_release={"external_ids": {"discogs_release": "123", "discogs_master": "45"}})
    from_url = Meta(category="MUSIC", music_discogs_id="https://www.discogs.com/master/678-Fictional-Album")

    assert upload_history.external_ids(matched) == {"discogs_release": "123", "discogs_master": "45"}
    assert upload_history.external_ids(from_url) == {"discogs_master": "678"}
    assert upload_history.external_ids(Meta(category="MUSIC", music_discogs_release_id="not an id")) == {}


def test_saved_discogs_ids_are_labelled(tmp_path):
    release = _release(tmp_path, "Fictional Album")
    upload_history.remember_release(_confirm(Meta(path=str(release), category="MUSIC", music_release={"external_ids": {"discogs_release": "123"}})))

    meta = _load(release)
    meta.category = "MUSIC"

    assert upload_history.apply_saved_ids(meta) == ["Discogs release 123"]
    assert meta.music_discogs_release_id == "123"


def test_an_id_given_again_in_an_edit_is_kept_with_no_saved_ids(tmp_path):
    meta = _tv_meta_with_saved_ids(tmp_path)
    parser = SimpleNamespace(_actions=[SimpleNamespace(dest="tmdb_manual", option_strings=["-tmdb", "--tmdb"])])
    # Args.parse clears the TMDb ID, then sets the one given: the same as the saved one.
    meta.imdb_id = None
    meta.tmdb_manual, meta.tmdb_manual_category, meta.no_saved_ids = 2, "TV", True

    upload_history.keep_given_ids(meta, parser, ["--tag", "FICT", "--tmdb", "tv/2", "--no-saved-ids"])
    asyncio.run(upload_history.load_release_memory(meta))

    assert upload_history.apply_saved_ids(meta) == []
    assert (meta.tmdb_manual, meta.tmdb_manual_category) == (2, "TV")
    assert (meta.imdb_manual, meta.tvdb_manual) == (None, None)


def test_discogs_arguments_do_not_join_the_selected_release():
    meta = Meta(category="MUSIC", music_discogs_master_id="45", music_release={"external_ids": {"discogs_release": "123"}})

    assert upload_history.external_ids(meta) == {"discogs_release": "123"}


def test_confirmed_xxx_metadata_ids_are_reused(tmp_path):
    release = _release(tmp_path, "Fictional.Studio.26.01.02.Fictional.Scene.XXX")
    meta = _confirm(Meta(path=str(release), category="XXX", tpdb_id="scenes/00000000-0000-4000-8000-000000000001", blvckout_id="4242"))
    assert upload_history.remember_release(meta) is True

    loaded = _load(release)
    loaded.category = "XXX"
    applied = upload_history.apply_saved_ids(loaded)

    assert (loaded.tpdb_manual, loaded.blvckout_manual) == ("scenes/00000000-0000-4000-8000-000000000001", "4242")
    assert applied == ["ThePornDB scenes/00000000-0000-4000-8000-000000000001", "BLVCKOUT 4242"]



def test_a_confirmed_xxx_category_is_restored_before_preparation(tmp_path):
    release = _release(tmp_path, "clip_0001")
    meta = _confirm(Meta(path=str(release), category="XXX", tpdb_id="scenes/1"))
    assert upload_history.remember_release(meta) is True

    # Category detection leaves a plain video without a category until the metadata search.
    restored = _load(release)
    upload_history.apply_saved_ids(restored)
    assert (restored.category, restored.tpdb_manual) == ("XXX", "scenes/1")

    chosen = _load(release, manual_category="MOVIE")
    upload_history.apply_saved_ids(chosen)
    assert chosen.category == ""

    skipped = _load(release, no_saved_ids=True)
    upload_history.apply_saved_ids(skipped)
    assert skipped.category == ""



def test_a_given_id_keeps_the_saved_xxx_category_from_being_restored(tmp_path):
    release = _release(tmp_path, "clip_0001")
    assert upload_history.remember_release(_confirm(Meta(path=str(release), category="XXX", tpdb_id="scenes/1"))) is True

    unset = _load(release, imdb_manual="tt0000001")
    upload_history.apply_saved_ids(unset)
    guessed = _load(release, imdb_manual="tt0000001", category="MOVIE")
    upload_history.apply_saved_ids(guessed)

    # The saved IDs are not reused, so neither is the category they were confirmed with.
    assert (unset.category, unset.tpdb_manual) == ("", None)
    assert (guessed.category, guessed.tpdb_manual) == ("MOVIE", None)
