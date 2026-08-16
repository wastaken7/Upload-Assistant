# ruff: noqa: S101
from pathlib import Path

from bin.get_ffmpeg import FfmpegBinaryManager


def test_managed_ffmpeg_requires_matching_version_marker(tmp_path: Path, monkeypatch) -> None:
    binary = FfmpegBinaryManager.binary_path(tmp_path)
    binary.parent.mkdir(parents=True)
    binary.touch()
    monkeypatch.setattr("bin.get_ffmpeg.shutil.which", lambda _: None)

    assert FfmpegBinaryManager.find_existing_binary(tmp_path) is None

    (binary.parent / f"version_{FfmpegBinaryManager.VERSION}").touch()
    assert FfmpegBinaryManager.find_existing_binary(tmp_path) == str(binary)


def test_system_ffmpeg_uses_platform_appropriate_name(tmp_path: Path, monkeypatch) -> None:
    requested_names: list[str] = []
    monkeypatch.setattr("bin.get_ffmpeg.platform.system", lambda: "Linux")
    monkeypatch.setattr("bin.get_ffmpeg.shutil.which", lambda name: requested_names.append(name) or "/usr/bin/ffmpeg")

    assert FfmpegBinaryManager.find_existing_binary(tmp_path) == "/usr/bin/ffmpeg"
    assert requested_names == ["ffmpeg"]
