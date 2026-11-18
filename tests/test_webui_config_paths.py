from pathlib import Path

import web_ui.argument_presets as webui_argument_presets
import web_ui.config_store as webui_config_store
import web_ui.context as webui_context


def test_load_config_accepts_user_owned_runtime_path(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    config_path = state_dir / "data" / "config.py"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("config = {'DEFAULT': {'screens': 6}}\n", encoding="utf-8")
    monkeypatch.setattr(webui_context, "STATE_DIR", state_dir)

    assert webui_config_store._load_config_from_file(config_path) == {"DEFAULT": {"screens": 6}}


def test_load_config_accepts_python_files_beneath_both_data_directories(tmp_path: Path, monkeypatch) -> None:
    code_dir = tmp_path / "checkout"
    state_dir = tmp_path / "state"
    repository_path = code_dir / "data" / "nested" / "repository_config.py"
    runtime_path = state_dir / "data" / "nested" / "runtime_config.py"
    for path in (repository_path, runtime_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("config = {'DEFAULT': {}}\n", encoding="utf-8")
    monkeypatch.setattr(webui_context, "CODE_DIR", code_dir)
    monkeypatch.setattr(webui_context, "STATE_DIR", state_dir)

    assert webui_config_store._load_config_from_file(repository_path) == {"DEFAULT": {}}
    assert webui_config_store._load_config_from_file(runtime_path) == {"DEFAULT": {}}


def test_load_config_rejects_unrelated_python_file(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    unrelated_path = tmp_path / "config.py"
    unrelated_path.write_text("config = {'DEFAULT': {}}\n", encoding="utf-8")
    monkeypatch.setattr(webui_context, "STATE_DIR", state_dir)

    assert webui_config_store._load_config_from_file(unrelated_path) is None


def test_load_config_rejects_non_python_file_inside_runtime_data(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    config_path = state_dir / "data" / "config.txt"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("config = {'DEFAULT': {}}\n", encoding="utf-8")
    monkeypatch.setattr(webui_context, "STATE_DIR", state_dir)

    assert webui_config_store._load_config_from_file(config_path) is None


def test_argument_presets_are_saved_in_user_owned_state(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / "state" / "data" / "argument_presets.json"
    legacy_path = tmp_path / "checkout" / "data" / "argument_presets.json"
    monkeypatch.setattr(webui_argument_presets, "ARGUMENT_PRESETS_PATH", state_path)
    monkeypatch.setattr(webui_argument_presets, "LEGACY_ARGUMENT_PRESETS_PATH", legacy_path)

    expected = [{"name": "Movie", "arguments": "--category MOVIE"}]
    webui_argument_presets._save_argument_presets(expected)

    assert state_path.exists()
    assert not legacy_path.exists()
    assert webui_argument_presets._load_argument_presets() == expected


def test_argument_presets_fall_back_to_legacy_checkout_file(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / "state" / "data" / "argument_presets.json"
    legacy_path = tmp_path / "checkout" / "data" / "argument_presets.json"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text('[{"name": "Legacy", "arguments": "--no-seed"}]\n', encoding="utf-8")
    monkeypatch.setattr(webui_argument_presets, "ARGUMENT_PRESETS_PATH", state_path)
    monkeypatch.setattr(webui_argument_presets, "LEGACY_ARGUMENT_PRESETS_PATH", legacy_path)

    assert webui_argument_presets._load_argument_presets() == [{"name": "Legacy", "arguments": "--no-seed"}]
