# ruff: noqa: S101
import asyncio

from src.meta import Meta
from src.trackers.UNIT3D.aither import Aither


def _name(meta: Meta) -> str:
    config = {"DEFAULT": {}, "TRACKERS": {"AITHER": {}}}
    return asyncio.run(Aither(config).get_name(meta))["name"]


def _category(meta: Meta, **kwargs: object) -> dict[str, str]:
    config = {"DEFAULT": {}, "TRACKERS": {"AITHER": {}}}
    return asyncio.run(Aither(config).get_category_id(meta, **kwargs))


def test_aither_uses_sports_category_for_detected_sports() -> None:
    assert _category(Meta(category="MOVIE", is_sports=True)) == {"category_id": "9"}
    assert _category(Meta(category="TV", is_sports=True)) == {"category_id": "9"}


def test_aither_preserves_regular_categories() -> None:
    assert _category(Meta(category="MOVIE")) == {"category_id": "1"}
    assert _category(Meta(category="TV")) == {"category_id": "2"}


def test_aither_exposes_sports_category_mapping() -> None:
    assert _category(Meta(), mapping_only=True)["SPORTS"] == "9"
    assert _category(Meta(), reverse=True)["9"] == "SPORTS"


def test_aither_preserves_space_before_aka_when_tv_year_is_omitted() -> None:
    meta = Meta(
        category="TV",
        year=2024,
        search_year="",
        name="Example Show AKA Alternate Show Title S17 1080p WEB-DL",
        aka="AKA Alternate Show Title",
        language_checked=True,
    )

    assert _name(meta) == "Example Show AKA Alternate Show Title S17 1080p WEB-DL"


def test_aither_moves_aka_before_a_present_year() -> None:
    meta = Meta(
        category="MOVIE",
        year=2024,
        name="Example Movie 2024 AKA Alternate Movie Title 1080p Blu-ray",
        aka="AKA Alternate Movie Title",
        language_checked=True,
    )

    assert _name(meta) == "Example Movie AKA Alternate Movie Title 2024 1080p Blu-ray"
