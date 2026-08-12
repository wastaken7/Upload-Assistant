# ruff: noqa: S101

import pytest

from src.prep_helpers import _normalize_search_year


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (2013, "2013"),
        ("2013", "2013"),
        ([2013, 2021], "2013"),
        ("[2013, 2021]", "2013"),
        ("not a year", None),
    ],
)
def test_normalize_search_year_uses_the_first_valid_year(value: object, expected: str | None) -> None:
    assert _normalize_search_year(value) == expected
