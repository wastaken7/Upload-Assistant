from pathlib import Path

import web_ui.server as server


def test_load_config_accepts_user_owned_runtime_path(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    config_path = state_dir / "data" / "config.py"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("config = {'DEFAULT': {'screens': 6}}\n", encoding="utf-8")
    monkeypatch.setattr(server, "STATE_DIR", state_dir)

    assert server._load_config_from_file(config_path) == {"DEFAULT": {"screens": 6}}


def test_load_config_accepts_python_files_beneath_both_data_directories(tmp_path: Path, monkeypatch) -> None:
    code_dir = tmp_path / "checkout"
    state_dir = tmp_path / "state"
    repository_path = code_dir / "data" / "nested" / "repository_config.py"
    runtime_path = state_dir / "data" / "nested" / "runtime_config.py"
    for path in (repository_path, runtime_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("config = {'DEFAULT': {}}\n", encoding="utf-8")
    monkeypatch.setattr(server, "CODE_DIR", code_dir)
    monkeypatch.setattr(server, "STATE_DIR", state_dir)

    assert server._load_config_from_file(repository_path) == {"DEFAULT": {}}
    assert server._load_config_from_file(runtime_path) == {"DEFAULT": {}}


def test_load_config_rejects_unrelated_python_file(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    unrelated_path = tmp_path / "config.py"
    unrelated_path.write_text("config = {'DEFAULT': {}}\n", encoding="utf-8")
    monkeypatch.setattr(server, "STATE_DIR", state_dir)

    assert server._load_config_from_file(unrelated_path) is None


def test_load_config_rejects_non_python_file_inside_runtime_data(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    config_path = state_dir / "data" / "config.txt"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("config = {'DEFAULT': {}}\n", encoding="utf-8")
    monkeypatch.setattr(server, "STATE_DIR", state_dir)

    assert server._load_config_from_file(config_path) is None
