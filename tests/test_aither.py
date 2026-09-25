# ruff: noqa: S101
import asyncio
from unittest.mock import AsyncMock

import pytest

from src.meta import Meta
from src.sports import detect_sports
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


@pytest.mark.asyncio
@pytest.mark.parametrize("episode,tv_pack", [(0, True), (3, False)])
@pytest.mark.parametrize("sports_event", [False, True])
async def test_aither_upload_category_and_tv_fields_agree(monkeypatch, episode, tv_pack, sports_event):
    tracker = Aither({"DEFAULT": {}, "TRACKERS": {"AITHER": {}}})
    title = "UFC 123 Example Event" if sports_event else "Example Sports Family"
    meta = Meta(
        category="TV", title=title, name=f"{title} S01 1080p WEB-DL-GROUP",
        genres=["Reality", "Sport"], keywords=["baseball"],
        season_int=1, episode_int=episode, tv_pack=tv_pack,
        language_checked=True,
    )
    meta.is_sports = detect_sports(meta)
    for method in ("get_description", "get_mediainfo", "get_bdinfo"):
        monkeypatch.setattr(tracker, method, AsyncMock(return_value={}))

    data = await tracker.get_data(meta)

    assert data["category_id"] == ("9" if sports_event else "2")
    if sports_event:
        assert "season_number" not in data
        assert "episode_number" not in data
    else:
        assert data["season_number"] == "1"
        assert data["episode_number"] == str(episode)
    assert (meta.category, meta.season_int, meta.episode_int) == ("TV", 1, episode)


@pytest.mark.asyncio
@pytest.mark.parametrize("category,is_sports", [("MOVIE", False), ("MOVIE", True), ("SPORTS", False)])
async def test_aither_non_tv_categories_omit_tv_fields(category, is_sports):
    tracker = Aither({"DEFAULT": {}, "TRACKERS": {"AITHER": {}}})
    meta = Meta(category=category, is_sports=is_sports, season_int=1, episode_int=3)

    assert await tracker.get_season_number(meta) == {}
    assert await tracker.get_episode_number(meta) == {}
def test_aither_expands_multiple_audio_language_from_mediainfo() -> None:
    meta = Meta(
        name="Synthetic Feature 2024 1080p WEB-DL AAC 2.0 H.264-TESTGROUP",
        resolution="1080p",
        audio_languages=["Multiple"],
        language_checked=True,
    )

    assert _name(meta) == "Synthetic Feature 2024 MULTIPLE LANGUAGES 1080p WEB-DL AAC 2.0 H.264-TESTGROUP"


def test_aither_expands_existing_multiple_tag_without_duplication() -> None:
    meta = Meta(
        name="Synthetic Feature 2024 MULTIPLE 1080p WEB-DL AAC 2.0 H.264-TESTGROUP",
        resolution="1080p",
        audio_languages=["Multiple"],
        language_checked=True,
    )

    assert _name(meta) == "Synthetic Feature 2024 MULTIPLE LANGUAGES 1080p WEB-DL AAC 2.0 H.264-TESTGROUP"


def test_aither_preserves_existing_multiple_languages_tag() -> None:
    meta = Meta(
        name="Imaginary Short 2024 MULTIPLE LANGUAGES 1080p WEB-DL AAC 2.0 H.264-TESTGROUP",
        resolution="1080p",
        audio_languages=["Multiple languages"],
        language_checked=True,
    )

    assert _name(meta) == "Imaginary Short 2024 MULTIPLE LANGUAGES 1080p WEB-DL AAC 2.0 H.264-TESTGROUP"


def test_aither_preserves_other_language_and_release_group() -> None:
    meta = Meta(
        name="Synthetic Feature 2024 1080p WEB-DL-TESTMULTiPLY",
        resolution="1080p",
        audio_languages=["French"],
        language_checked=True,
    )

    assert _name(meta) == "Synthetic Feature 2024 FRENCH 1080p WEB-DL-TESTMULTiPLY"


def test_aither_normalizes_mixed_case_language_label_without_duplication() -> None:
    meta = Meta(
        name="Synthetic Feature 2024 Multiple 1080p WEB-DL-TESTGROUP",
        resolution="1080p",
        audio_languages=["Multiple"],
        language_checked=True,
    )

    assert _name(meta) == "Synthetic Feature 2024 MULTIPLE LANGUAGES 1080p WEB-DL-TESTGROUP"


def test_aither_preserves_multiple_in_title_and_release_group() -> None:
    meta = Meta(
        name="MULTIPLE Synthetic Feature 2024 1080p WEB-DL-MULTIPLE",
        resolution="1080p",
        audio_languages=["Multiple"],
        language_checked=True,
    )

    assert _name(meta) == "MULTIPLE Synthetic Feature 2024 MULTIPLE LANGUAGES 1080p WEB-DL-MULTIPLE"


def test_aither_preserves_release_group_when_english_audio_skips_label() -> None:
    meta = Meta(
        name="Synthetic Feature 2024 1080p WEB-DL-MULTIPLE",
        resolution="1080p",
        audio_languages=["English"],
        language_checked=True,
    )

    assert _name(meta) == "Synthetic Feature 2024 1080p WEB-DL-MULTIPLE"
