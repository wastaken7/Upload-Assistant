import json
import shutil
from pathlib import Path

import pytest

import web_ui.server as server
from src.get_desc import DescriptionBuilder
from src.meta import Meta


def test_copied_example_documents_groups_without_enabling_them(tmp_path, monkeypatch):
    example_path = server.CODE_DIR / "data" / "example_config.py"
    original_example = example_path.read_bytes()
    config_path = tmp_path / "data" / "config.py"
    config_path.parent.mkdir()
    monkeypatch.setattr(server, "STATE_DIR", tmp_path)

    shutil.copy2(example_path, config_path)

    example = server._load_config_from_file(example_path)
    saved = server._load_config_from_file(config_path)
    assert saved == example
    assert saved["DEFAULT"]["tag_overrides"] == {}
    assert example_path.read_bytes() == original_example
    generated_source = config_path.read_text(encoding="utf-8")
    assert '# "MyAwesomeGroupTag": {' in generated_source
    assert "# Override description text fields for specific release groups." in generated_source
    assert "# Per-tracker tag_overrides take precedence over these DEFAULT overrides." in generated_source
    assert "# Set to True to display a notice when an update is available." in generated_source
    items = server._build_config_items(example["DEFAULT"], saved["DEFAULT"], {}, {}, ["DEFAULT"])
    assert next(item for item in items if item["key"] == "tag_overrides")["value"] == {}


def test_saved_sample_named_group_remains_editable():
    user = {"tag_overrides": {"MyAwesomeGroupTag": {"custom_signature": "saved text"}}}
    items = server._build_config_items({"tag_overrides": {}}, user, {}, {}, ["DEFAULT"])

    assert items[0]["value"] == user["tag_overrides"]


@pytest.fixture
def config_files(tmp_path: Path, monkeypatch):
    code_dir = tmp_path / "checkout"
    state_dir = tmp_path / "state"
    example_path = code_dir / "data" / "example_config.py"
    config_path = state_dir / "data" / "config.py"
    example = {
        "DEFAULT": {"tag_overrides": {"SampleGroup": {"custom_signature": "example"}}},
        "TRACKERS": {"AITHER": {"api_key": ""}},
    }
    user = {
        "DEFAULT": {"screens": 6, "screenshot_header": "inherited screenshots"},
        "TRACKERS": {"AITHER": {"api_key": "test-only-key"}},
    }
    for path, config in ((example_path, example), (config_path, user)):
        path.parent.mkdir(parents=True)
        path.write_text(f"config = {config!r}\n", encoding="utf-8")
    monkeypatch.setattr(server, "CODE_DIR", code_dir)
    monkeypatch.setattr(server, "STATE_DIR", state_dir)
    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_verify_same_origin", lambda: True)
    monkeypatch.setattr(server, "_write_audit_log", lambda *args, **kwargs: None)
    return example_path, config_path


def update(path, value):
    with server.app.test_request_context("/api/config_update", method="POST", json={"path": path, "value": value}):
        result = server.config_update()
        response, status = result if isinstance(result, tuple) else (result, 200)
        return response.get_json(), status


@pytest.mark.parametrize("user", [{}, {"tag_overrides": {}}, {"tag_overrides": {"RealGroup": {"custom_signature": "saved"}}}])
def test_metadata_uses_only_saved_groups(user):
    example = {"tag_overrides": {"SampleGroup": {"custom_signature": "example"}}}
    items = server._build_config_items(example, user, {}, {}, ["DEFAULT"])

    assert items[0]["value"] == user.get("tag_overrides", {})
    assert items[0]["example_value"] == {}
    assert items[0]["children"] == []
    assert {field["key"] for field in items[0]["override_fields"]} == {
        "custom_description_header", "screenshot_header", "disc_menu_header", "audio_spectrogram_header",
        "dynamic_hdr_plot_header", "tonemapped_header", "custom_signature",
    }


def test_tracker_metadata_exposes_editor_without_example_groups():
    items = server._build_config_items({"api_key": ""}, {}, {}, {}, ["TRACKERS", "AITHER"])
    group_item = next(item for item in items if item["key"] == "tag_overrides")

    assert group_item["value"] == {}
    assert group_item["override_fields"]
    assert group_item["source"] == "example"


@pytest.mark.parametrize("path", [["DEFAULT", "tag_overrides"], ["TRACKERS", "AITHER", "tag_overrides"]])
def test_create_edit_rename_and_remove_round_trip(config_files, path):
    example_path, config_path = config_files
    original_example = example_path.read_bytes()
    fields = {
        "custom_signature": "[b]Grüppe[/b]\nSecond line with 'quotes' and \\slashes",
        "disc_menu_header": "",
        "screenshot_header": None,
        "future_text_field": "preserve existing fields",
    }
    for groups in ({"CustomGroup": {}}, {"CustomGroup": fields}, {"RenamedGroup": fields}, {}):
        result, status = update(path, json.dumps(groups))
        assert status == 200, result
        saved = server._load_config_from_file(config_path)
        assert server._get_nested_value(saved, path) == groups
        assert saved["DEFAULT"]["screens"] == 6
        assert saved["TRACKERS"]["AITHER"]["api_key"] == "test-only-key"
        if groups and next(iter(groups.values())):
            builder = DescriptionBuilder("AITHER", saved)
            meta = Meta({"tag": "-" + next(iter(groups)).lower()})
            assert builder._get_str_config("custom_signature", "fallback", meta) == fields["custom_signature"]
            assert builder._get_str_config("disc_menu_header", "fallback", meta) == ""
            assert builder._get_str_config("screenshot_header", "fallback", meta) == "inherited screenshots"
    assert example_path.read_bytes() == original_example


@pytest.mark.parametrize("value", [
    "{invalid json", [], {"Group": []}, {"Group": {"custom_signature": 12}},
    {"": {}}, {"---": {}}, {"Bad\nName": {}}, {"Group": {}, "-gRoUp": {}}, {"Straße": {}, "STRASSE": {}},
])
def test_invalid_maps_do_not_modify_config(config_files, value):
    _, config_path = config_files
    original = config_path.read_bytes()

    result, status = update(["DEFAULT", "tag_overrides"], value)

    assert status == 400
    assert result["success"] is False
    assert config_path.read_bytes() == original


def test_unknown_tracker_scope_does_not_modify_config(config_files):
    _, config_path = config_files
    original = config_path.read_bytes()

    _, status = update(["TRACKERS", "UNKNOWN", "tag_overrides"], {"Group": {}})

    assert status == 400
    assert config_path.read_bytes() == original


@pytest.mark.parametrize("guard,status", [("_is_authenticated", 401), ("_verify_csrf_header", 403), ("_verify_same_origin", 403)])
def test_updates_require_authenticated_same_origin_session(config_files, monkeypatch, guard, status):
    _, config_path = config_files
    original = config_path.read_bytes()
    monkeypatch.setattr(server, guard, lambda: False)

    _, actual_status = update(["DEFAULT", "tag_overrides"], {"Group": {}})

    assert actual_status == status
    assert config_path.read_bytes() == original
