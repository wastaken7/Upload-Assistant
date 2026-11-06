"""Game category and platform detection from file types and names."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.meta import Meta
from src.prep_game import clean_game_search_title, detect_platform_from_files, map_to_clean_code
from src.prep_helpers import detect_disc_and_category


def test_nup_file_is_detected_as_game(tmp_path):
    game = tmp_path / "Example Quest [0400000000000000][v0].nup"
    game.write_bytes(b"game package")
    meta = Meta(path=str(game))
    prep = SimpleNamespace(disc_info_manager=SimpleNamespace(get_disc=AsyncMock(return_value=("", str(game), {}, []))))

    asyncio.run(detect_disc_and_category(prep, meta))

    assert meta.category == "GAME"


@pytest.mark.parametrize("alias", ["switch2", "ns2"])
def test_switch2_platform_arg_is_accepted(alias):
    from src.args import Args

    meta, _, _ = Args({"DEFAULT": {"screens": 1}}).parse(["example.nup", "--platform", alias], Meta())

    assert meta.platform == "SWITCH2"


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        (["Example Quest/Example Quest.nup"], "SWITCH2"),
        (["Example Quest/Example Quest.nup", "Example Quest/Example Quest Update.nsp"], "SWITCH2"),
        (["Example Quest/Example Quest.nsp"], "SWITCH"),
        (["Example Quest/Example Quest.xci"], "SWITCH"),
    ],
)
def test_platform_is_detected_from_file_extension(files, expected):
    assert asyncio.run(detect_platform_from_files(files)) == expected


@pytest.mark.parametrize("name", ["Example.Quest.NSW2-GROUP", "Example Quest [Switch 2]", "Example_Quest_Switch2"])
def test_switch2_tag_wins_over_shared_switch_extensions(name):
    assert asyncio.run(detect_platform_from_files([f"{name}/Example Quest.nsp"], name)) == "SWITCH2"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Example.Quest.NSW2-GROUP", "SWITCH2"),
        ("Example Quest Switch 2-GROUP", "SWITCH2"),
        ("Example.Quest.Switch2-GROUP", "SWITCH2"),
        ("Example.Quest.NSW-GROUP", "SWITCH"),
        ("Example Quest Switch-GROUP", "SWITCH"),
    ],
)
def test_platform_is_detected_from_release_name(name, expected):
    assert asyncio.run(detect_platform_from_files([], name)) == expected


@pytest.mark.parametrize(
    ("platform_name", "expected"),
    [
        ("Nintendo Switch 2", "SWITCH2"),
        ("SWITCH2", "SWITCH2"),
        ("Nintendo Switch", "SWITCH"),
        ("switch", "SWITCH"),
    ],
)
def test_platform_names_map_to_clean_codes(platform_name, expected):
    assert map_to_clean_code(platform_name) == expected


def test_switch2_tag_is_removed_from_search_title():
    assert clean_game_search_title("Example Quest NSW2") == "Example Quest"
    assert clean_game_search_title("Example Quest Switch 2") == "Example Quest"
