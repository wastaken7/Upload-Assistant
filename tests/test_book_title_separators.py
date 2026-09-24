from unittest.mock import AsyncMock

import pytest

from src.book_extractors import normalize_book_title_separators
from src.book_prep import gather_book_prep
from src.meta import Meta


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Parte Um:Parte Dois:Parte Três", "Parte Um: Parte Dois – Parte Três"),  # noqa: RUF001
        ("Parte Um: Parte Dois", "Parte Um: Parte Dois"),
        ("Relógio: 10:30", "Relógio: 10:30"),
    ],
)
def test_book_title_separator_normalizer_handles_compact_colons_without_changing_times(title, expected):
    assert normalize_book_title_separators(title) == expected  # noqa: S101


@pytest.mark.asyncio
@pytest.mark.parametrize("audiobook", [False, True])
async def test_book_prep_normalizes_metadata_title_for_all_book_formats(tmp_path, monkeypatch, audiobook):
    monkeypatch.setattr("src.book_prep.get_audiobook_duration", AsyncMock(return_value=(0, "")))
    monkeypatch.setattr("src.book_prep.get_audiobook_bitrate", AsyncMock(return_value=None))
    original_title = "Título Exemplo: Subtítulo de teste: Parte final"
    meta = Meta(
        audiobook=audiobook,
        edit=True,
        mediainfo={"media": {"track": [{"@type": "General", "Title": original_title}]}},
    )

    await gather_book_prep(meta, "book.m4b" if audiobook else "book.epub", str(tmp_path))

    assert meta.category == "BOOK"  # noqa: S101
    assert meta.title == "Título Exemplo: Subtítulo de teste – Parte final"  # noqa: S101, RUF001


@pytest.mark.asyncio
async def test_book_prep_keeps_two_part_title_and_series_metadata(tmp_path):
    meta = Meta(title="Livro: Subtítulo", book_series="Série", edit=True)

    await gather_book_prep(meta, "book.epub", str(tmp_path))

    assert meta.title == "Livro: Subtítulo"  # noqa: S101
    assert meta.book_series == "Série"  # noqa: S101
