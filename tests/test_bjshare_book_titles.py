# ruff: noqa: RUF001
from types import SimpleNamespace

import pytest

from src.trackers.common import Common
from src.trackers.GAZELLE.bjshare import BJShare


def test_get_titles_reorders_legacy_audiobook_series_title():
    tracker = object.__new__(BJShare)
    tracker.common = Common({})
    meta = SimpleNamespace(
        category="BOOK",
        title="História 4 de Série Imaginária",
        book_series="Capítulo Exemplo",
        book_series_index="",
    )

    assert tracker.get_titles(meta) == ("Série Imaginária: Capítulo Exemplo - Vol. 04", "")  # noqa: S101


def test_get_titles_reorders_legacy_title_with_book_prefix():
    tracker = object.__new__(BJShare)
    tracker.common = Common({})
    meta = SimpleNamespace(
        category="BOOK",
        title="Capítulo Exemplo: História 4 de Série Imaginária",
        book_series="",
        book_series_index="",
    )

    assert tracker.get_titles(meta) == ("Série Imaginária: Capítulo Exemplo - Vol. 04", "")  # noqa: S101


def test_get_titles_prefers_localized_legacy_series_over_api_series():
    tracker = object.__new__(BJShare)
    tracker.common = Common({})
    meta = SimpleNamespace(
        category="BOOK",
        title="O capítulo fictício: História 6 de Série Imaginária",
        book_series="Unrelated Series",
        book_series_index="6",
    )

    assert tracker.get_titles(meta) == ("Série Imaginária: O Capítulo Fictício - Vol. 06", "")  # noqa: S101


def test_get_titles_keeps_regular_book_title_format():
    tracker = object.__new__(BJShare)
    tracker.common = Common({})
    meta = SimpleNamespace(
        category="BOOK",
        title="Livro Exemplo",
        book_series="Coleção imaginária",
        book_series_index="1",
    )

    assert tracker.get_titles(meta) == ("Coleção Imaginária: Livro Exemplo - Vol. 01", "")  # noqa: S101


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        (
            "Título Exemplo – Subtítulo de Teste: Parte Final",
            "Título Exemplo: Subtítulo de Teste – Parte Final",
        ),
        (
            "Título Exemplo: Subtítulo de Teste: Parte Final",
            "Título Exemplo: Subtítulo de Teste – Parte Final",
        ),
        (
            "Título Exemplo: Subtítulo de Teste – Parte Final",
            "Título Exemplo: Subtítulo de Teste – Parte Final",
        ),
        (
            "Título exemplo: Subtítulo de teste: Parte final",
            "Título Exemplo: Subtítulo de Teste – Parte Final",
        ),
    ],
)
def test_get_titles_uses_colon_then_dash_for_book_subtitles(title, expected):
    tracker = object.__new__(BJShare)
    tracker.common = Common({})
    meta = SimpleNamespace(category="BOOK", title=title, book_series="", book_series_index="")

    assert tracker.get_titles(meta) == (expected, "")  # noqa: S101
    assert meta.title == title  # noqa: S101


def test_get_titles_keeps_volume_suffix_after_subtitle_normalization():
    tracker = object.__new__(BJShare)
    tracker.common = Common({})
    meta = SimpleNamespace(category="BOOK", title="Livro: Subtítulo: Parte", book_series="Série", book_series_index="2")

    assert tracker.get_titles(meta) == ("Série: Livro – Subtítulo – Parte - Vol. 02", "")  # noqa: S101
