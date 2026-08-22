from types import SimpleNamespace

from src.trackers.bjshare import BJShare
from src.trackers.common import Common


def test_get_titles_reorders_legacy_audiobook_series_title():
    tracker = object.__new__(BJShare)
    tracker.common = Common({})
    meta = SimpleNamespace(
        category="BOOK",
        title="História 4 de Reinações de Narizinho",
        book_series="O Casamento de Narizinho",
        book_series_index="",
    )

    assert tracker.get_titles(meta) == ("Reinações de Narizinho: O Casamento de Narizinho - Vol. 04", "")  # noqa: S101


def test_get_titles_reorders_legacy_title_with_book_prefix():
    tracker = object.__new__(BJShare)
    tracker.common = Common({})
    meta = SimpleNamespace(
        category="BOOK",
        title="O Casamento de Narizinho: História 4 de Reinações de Narizinho",
        book_series="",
        book_series_index="",
    )

    assert tracker.get_titles(meta) == ("Reinações de Narizinho: O Casamento de Narizinho - Vol. 04", "")  # noqa: S101


def test_get_titles_prefers_localized_legacy_series_over_api_series():
    tracker = object.__new__(BJShare)
    tracker.common = Common({})
    meta = SimpleNamespace(
        category="BOOK",
        title="O gato Félix: História 6 de Reinações de Narizinho",
        book_series="The Adventures of Lucia Little Nose",
        book_series_index="6",
    )

    assert tracker.get_titles(meta) == ("Reinações de Narizinho: O Gato Félix - Vol. 06", "")  # noqa: S101


def test_get_titles_keeps_regular_book_title_format():
    tracker = object.__new__(BJShare)
    tracker.common = Common({})
    meta = SimpleNamespace(
        category="BOOK",
        title="O Hobbit",
        book_series="Terra-media",
        book_series_index="1",
    )

    assert tracker.get_titles(meta) == ("Terra-Media: O Hobbit - Vol. 01", "")  # noqa: S101
