from pathlib import Path

import pytest

import web_ui.server as server


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

    result, status = update(path, value, remove=True)
    assert status == 200, result
    assert server._load_config_from_file(config_path) == original
    # Retrying a removal is safe and never adds an empty override.
    assert update(path, value, remove=True)[1] == 200
    assert server._load_config_from_file(config_path) == original
    assert example_path.read_bytes() == example_bytes


def test_removing_one_override_preserves_another(tracker_config):
    config_path, _, _ = tracker_config
    assert update(["TRACKERS", "AITHER", "add_logo"], False)[1] == 200
    assert update(["TRACKERS", "AITHER", "multiScreens"], 0)[1] == 200
    assert update(["TRACKERS", "AITHER", "add_logo"], False, remove=True)[1] == 200
    tracker = server._load_config_from_file(config_path)["TRACKERS"]["AITHER"]
    assert "add_logo" not in tracker
    assert tracker["multiScreens"] == 0


def test_existing_override_missing_from_tracker_template_remains_editable(tracker_config):
    config_path, _, original = tracker_config
    original["TRACKERS"]["AITHER"]["custom_header"] = "Legacy header"
    config_path.write_text(f"config = {original!r}\n", encoding="utf-8")
    path = ["TRACKERS", "AITHER", "custom_header"]
    assert update(path, "Updated header")[1] == 200
    assert server._load_config_from_file(config_path)["TRACKERS"]["AITHER"]["custom_header"] == "Updated header"
    assert update(path, "Updated header", remove=True)[1] == 200
    del original["TRACKERS"]["AITHER"]["custom_header"]
    assert server._load_config_from_file(config_path) == original


@pytest.mark.parametrize("path", [["TRACKERS", "UNKNOWN", "add_logo"], ["TRACKERS", "AITHER", "unknown_key"]])
def test_unknown_override_paths_do_not_modify_config(tracker_config, path):
    config_path, _, _ = tracker_config
    original = config_path.read_bytes()
    assert update(path, False, remove=True)[1] == 400
    assert config_path.read_bytes() == original


@pytest.mark.parametrize("guard,status", [("_is_authenticated", 401), ("_verify_csrf_header", 403), ("_verify_same_origin", 403)])
def test_override_removal_requires_authenticated_same_origin_session(tracker_config, monkeypatch, guard, status):
    config_path, _, _ = tracker_config
    original = config_path.read_bytes()
    monkeypatch.setattr(server, guard, lambda: False)
    assert update(["TRACKERS", "AITHER", "add_logo"], False, remove=True)[1] == status
    assert config_path.read_bytes() == original
