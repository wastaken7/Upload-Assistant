# ruff: noqa: S101

import asyncio

import pytest

from src.imdb import imdb_manager
from src.meta import Meta
from src.prep_helpers import _reject_invalid_automatic_imdb
from src.trackers.UNIT3D import UNIT3D


@pytest.mark.parametrize(
    ("filename", "title", "year", "imdb_id", "imdb_title", "imdb_year", "imdb_type"),
    [
        ("Nossa Mae era Atriz", "Our Mother was an Actress", 2023, 32345230, "157. Nossas mães", 2024, "podcastEpisode"),
        ("Rua Ataleia", "Ataléia Street", 2021, 6868820, "Rua Augusta", 2018, "tvSeries"),
    ],
)
def test_wrong_imdb_from_real_uploads_is_removed(filename, title, year, imdb_id, imdb_title, imdb_year, imdb_type):
    meta = Meta(
        category="MOVIE",
        filename=filename,
        title=title,
        year=year,
        imdb_id=imdb_id,
        imdb_tt=f"tt{imdb_id}",
        imdb=str(imdb_id),
        imdb_info={"imdbID": f"tt{imdb_id}", "title": imdb_title, "year": imdb_year, "type": imdb_type},
        aka=f"AKA {imdb_title}",
    )

    _reject_invalid_automatic_imdb(meta, filename)

    assert (meta.imdb_id, meta.imdb_tt, meta.imdb, meta.imdb_info, meta.aka, meta.no_imdb) == (0, "", "0", {}, "", True)
    assert asyncio.run(UNIT3D.get_imdb(None, meta)) == {"imdb": "0"}


def test_valid_automatic_imdb_is_kept():
    meta = Meta(category="MOVIE", filename="Rua Ataleia", title="Ataléia Street", year=2021, imdb_id=1234567)
    meta.imdb_info = {"imdbID": "tt1234567", "title": "Rua Ataléia", "year": 2021, "type": "short"}

    _reject_invalid_automatic_imdb(meta, meta.filename)

    assert meta.imdb_id == 1234567
    assert meta.no_imdb is False


def test_translated_title_is_accepted_when_tmdb_links_imdb():
    meta = Meta(category="MOVIE", filename="Outro Titulo", title="Completely Different Translation", year=2023, imdb_id=1234567, tmdb_imdb_id=1234567)
    meta.imdb_info = {"imdbID": "tt1234567", "title": "Original Foreign Title", "year": 2023, "type": "movie"}

    _reject_invalid_automatic_imdb(meta, meta.filename)

    assert meta.imdb_id == 1234567


def test_missing_imdb_details_are_not_used_automatically():
    meta = Meta(category="MOVIE", filename="Example", title="Example", year=2023, imdb_id=1234567, imdb_tt="tt1234567", imdb_info={})

    _reject_invalid_automatic_imdb(meta, meta.filename)

    assert (meta.imdb_id, meta.imdb_tt, meta.no_imdb) == (0, "", True)


def test_explicit_manual_imdb_is_preserved():
    meta = Meta(category="MOVIE", filename="Example", title="Example", year=2023, imdb_manual="tt1234567", imdb_id=1234567, imdb_info={})

    _reject_invalid_automatic_imdb(meta, meta.filename)

    assert meta.imdb_id == 1234567


class _Response:
    def __init__(self, candidates):
        self.candidates = candidates

    def raise_for_status(self):
        return None

    def json(self):
        return {"data": {"advancedTitleSearch": {"edges": [{"node": {"title": candidate}} for candidate in self.candidates]}}}


class _Client:
    def __init__(self, candidates):
        self.candidates = candidates

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, *_args, **_kwargs):
        return _Response(self.candidates)


def _candidate(imdb_id, title, year, title_type):
    return {"id": f"tt{imdb_id}", "titleText": {"text": title}, "releaseYear": {"year": year}, "titleType": {"text": title_type}}


def test_single_incompatible_search_result_is_not_selected(monkeypatch):
    monkeypatch.setattr("src.imdb.httpx.AsyncClient", lambda: _Client([_candidate(32345230, "157. Nossas mães", 2024, "Podcast Episode")]))

    result = asyncio.run(imdb_manager.search_imdb("Nossa Mae era Atriz", 2023, category="MOVIE", unattended=True))

    assert result == 0


def test_unattended_search_skips_wrong_first_result(monkeypatch):
    monkeypatch.setattr(
        "src.imdb.httpx.AsyncClient",
        lambda: _Client([_candidate(6868820, "Rua Augusta", 2018, "TV Series"), _candidate(1234567, "Rua Ataléia", 2021, "Short")]),
    )

    result = asyncio.run(imdb_manager.search_imdb("Rua Ataleia", 2021, category="MOVIE", unattended=True))

    assert result == 1234567


def test_quick_search_skips_wrong_first_result(monkeypatch):
    monkeypatch.setattr(
        "src.imdb.httpx.AsyncClient",
        lambda: _Client([_candidate(6868820, "Rua Augusta", 2018, "TV Series"), _candidate(1234567, "Rua Ataléia", 2021, "Short")]),
    )

    result = asyncio.run(imdb_manager.search_imdb("Rua Ataleia", 2021, category="MOVIE", quickie=True, unattended=True))

    assert result == 1234567


def test_attended_selection_marks_incompatible_id_as_manual(monkeypatch):
    monkeypatch.setattr("src.imdb.httpx.AsyncClient", lambda: _Client([_candidate(6868820, "Rua Augusta", 2018, "TV Series")]))

    async def select_first(*_args, **_kwargs):
        return "1"

    monkeypatch.setattr("src.imdb.prompt_in_thread", select_first)
    selected = []

    result = asyncio.run(imdb_manager.search_imdb("Rua Ataleia", 2021, category="MOVIE", on_manual_selection=selected.append))

    assert result == 6868820
    assert selected == [6868820]
