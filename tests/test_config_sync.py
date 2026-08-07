# ruff: noqa: S101

import ast
from pathlib import Path

from src.config_sync import CONFIG_SCHEMA_VERSION, ensure_config_exists, find_obsolete_config_paths, sync_config_schema


def _write_config(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def _read_config(path: Path) -> dict[str, object]:
    assignment = ast.parse(path.read_text(encoding="utf-8")).body[0]
    return ast.literal_eval(assignment.value)


def test_ensure_config_exists_copies_the_example_once(tmp_path: Path) -> None:
    config_path = tmp_path / "data" / "config.py"
    example_path = tmp_path / "example_config.py"
    _write_config(example_path, "config = {'DEFAULT': {'value': True}}\n")

    assert ensure_config_exists(config_path, example_path) is True
    assert config_path.read_text(encoding="utf-8") == example_path.read_text(encoding="utf-8")
    assert ensure_config_exists(config_path, example_path) is False


def test_sync_adds_missing_defaults_and_preserves_comments(tmp_path: Path) -> None:
    config_path = tmp_path / "config.py"
    example_path = tmp_path / "example_config.py"
    _write_config(
        config_path,
        "config = {\n    # Keep this user comment\n    'DEFAULT': {'existing': True},\n    'TRACKERS': {},\n}\n",
    )
    _write_config(
        example_path,
        "config = {\n    'DEFAULT': {'config_schema_version': 1, 'existing': False, 'new_default': 42},\n"
        "    'TRACKERS': {'NEW': {'api_key': ''}},\n"
        "    'USENET': {'enabled': False},\n}\n",
    )

    added = sync_config_schema(config_path, example_path)

    assert set(added) == {"DEFAULT.config_schema_version", "DEFAULT.new_default", "TRACKERS.NEW", "USENET"}
    assert "# Keep this user comment" in config_path.read_text(encoding="utf-8")
    assert config_path.with_suffix(".py.bak").read_text(encoding="utf-8").startswith("config =")

    config = _read_config(config_path)
    assert config["DEFAULT"] == {"existing": True, "config_schema_version": CONFIG_SCHEMA_VERSION, "new_default": 42}
    assert config["TRACKERS"]["NEW"] == {"api_key": ""}
    assert config["USENET"] == {"enabled": False}


def test_sync_only_updates_configured_torrent_clients(tmp_path: Path) -> None:
    config_path = tmp_path / "config.py"
    example_path = tmp_path / "example_config.py"
    _write_config(config_path, "config = {'DEFAULT': {'config_schema_version': 0}, 'TORRENT_CLIENTS': {'home': {'torrent_client': 'qbittorrent'}}}\n")
    _write_config(
        example_path,
        "config = {'DEFAULT': {'config_schema_version': 1}, 'TORRENT_CLIENTS': {'example_qbit': {'torrent_client': 'qbittorrent', 'host': 'localhost'}, 'example_rtorrent': {'torrent_client': 'rtorrent', 'url': ''}}}\n",
    )

    added = sync_config_schema(config_path, example_path)

    assert set(added) == {"DEFAULT.config_schema_version", "TORRENT_CLIENTS.home.host"}
    synced_config = _read_config(config_path)
    assert synced_config["DEFAULT"] == {"config_schema_version": CONFIG_SCHEMA_VERSION}
    assert synced_config["TORRENT_CLIENTS"] == {"home": {"torrent_client": "qbittorrent", "host": "localhost"}}


def test_sync_prompts_before_removing_obsolete_settings(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.py"
    example_path = tmp_path / "example_config.py"
    _write_config(
        config_path,
        "config = {\n    'DEFAULT': {'config_schema_version': 1},\n    # Deprecated setting\n    'obsolete': 'remove me',\n}\n",
    )
    _write_config(example_path, "config = {'DEFAULT': {'config_schema_version': 1, 'new_default': True}}\n")

    assert sync_config_schema(config_path, example_path) == ["DEFAULT.new_default"]
    assert find_obsolete_config_paths(config_path, example_path) == ["obsolete"]

    class InteractiveInput:
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr("sys.stdin", InteractiveInput())
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")
    assert sync_config_schema(config_path, example_path, prompt_for_obsolete=True) == ["obsolete"]
    assert find_obsolete_config_paths(config_path, example_path) == []
    assert "Deprecated setting" not in config_path.read_text(encoding="utf-8")
    assert _read_config(config_path) == {"DEFAULT": {"config_schema_version": 1, "new_default": True}}


def test_sync_migrates_legacy_tracker_aliases(tmp_path: Path) -> None:
    config_path = tmp_path / "config.py"
    example_path = tmp_path / "example_config.py"
    _write_config(config_path, "config = {'DEFAULT': {'config_schema_version': 1, 'default_trackers': 'MTV'}, 'TRACKERS': {'MTV': {'api_key': 'saved'}}}\n")
    _write_config(example_path, "config = {'DEFAULT': {'config_schema_version': 1, 'default_trackers': ''}, 'TRACKERS': {'MORETHANTV': {'api_key': ''}}}\n")

    changed = sync_config_schema(config_path, example_path)

    assert set(changed) == {"DEFAULT.default_trackers", "TRACKERS.MTV->MORETHANTV"}
    config = _read_config(config_path)
    assert config["DEFAULT"]["default_trackers"] == "MORETHANTV"
    assert config["TRACKERS"] == {"MORETHANTV": {"api_key": "saved"}}
