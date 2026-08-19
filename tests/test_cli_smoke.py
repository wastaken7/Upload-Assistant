# ruff: noqa: S101, S603
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_upload_help_flags(flag: str) -> None:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "upload.py"), flag],
        cwd=REPO_ROOT,
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


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_config_generator_help_flags(flag: str) -> None:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "config-generator.py"), flag],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, f"Command failed with stderr: {result.stderr}"
    assert "usage: config-generator.py" in result.stdout.lower()
