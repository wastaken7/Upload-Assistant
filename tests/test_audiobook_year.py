# ruff: noqa: S101
from unittest.mock import AsyncMock

import pytest

from src.book_prep import gather_book_prep
from src.meta import Meta


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("release_name", "generic_year"),
    [
        ("Autor_Um-1889_Titulo_de_exemplo-2013-AUDIOBOOK-POR-2022-Grupo", 1889),
        ("Autora_Dois-Titulo_1914_de_exemplo-2013-AUDIOBOOK-POR-2023-Grupo", 1914),
    ],
)
async def test_audiobook_release_year_beats_title_and_recorded_year(tmp_path, monkeypatch, release_name, generic_year):
    monkeypatch.setattr("src.book_prep.get_audiobook_duration", AsyncMock(return_value=(0, "")))
    monkeypatch.setattr("src.book_prep.get_audiobook_bitrate", AsyncMock(return_value=None))
    meta = Meta(
        audiobook=True,
        basename_no_ext=release_name,
        year=generic_year,
        edit=True,
        mediainfo={"media": {"track": [{"@type": "General", "Recorded_Date": "2023"}]}},
    )

    await gather_book_prep(meta, f"{release_name}.m4b", str(tmp_path))

    assert meta.year == 2013
    assert meta.search_year == 2013


@pytest.mark.asyncio
async def test_audiobook_recorded_year_beats_generic_title_year(tmp_path, monkeypatch):
    monkeypatch.setattr("src.book_prep.get_audiobook_duration", AsyncMock(return_value=(0, "")))
    monkeypatch.setattr("src.book_prep.get_audiobook_bitrate", AsyncMock(return_value=None))
    meta = Meta(
        audiobook=True,
        basename_no_ext="Autor_Exemplo-Titulo_1914_de_exemplo-AUDIOBOOK",
        year=1914,
        edit=True,
        mediainfo={"media": {"track": [{"@type": "General", "Recorded_Date": "2023-08-15"}]}},
    )

    await gather_book_prep(meta, "book.m4b", str(tmp_path))

    assert meta.year == 2023
    assert meta.search_year == 2023


@pytest.mark.asyncio
async def test_audiobook_manual_year_beats_release_and_recorded_year(tmp_path, monkeypatch):
    monkeypatch.setattr("src.book_prep.get_audiobook_duration", AsyncMock(return_value=(0, "")))
    monkeypatch.setattr("src.book_prep.get_audiobook_bitrate", AsyncMock(return_value=None))
    meta = Meta(
        audiobook=True,
        basename_no_ext="Author-1889_Title-2013-AUDIOBOOK-POR-2023-Group",
        year=2010,
        manual_year=2010,
        edit=True,
        mediainfo={"media": {"track": [{"@type": "General", "Recorded_Date": "2023"}]}},
    )

    await gather_book_prep(meta, "book.m4b", str(tmp_path))

    assert meta.year == 2010
    assert meta.search_year == 2010


@pytest.mark.asyncio
async def test_audiobook_book_metadata_year_beats_release_year(tmp_path, monkeypatch):
    from src.google_books import google_books_manager
    from src.openlibrary import openlibrary_manager

    monkeypatch.setattr("src.book_prep.get_audiobook_duration", AsyncMock(return_value=(0, "")))
    monkeypatch.setattr("src.book_prep.get_audiobook_bitrate", AsyncMock(return_value=None))
    monkeypatch.setattr(google_books_manager, "search_by_isbn", AsyncMock(return_value={"year": 2012}))
    monkeypatch.setattr(openlibrary_manager, "search_by_isbn", AsyncMock(return_value={"year": 2011}))
    meta = Meta(
        audiobook=True,
        basename_no_ext="Author-1889_Title-2013-AUDIOBOOK-POR-2023-Group",
        isbn="9781234567890",
        year=1889,
        edit=True,
        mediainfo={"media": {"track": [{"@type": "General", "Recorded_Date": "2023"}]}},
    )

    await gather_book_prep(meta, "book.m4b", str(tmp_path))

    assert meta.year == 2012
    assert meta.search_year == 2012
