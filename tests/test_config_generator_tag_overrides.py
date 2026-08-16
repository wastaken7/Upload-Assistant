# ruff: noqa: S101

import builtins
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def config_generator_module():
    path = Path(__file__).parents[1] / "config-generator.py"
    spec = importlib.util.spec_from_file_location("config_generator", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validate_config_preserves_tracker_tag_overrides(config_generator_module, monkeypatch):
    config = {
        "DEFAULT": {},
        "TRACKERS": {
            "AITHER": {
                "api_key": "key",
                "tag_overrides": {"MyGroup": {"custom_signature": "signature"}},
            },
        },
    }
    example = {"DEFAULT": {}, "TRACKERS": {"AITHER": {"api_key": ""}}}

    monkeypatch.setattr(builtins, "input", lambda _prompt: pytest.fail("tag_overrides must not be treated as unexpected"))

    assert config_generator_module.validate_config(config, example) == config


def test_configure_default_section_keeps_tag_overrides_as_a_mapping(config_generator_module):
    existing = {"tag_overrides": {"MyGroup": {"custom_signature": "signature"}}}
    example = {"tag_overrides": {"MyAwesomeGroupTag": {"custom_signature": "example signature"}}}

    configured = config_generator_module.configure_default_section(existing, example, {})

    assert configured["tag_overrides"] == existing["tag_overrides"]
    assert configured["tag_overrides"] is not existing["tag_overrides"]


def test_configure_trackers_keeps_existing_tag_overrides(config_generator_module, monkeypatch):
    existing = {
        "default_trackers": "AITHER",
        "AITHER": {
            "api_key": "key",
            "tag_overrides": {"MyGroup": {"custom_signature": "signature"}},
        },
    }
    example = {"AITHER": {"api_key": ""}}

    monkeypatch.setattr(config_generator_module, "get_user_input", lambda *_args, **_kwargs: "AITHER")
    monkeypatch.setattr(builtins, "input", lambda _prompt: "y")

    configured = config_generator_module.configure_trackers(existing, example, {})

    assert configured["AITHER"]["tag_overrides"] == existing["AITHER"]["tag_overrides"]
    assert configured["AITHER"]["tag_overrides"] is not existing["AITHER"]["tag_overrides"]


def test_generator_writes_tag_override_comments(config_generator_module, monkeypatch, tmp_path):
    monkeypatch.setattr(config_generator_module, "ensure_data_dir", lambda: None)
    _example, comments = config_generator_module.read_example_config()
    output = tmp_path / "config.py"

    assert comments["DEFAULT.tag_overrides"] == [
        "# Override description text fields for specific release groups. Tags are matched",
        "# case-insensitively, with or without their leading hyphen.",
        "# Per-tracker tag_overrides take precedence over these DEFAULT overrides.",
    ]
    assert config_generator_module.generate_config_file(
        {"DEFAULT": {"tag_overrides": {"MyAwesomeGroupTag": {"custom_signature": "signature"}}}},
        output,
        comments,
    )

    content = output.read_text(encoding="utf-8")
    assert "        # Override description text fields for specific release groups. Tags are matched\n" in content
    assert '        # Per-tracker tag_overrides take precedence over these DEFAULT overrides.\n        "tag_overrides": {\n' in content
