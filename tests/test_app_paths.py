import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


def test_user_data_override_holds_runtime_config(tmp_path: Path) -> None:
    """``data.config`` must resolve from UA_DATA_DIR, never the checkout."""
    state_dir = tmp_path / "state"
    environment = os.environ | {"PYTHONPATH": str(Path.cwd()), "UA_DATA_DIR": str(state_dir)}

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from data.config import config; from src.app_paths import CONFIG_PATH, DATA_DIR, STATE_DIR; "
            "assert CONFIG_PATH.parent == DATA_DIR; assert CONFIG_PATH.exists(); "
            "assert str(STATE_DIR / 'data' / 'config.py') == str(CONFIG_PATH); assert isinstance(config, dict)",
        ],
        cwd=Path.cwd(),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr  # noqa: S101
    assert (state_dir / "data" / "config.py").is_file()  # noqa: S101


def test_state_layout_has_one_data_directory(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    config_path = state_dir / "data" / "config.py"
    assert config_path.parent == state_dir / "data"  # noqa: S101
    assert not (state_dir / "data" / "data" / "config.py").exists()  # noqa: S101


def test_legacy_checkout_config_blocks_upload(monkeypatch, tmp_path: Path) -> None:
    from src import app_paths

    legacy_config = tmp_path / "checkout" / "data" / "config.py"
    active_config = tmp_path / "state" / "data" / "config.py"
    legacy_config.parent.mkdir(parents=True)
    legacy_config.write_text("config = {}", encoding="utf-8")
    monkeypatch.setattr(app_paths, "LEGACY_CONFIG_PATH", legacy_config)
    monkeypatch.setattr(app_paths, "CONFIG_PATH", active_config)

    with pytest.raises(app_paths.LegacyConfigLocationError, match="obsolete location") as exc_info:
        app_paths.ensure_legacy_config_absent()

    assert str(legacy_config) in str(exc_info.value)  # noqa: S101
    assert str(active_config) in str(exc_info.value)  # noqa: S101


def test_active_config_is_not_mistaken_for_legacy(monkeypatch, tmp_path: Path) -> None:
    from src import app_paths

    config_path = tmp_path / "data" / "config.py"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("config = {}", encoding="utf-8")
    monkeypatch.setattr(app_paths, "LEGACY_CONFIG_PATH", config_path)
    monkeypatch.setattr(app_paths, "CONFIG_PATH", config_path)

    app_paths.ensure_legacy_config_absent()


def test_default_data_dir_unix_default(monkeypatch) -> None:
    from src.app_paths import _default_data_dir

    fake_home = Path("/home/user")
    monkeypatch.delenv("UA_DATA_DIR", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.setattr(Path, "exists", lambda _self: False)

    with patch("src.app_paths.os.name", "posix"):
        assert _default_data_dir().as_posix() == "/home/user/.local/share/Upload-Assistant"  # noqa: S101


def test_default_data_dir_unix_xdg_data_home(monkeypatch) -> None:
    from src.app_paths import _default_data_dir

    fake_xdg = Path("/custom_xdg")
    monkeypatch.delenv("UA_DATA_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", "/custom_xdg")
    monkeypatch.setattr(Path, "expanduser", lambda _self: fake_xdg)
    monkeypatch.setattr(Path, "exists", lambda _self: False)

    with patch("src.app_paths.os.name", "posix"):
        assert _default_data_dir() == fake_xdg / "Upload-Assistant"  # noqa: S101


def test_default_data_dir_unix_legacy_fallback(monkeypatch) -> None:
    from src.app_paths import _default_data_dir

    fake_home = Path("/home/user")
    legacy_dir = "/home/user/.local/share/upload-assistant"

    monkeypatch.delenv("UA_DATA_DIR", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    def fake_exists(self: Path) -> bool:
        return self.as_posix() == legacy_dir

    monkeypatch.setattr(Path, "exists", fake_exists)

    with patch("src.app_paths.os.name", "posix"):
        assert _default_data_dir().as_posix() == legacy_dir  # noqa: S101
