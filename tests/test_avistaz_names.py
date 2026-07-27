from types import SimpleNamespace

import pytest

from src.trackers.AVISTAZ import AZTrackerBase


def make_meta(**overrides):
    values = {
        "aka": "",
        "manual_episode_title": "",
        "daily_episode_title": "",
        "name": "Example 2024 1080p WEB-DL DD 5.1 H.264-GROUP",
        "has_encode_settings": False,
        "tag": "GROUP",
        "category": "MOVIE",
        "year": "2024",
        "no_year": False,
        "search_year": "",
        "season_int": 0,
        "imdb_info": {},
        "tv_pack": 0,
        "title": "Example",
        "season": "S01",
        "source": "",
        "audio": "",
        "type": "WEBDL",
        "is_disc": "",
        "region": "",
        "resolution": "1080p",
        "video_codec": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def tracker(name):
    return AZTrackerBase({"TRACKERS": {name: {}}}, name)


@pytest.mark.asyncio
async def test_cinemaz_title_rules_are_normalized():
    meta = make_meta(name="[Example] 2024 LIMITED Director's Cut Extended Cut 1080p Hybrid WEB-DL H.264-NOGRP", tag="NOGRP")

    name = await tracker("CINEMAZ").get_name(meta)

    assert name == "Example 2024 DC EXT 1080p HYBRID WEB-DL H.264-NoGroup"  # noqa: S101


@pytest.mark.asyncio
async def test_privatehd_removes_brackets_and_preserves_its_cut_terms():
    meta = make_meta(name="[Example] 2024 Criterion Collection Theatrical Cut 1080p WEB-DL H.264-GROUP")

    name = await tracker("PRIVATEHD").get_name(meta)

    assert name == "Example 2024 Theatrical 1080p WEB-DL H.264-GROUP"  # noqa: S101


@pytest.mark.asyncio
async def test_cinemaz_keeps_hybrid_when_no_quality_marker_exists():
    meta = make_meta(name="Example 2024 Hybrid WEB-DL H.264-GROUP")

    name = await tracker("CINEMAZ").get_name(meta)

    assert name == "Example 2024 Hybrid WEB-DL H.264-GROUP"  # noqa: S101


@pytest.mark.asyncio
async def test_cinemaz_places_hybrid_after_a_4k_quality_marker():
    meta = make_meta(name="Example 2024 Hybrid 4K WEB-DL H.264-GROUP")

    name = await tracker("CINEMAZ").get_name(meta)

    assert name == "Example 2024 4K HYBRID WEB-DL H.264-GROUP"  # noqa: S101
