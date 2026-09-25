"""CLI tracker aliases are limited to -tk/--trackers."""

# ruff: noqa: S101

import ast
from pathlib import Path

import pytest

from src.args import Args
from src.meta import Meta


@pytest.mark.parametrize("flag", ["-tk", "--trackers"])
def test_tracker_aliases_resolve_case_insensitively_with_canonical_names(tmp_path, flag):
    config = {
        "DEFAULT": {"screens": 1},
        "TRACKERS": {
            "CAPYBARABR": {"cli_alias": "cbr"},
            "BEYONDHD": {"cli_alias": "mybhd"},
        },
    }

    meta, _, _ = Args(config).parse([str(tmp_path), flag, "CBR,beyondhd,MyBHD"], Meta())

    assert meta.trackers == ["CAPYBARABR", "BEYONDHD", "BEYONDHD"]


def test_example_config_aliases_cover_all_trackers_and_are_unique(tmp_path):
    source = (Path(__file__).parents[1] / "data" / "example_config.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    example_config = ast.literal_eval(
        next(node.value for node in tree.body if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "config")
    )
    trackers = example_config["TRACKERS"]
    aliases = {name: options["cli_alias"] for name, options in trackers.items() if name != "default_trackers"}

    assert len(aliases) == len(trackers) - 1
    assert len({alias.upper() for alias in aliases.values()}) == len(aliases)
    assert aliases["CAPYBARABR"] == "CBR"
    assert aliases["BROADCASTHENET"] == "BTN"
    assert aliases["MANUAL"] == "MANUAL"

    meta, _, _ = Args({"DEFAULT": {"screens": 1}, "TRACKERS": trackers}).parse([str(tmp_path), "-tk", "cbr,btn"], Meta())
    assert meta.trackers == ["CAPYBARABR", "BROADCASTHENET"]


def test_alias_does_not_change_other_tracker_options_or_defaults(tmp_path):
    config = {
        "DEFAULT": {"screens": 1},
        "TRACKERS": {"default_trackers": "AITHER", "AITHER": {"cli_alias": "FOX"}},
    }

    meta, _, _ = Args(config).parse([str(tmp_path), "--trackers-remove", "FOX", "--tracker-id", "AITHER=123"], Meta())

    assert meta.trackers == []
    assert meta.trackers_remove == "FOX"
    assert meta.get_tracker_id("AITHER") == "123"
    assert config["TRACKERS"]["default_trackers"] == "AITHER"
    with pytest.raises(ValueError, match="supported tracker name"):
        Args(config).parse_tracker_id("FOX=123")


@pytest.mark.parametrize(
    "tracker_configs, message",
    [
        ({"AITHER": {"cli_alias": "X"}, "BEYONDHD": {"cli_alias": "x"}}, "configured for both"),
        ({"AITHER": {"cli_alias": "BEYONDHD"}}, "conflicts with a canonical tracker name"),
        ({"AITHER": {"cli_alias": "bhd"}}, "already selects BEYONDHD"),
        ({"AITHER": {"cli_alias": "two words"}}, "without spaces or commas"),
    ],
)
def test_conflicting_or_invalid_aliases_are_rejected_only_when_trackers_arg_is_used(tmp_path, capsys, tracker_configs, message):
    args = Args({"DEFAULT": {"screens": 1}, "TRACKERS": tracker_configs})

    args.parse([str(tmp_path)], Meta())
    with pytest.raises(SystemExit, match="2"):
        args.parse([str(tmp_path), "-tk", "AITHER"], Meta())
    assert message in capsys.readouterr().err
