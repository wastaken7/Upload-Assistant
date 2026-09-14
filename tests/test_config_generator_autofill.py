"""Regression tests for config-generator tracker key autofill."""
# ruff: noqa: S101

import ast
import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

EXAMPLE_CONFIG_PATH = Path(__file__).parents[1] / "data" / "example_config.py"


def load_example_config() -> dict:
    tree = ast.parse(EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8"), filename=str(EXAMPLE_CONFIG_PATH))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "config":
            value = ast.literal_eval(node.value)
            assert isinstance(value, dict)
            return value
    raise AssertionError("data/example_config.py must define config as a literal dictionary")


@pytest.fixture(scope="module")
def config_generator_module():
    path = Path(__file__).parents[1] / "config-generator.py"
    spec = importlib.util.spec_from_file_location("config_generator", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_autofill_missing_keys_backfills_tracker_anon(config_generator_module) -> None:
    example = load_example_config()
    user = {
        "TRACKERS": {
            "SEEDPOOL": {"api_key": "key"},
            "TORRENTHR": {"api_key": "key"},
        },
    }

    config_generator_module.autofill_missing_keys(user, deepcopy(example))

    for tracker in ("SEEDPOOL", "TORRENTHR"):
        assert user["TRACKERS"][tracker]["anon"] == example["TRACKERS"][tracker]["anon"]
