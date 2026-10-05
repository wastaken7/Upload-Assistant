from pathlib import Path

import pytest

import web_ui.server as server
from src.config_sync import sync_user_config
from src.get_desc import DescriptionBuilder
from src.meta import Meta


@pytest.fixture
def tracker_config(tmp_path: Path, monkeypatch):
    example = {
        "DEFAULT": {"add_logo": True, "multiScreens": 4, "custom_signature": "Default text"},
        "TRACKERS": {"AITHER": {"api_key": "", "add_logo": True, "multiScreens": 2, "custom_signature": ""}},
    }
    user = {
        "DEFAULT": example["DEFAULT"].copy(),
        "TRACKERS": {"AITHER": {"api_key": "test-key", "tag_overrides": {"Group": {"custom_signature": "Group text"}}}},
    }
    example_path = tmp_path / "code" / "data" / "example_config.py"
    config_path = tmp_path / "state" / "data" / "config.py"
    for path, config in ((example_path, example), (config_path, user)):
        path.parent.mkdir(parents=True)
        path.write_text(f"config = {config!r}\n", encoding="utf-8")
    monkeypatch.setattr(server, "CODE_DIR", example_path.parent.parent)
    monkeypatch.setattr(server, "STATE_DIR", config_path.parent.parent)
    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_verify_same_origin", lambda: True)
    monkeypatch.setattr(server, "_write_audit_log", lambda *args, **kwargs: None)
    return config_path, example_path, user


def update(path, value, remove=False):
    with server.app.test_request_context("/api/config_update", method="POST", json={"path": path, "value": value, "remove": remove}):
        result = server.config_update()
        response, status = result if isinstance(result, tuple) else (result, 200)
        return response.get_json(), status


@pytest.mark.parametrize("key,value", [("add_logo", False), ("multiScreens", 0), ("custom_signature", "")])
def test_individual_override_round_trip_preserves_falsy_values_and_inheritance(tracker_config, key, value):
    config_path, example_path, original = tracker_config
    example_bytes = example_path.read_bytes()
    path = ["TRACKERS", "AITHER", key]

    result, status = update(path, value)
    assert status == 200, result
    expected = {**original["TRACKERS"]["AITHER"], key: value}
    saved = server._load_config_from_file(config_path)
    assert saved["TRACKERS"]["AITHER"] == expected
    assert type(saved["TRACKERS"]["AITHER"][key]) is type(value)
    assert saved["DEFAULT"] == original["DEFAULT"]

    result, status = update(path, None)
    assert status == 200, result
    assert result["value"] is None
    expected[key] = None
    assert server._load_config_from_file(config_path)["TRACKERS"]["AITHER"] == expected
    # Retrying inheritance retains the key and never turns it into False, 0 or "".
    assert update(path, None)[1] == 200
    assert server._load_config_from_file(config_path)["TRACKERS"]["AITHER"] == expected
    sync_user_config(config_path, example_path)
    assert server._load_config_from_file(config_path)["TRACKERS"]["AITHER"][key] is None
    # Re-enabling also preserves explicit falsy values after synchronization.
    assert update(path, value)[1] == 200
    saved = server._load_config_from_file(config_path)
    assert saved["TRACKERS"]["AITHER"][key] == value
    assert type(saved["TRACKERS"]["AITHER"][key]) is type(value)
    assert example_path.read_bytes() == example_bytes


def test_legacy_removal_request_retains_inheritance_and_preserves_another_override(tracker_config):
    config_path, _, _ = tracker_config
    assert update(["TRACKERS", "AITHER", "add_logo"], False)[1] == 200
    assert update(["TRACKERS", "AITHER", "multiScreens"], 0)[1] == 200
    assert update(["TRACKERS", "AITHER", "add_logo"], False, remove=True)[1] == 200
    tracker = server._load_config_from_file(config_path)["TRACKERS"]["AITHER"]
    assert tracker["add_logo"] is None
    assert tracker["multiScreens"] == 0


def test_existing_override_missing_from_tracker_template_remains_editable(tracker_config):
    config_path, _, original = tracker_config
    original["TRACKERS"]["AITHER"]["custom_header"] = "Legacy header"
    config_path.write_text(f"config = {original!r}\n", encoding="utf-8")
    path = ["TRACKERS", "AITHER", "custom_header"]
    assert update(path, "Updated header")[1] == 200
    assert server._load_config_from_file(config_path)["TRACKERS"]["AITHER"]["custom_header"] == "Updated header"
    assert update(path, "Updated header", remove=True)[1] == 200
    original["TRACKERS"]["AITHER"]["custom_header"] = None
    assert server._load_config_from_file(config_path) == original
    assert update(path, "Re-enabled header")[1] == 200
    assert server._load_config_from_file(config_path)["TRACKERS"]["AITHER"]["custom_header"] == "Re-enabled header"


def set_overrides(enabled, tracker="AITHER"):
    with server.app.test_request_context("/api/config_set_tracker_overrides", method="POST", json={"tracker": tracker, "enabled": enabled}):
        result = server.config_set_tracker_overrides()
        response, status = result if isinstance(result, tuple) else (result, 200)
        return response.get_json(), status


def test_disable_save_sync_reload_keeps_keys_and_follows_default_changes(tracker_config):
    config_path, example_path, original = tracker_config
    keys = ("add_logo", "multiScreens", "custom_signature")
    assert set_overrides(True)[1] == 200
    # The current UI saves each disabled field as JSON null.
    for key in keys:
        assert update(["TRACKERS", "AITHER", key], None)[1] == 200

    # New general defaults are added while tracker options remain user-managed.
    example = server._load_config_from_file(example_path)
    example["DEFAULT"]["new_option"] = True
    example["TRACKERS"]["AITHER"]["new_option"] = True
    example_path.write_text(f"config = {example!r}\n", encoding="utf-8")
    result = sync_user_config(config_path, example_path)
    assert result.added_paths == ("DEFAULT.new_option",)
    assert not sync_user_config(config_path, example_path).changed

    saved = server._load_config_from_file(config_path)
    assert saved["DEFAULT"]["new_option"] is True
    assert saved["TRACKERS"]["AITHER"] == {
        **original["TRACKERS"]["AITHER"], **dict.fromkeys(keys),
    }
    items = server._build_config_items(example["TRACKERS"]["AITHER"], saved["TRACKERS"]["AITHER"], {}, {}, ["TRACKERS", "AITHER"])
    for item in items:
        if item["key"] in keys:
            assert item["source"] == "config"
            assert item["value"] is None

    for defaults in (
        original["DEFAULT"],
        {"add_logo": False, "multiScreens": 7, "custom_signature": "Changed global signature"},
    ):
        for key, value in defaults.items():
            assert update(["DEFAULT", key], value)[1] == 200
        assert not sync_user_config(config_path, example_path).changed
        builder = DescriptionBuilder("AITHER", server._load_config_from_file(config_path))
        assert builder._get_bool_config("add_logo") is defaults["add_logo"]
        assert builder._get_int_config("multiScreens") == defaults["multiScreens"]
        assert builder._get_str_config("custom_signature") == defaults["custom_signature"]
        assert builder._get_str_config("custom_signature", meta=Meta({"tag": "-Group"})) == "Group text"


def test_bulk_disable_keeps_inherited_keys_including_legacy_fields(tracker_config):
    config_path, example_path, original = tracker_config
    original["TRACKERS"]["AITHER"]["custom_header"] = "Legacy header"
    config_path.write_text(f"config = {original!r}\n", encoding="utf-8")
    assert set_overrides(True)[1] == 200
    assert set_overrides(False)[1] == 200
    expected = {
        **original["TRACKERS"]["AITHER"],
        **dict.fromkeys(("add_logo", "multiScreens", "custom_signature", "custom_header")),
    }
    assert server._load_config_from_file(config_path)["TRACKERS"]["AITHER"] == expected
    assert not sync_user_config(config_path, example_path).changed
    assert set_overrides(False)[1] == 200
    assert server._load_config_from_file(config_path)["TRACKERS"]["AITHER"] == expected


def test_bulk_disable_can_save_inheritance_for_an_unsaved_tracker(tracker_config):
    config_path, example_path, original = tracker_config
    config_path.write_text(f"config = {{'DEFAULT': {original['DEFAULT']!r}}}\n", encoding="utf-8")
    assert set_overrides(False)[1] == 200
    assert not sync_user_config(config_path, example_path).changed
    tracker = server._load_config_from_file(config_path)["TRACKERS"]["AITHER"]
    assert tracker == {"add_logo": None, "multiScreens": None, "custom_signature": None}


def test_inheritance_retains_the_setting_in_config_source(tracker_config):
    config_path, _, _ = tracker_config
    config_path.write_text(
        'config = {\n    "TRACKERS": {\n        "AITHER": {\n'
        '            "add_logo": True,\n        },\n    },\n}\n',
        encoding="utf-8",
    )
    assert update(["TRACKERS", "AITHER", "add_logo"], None)[1] == 200
    assert "'add_logo': None" in config_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", [["TRACKERS", "UNKNOWN", "add_logo"], ["TRACKERS", "AITHER", "unknown_key"]])
def test_unknown_override_paths_do_not_modify_config(tracker_config, path):
    config_path, _, _ = tracker_config
    original = config_path.read_bytes()
    assert update(path, False, remove=True)[1] == 400
    assert config_path.read_bytes() == original


@pytest.mark.parametrize("guard,status", [("_is_authenticated", 401), ("_verify_csrf_header", 403), ("_verify_same_origin", 403)])
def test_override_inheritance_requires_authenticated_same_origin_session(tracker_config, monkeypatch, guard, status):
    config_path, _, _ = tracker_config
    original = config_path.read_bytes()
    monkeypatch.setattr(server, guard, lambda: False)
    assert update(["TRACKERS", "AITHER", "add_logo"], None)[1] == status
    assert set_overrides(False)[1] == status
    assert config_path.read_bytes() == original
