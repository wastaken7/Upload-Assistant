# ruff: noqa: S101
from pathlib import Path

import pytest

from src.binaries import configured_binary


def test_configured_binary_returns_existing_override(tmp_path: Path) -> None:
    executable = tmp_path / "ffmpeg.exe"
    executable.touch()

    assert configured_binary("ffmpeg_path", {"DEFAULT": {"ffmpeg_path": str(executable)}}) == str(executable)


def test_configured_binary_ignores_empty_override() -> None:
    assert configured_binary("ffmpeg_path", {"DEFAULT": {"ffmpeg_path": ""}}) is None


def test_configured_binary_rejects_missing_override(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="ffmpeg_path"):
        configured_binary("ffmpeg_path", {"DEFAULT": {"ffmpeg_path": str(tmp_path / "missing.exe")}})
