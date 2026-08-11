import stat
from pathlib import Path

import pytest

from bin.get_mkbrr import MkbrrBinaryManager
from src.meta import Meta
from src.torrentcreate import TorrentCreator


@pytest.mark.asyncio
async def test_existing_local_mkbrr_is_used_on_unsupported_platform(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binary_path = tmp_path / "bin" / "mkbrr"
    binary_path.parent.mkdir()
    binary_path.write_text("#!/bin/sh\n", encoding="utf-8")
    binary_path.chmod(binary_path.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr("bin.get_mkbrr.platform.system", lambda: "Android")
    monkeypatch.setattr("bin.get_mkbrr.platform.machine", lambda: "aarch64")

    assert await MkbrrBinaryManager.ensure_mkbrr_binary(tmp_path, "v1.24.0") == str(binary_path)  # noqa: S101
    assert TorrentCreator.get_mkbrr_path(Meta(base_dir=str(tmp_path))) == str(binary_path)  # noqa: S101


def test_find_existing_binary_uses_docker_platform_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binary_path = tmp_path / "bin" / "mkbrr" / "linux" / "amd64" / "mkbrr"
    binary_path.parent.mkdir(parents=True)
    binary_path.write_text("#!/bin/sh\n", encoding="utf-8")
    binary_path.chmod(binary_path.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr("bin.get_mkbrr.platform.system", lambda: "Linux")
    monkeypatch.setattr("bin.get_mkbrr.platform.machine", lambda: "x86_64")

    assert MkbrrBinaryManager.find_existing_binary(tmp_path) == str(binary_path)  # noqa: S101


def test_find_existing_binary_version_checks_managed_platform_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binary_path = tmp_path / "bin" / "mkbrr" / "linux" / "amd64" / "mkbrr"
    binary_path.parent.mkdir(parents=True)
    binary_path.write_text("#!/bin/sh\n", encoding="utf-8")
    binary_path.chmod(binary_path.stat().st_mode | stat.S_IXUSR)
    (binary_path.parent / "v1.23.0").touch()
    monkeypatch.setattr("bin.get_mkbrr.platform.system", lambda: "Linux")
    monkeypatch.setattr("bin.get_mkbrr.platform.machine", lambda: "x86_64")
    monkeypatch.setattr("bin.get_mkbrr.shutil.which", lambda _: None)

    assert MkbrrBinaryManager.find_existing_binary(tmp_path, "v1.24.0") is None  # noqa: S101

    (binary_path.parent / "v1.24.0").touch()
    assert MkbrrBinaryManager.find_existing_binary(tmp_path, "v1.24.0") == str(binary_path)  # noqa: S101


def test_find_existing_binary_uses_freebsd_platform_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binary_path = tmp_path / "bin" / "mkbrr" / "freebsd" / "x86_64" / "mkbrr"
    binary_path.parent.mkdir(parents=True)
    binary_path.write_text("#!/bin/sh\n", encoding="utf-8")
    binary_path.chmod(binary_path.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr("bin.get_mkbrr.platform.system", lambda: "FreeBSD")
    monkeypatch.setattr("bin.get_mkbrr.platform.machine", lambda: "amd64")

    assert MkbrrBinaryManager.find_existing_binary(tmp_path) == str(binary_path)  # noqa: S101


@pytest.mark.asyncio
@pytest.mark.parametrize(("system", "machine"), [("Windows", "i686"), ("Darwin", "ppc64")])
async def test_ensure_mkbrr_binary_rejects_unsupported_platforms(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, system: str, machine: str) -> None:
    monkeypatch.setattr("bin.get_mkbrr.platform.system", lambda: system)
    monkeypatch.setattr("bin.get_mkbrr.platform.machine", lambda: machine)
    monkeypatch.setattr("bin.get_mkbrr.shutil.which", lambda _: None)

    with pytest.raises(Exception, match=f"Unsupported platform: {system.lower()} {machine}"):
        await MkbrrBinaryManager.ensure_mkbrr_binary(tmp_path, "v1.24.0")
