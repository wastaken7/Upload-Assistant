"""Regression tests for XXX release naming."""

import asyncio

from src.get_name import NameManager
from src.meta import Meta


def test_xxx_name_preserves_release_and_only_replaces_dots():
    release_name = "OnlyFans.2026.19yo.Lilibet.Saunders.Fucks.Lucky.Older.Fan.Big.Naturals.XXX.MP4-P0RNL0V3RSD"
    meta = Meta(category="XXX", basename_no_ext=release_name, tag="-P0RNL0V3RSD")

    name_notag, name, clean_name, potential_missing = asyncio.run(NameManager({}).get_name(meta))

    expected = "OnlyFans 2026 19yo Lilibet Saunders Fucks Lucky Older Fan Big Naturals XXX MP4-P0RNL0V3RSD"
    assert name_notag == expected
    assert name == expected
    assert clean_name == expected
    assert potential_missing == []


def test_xxx_name_appends_a_tag_not_already_in_the_release_name():
    meta = Meta(category="XXX", basename_no_ext="OnlyFans.2026.Clip.XXX.MP4", tag="-CUSTOM")

    _name_notag, name, _clean_name, _potential_missing = asyncio.run(NameManager({}).get_name(meta))

    assert name == "OnlyFans 2026 Clip XXX MP4-CUSTOM"


def test_manual_name_override_is_used_without_automatic_tagging():
    meta = Meta(category="XXX", basename_no_ext="ignored", tag="-AUTO", manual_name="Custom.Release.Name")

    name_notag, name, clean_name, potential_missing = asyncio.run(NameManager({}).get_name(meta))

    assert name_notag == "Custom.Release.Name"
    assert name == "Custom.Release.Name"
    assert clean_name == "Custom.Release.Name"
    assert potential_missing == []
