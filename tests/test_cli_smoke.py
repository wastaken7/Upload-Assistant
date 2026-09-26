# ruff: noqa: S101, S603
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_upload_help_flags_do_not_create_config(flag: str, tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    environment = os.environ | {"UA_DATA_DIR": str(state_dir)}
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "upload.py"), flag],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, f"Command failed with stderr: {result.stderr}"
    assert "usage: upload.py" in result.stdout.lower()
    if flag == "-h":
        assert "common options:" in result.stdout.lower() or "--help" in result.stdout.lower()
    else:
        assert "--trackers" in result.stdout.lower()
    assert not state_dir.exists()


def test_cli_creates_missing_config_and_stops_for_configuration(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    environment = os.environ | {"UA_DATA_DIR": str(state_dir)}
    bootstrap = (
        "import runpy, sys; from pathlib import Path; import src.app_paths as app_paths; "
        "script_path, content_path, legacy_path = map(Path, sys.argv[1:]); "
        "app_paths.LEGACY_CONFIG_PATH = legacy_path; "
        "sys.argv = [str(script_path), str(content_path)]; "
        "runpy.run_path(str(script_path), run_name='__main__')"
    )

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            bootstrap,
            str(REPO_ROOT / "upload.py"),
            str(tmp_path / "Fictional.Release.2026"),
            str(tmp_path / "checkout" / "data" / "config.py"),
        ],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    output = f"{result.stdout}\n{result.stderr}".lower()
    assert result.returncode == 1
    assert (state_dir / "data" / "config.py").is_file()
    assert "configuration file created" in output
    assert "configure it before running an upload" in output
