import os
import subprocess
import sys
from pathlib import Path


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


def test_upload_uses_state_root_without_nested_data_directory(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    environment = os.environ | {"PYTHONPATH": str(Path.cwd()), "UA_DATA_DIR": str(state_dir)}

    result = subprocess.run(
        [sys.executable, "upload.py", "-h"],
        cwd=Path.cwd(),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr  # noqa: S101
    assert (state_dir / "data" / "config.py").is_file()  # noqa: S101
    assert not (state_dir / "data" / "data" / "config.py").exists()  # noqa: S101
