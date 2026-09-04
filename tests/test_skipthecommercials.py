import asyncio

import pytest

from src.meta import Meta
from src.trackers.UNIT3D.skipthecommercials import SkipTheCommercials


@pytest.fixture
def tracker() -> SkipTheCommercials:
    return SkipTheCommercials({"DEFAULT": {}, "TRACKERS": {"SKIPTHECOMMERCIALS": {}}})


@pytest.mark.parametrize(
    "meta",
    [
        Meta(category="TV"),
        Meta(category="MOVIE", genres=["Documentary"]),
        Meta(category="MOVIE", keywords=["documentary"]),
        Meta(category="MOVIE", combined_genres="History, Documentary"),
        Meta(category="MOVIE", combined_genres=["Documentaries"]),
    ],
)
def test_skipthecommercials_allows_tv_and_documentary_movies(tracker: SkipTheCommercials, meta: Meta) -> None:
    assert asyncio.run(tracker.get_additional_checks(meta)) is True  # noqa: S101


@pytest.mark.parametrize(
    "meta",
    [
        Meta(category="MOVIE", genres=["Action", "Drama"], unattended=True),
        Meta(category="MOVIE", keywords=["documentary filmmaker"], unattended=True),
        Meta(category="MUSIC", genres=["Documentary"], unattended=True),
    ],
)
def test_skipthecommercials_rejects_non_documentary_movies_and_other_categories(tracker: SkipTheCommercials, meta: Meta) -> None:
    assert asyncio.run(tracker.get_additional_checks(meta)) is False  # noqa: S101
