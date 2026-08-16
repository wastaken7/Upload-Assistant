# ruff: noqa: S101
from pathlib import Path
from unittest.mock import patch

import pytest

from src.binaries import configured_binary


def test_configured_binary_returns_existing_override(tmp_path: Path) -> None:
    executable = tmp_path / "ffmpeg.exe"
    executable.touch()
    executable.chmod(executable.stat().st_mode | 0o111)

    assert configured_binary("ffmpeg_path", {"DEFAULT": {"ffmpeg_path": str(executable)}}) == str(executable)


def test_configured_binary_preserves_explicit_relative_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executable = tmp_path / "ffmpeg"
    executable.touch()
    executable.chmod(executable.stat().st_mode | 0o111)
    monkeypatch.chdir(tmp_path)

    assert configured_binary("ffmpeg_path", {"DEFAULT": {"ffmpeg_path": "./ffmpeg"}}) == "./ffmpeg"


def test_configured_binary_ignores_empty_override() -> None:
    assert configured_binary("ffmpeg_path", {"DEFAULT": {"ffmpeg_path": ""}}) is None


def test_configured_binary_uses_runtime_managed_ffmpeg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executable = tmp_path / "ffmpeg.exe"
    executable.touch()
    executable.chmod(executable.stat().st_mode | 0o111)
    monkeypatch.setenv("UA_FFMPEG_PATH", str(executable))

    assert configured_binary("ffmpeg_path", {"DEFAULT": {"ffmpeg_path": ""}}) == str(executable)


def test_configured_binary_prioritizes_explicit_ffmpeg_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    configured = tmp_path / "configured-ffmpeg.exe"
    managed = tmp_path / "managed-ffmpeg.exe"
    configured.touch()
    managed.touch()
    configured.chmod(configured.stat().st_mode | 0o111)
    managed.chmod(managed.stat().st_mode | 0o111)
    monkeypatch.setenv("UA_FFMPEG_PATH", str(managed))

    assert configured_binary("ffmpeg_path", {"DEFAULT": {"ffmpeg_path": str(configured)}}) == str(configured)


def test_configured_binary_rejects_missing_override(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="ffmpeg_path"):
        configured_binary("ffmpeg_path", {"DEFAULT": {"ffmpeg_path": str(tmp_path / "missing.exe")}})


def test_configured_binary_rejects_non_executable_posix_override(tmp_path: Path) -> None:
    executable = tmp_path / "ffmpeg"
    executable.touch()

    with (
        patch("src.binaries.os.name", "posix"),
        patch("src.binaries.os.access", return_value=False),
        pytest.raises(FileNotFoundError, match="not executable"),
    ):
        configured_binary("ffmpeg_path", {"DEFAULT": {"ffmpeg_path": str(executable)}})
