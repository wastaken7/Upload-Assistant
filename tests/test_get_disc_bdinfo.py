"""BDMV preparation resolves BDInfo without blocking on the managed download."""

# ruff: noqa: S101

import asyncio
import platform
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src import discparse, get_disc
from src.discparse import DiscParse
from src.get_disc import DiscInfoManager
from src.meta import Meta


def _executable(path: Path, mode: int = 0o755) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    path.chmod(mode)
    return path


def _linux_arm64(monkeypatch: pytest.MonkeyPatch, system: str = "Linux") -> None:
    monkeypatch.setattr(platform, "system", lambda: system)
    monkeypatch.setattr(platform, "machine", lambda: "aarch64")


def test_bdinfo_command_prefers_configured_path(tmp_path: Path) -> None:
    configured = _executable(tmp_path / "custom" / "bdinfo")

    assert DiscParse({"DEFAULT": {"bdinfo_path": str(configured)}})._bdinfo_command(str(tmp_path)) == str(configured)


def test_bdinfo_command_uses_managed_linux_build_on_android(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _linux_arm64(monkeypatch, "Android")
    _executable(tmp_path / "bin" / "bdinfo" / "linux" / "arm64" / "bdinfo")

    assert DiscParse({"DEFAULT": {}})._bdinfo_command(str(tmp_path)) == f"{tmp_path}/bin/bdinfo/linux/arm64/bdinfo"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX executable bits")
def test_bdinfo_command_skips_non_executable_managed_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _linux_arm64(monkeypatch)
    _executable(tmp_path / "bin" / "bdinfo" / "linux" / "arm64" / "bdinfo", mode=0o600)
    monkeypatch.setattr(discparse.shutil, "which", lambda command: f"/usr/bin/{command}")

    assert DiscParse({"DEFAULT": {}})._bdinfo_command(str(tmp_path)) == "bdinfo"


def test_bdinfo_command_reports_missing_binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _linux_arm64(monkeypatch)
    monkeypatch.setattr(discparse.shutil, "which", lambda _command: None)

    assert DiscParse({"DEFAULT": {}})._bdinfo_command(str(tmp_path)) is None


@pytest.mark.asyncio
async def test_malformed_bdinfo_report_is_not_retried_forever(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeMplsParser:
        def __init__(self, _file: object) -> None:
            pass

        def load_movie_playlist(self) -> SimpleNamespace:
            return SimpleNamespace(playlist_start_address=0)

        def load_playlist(self) -> SimpleNamespace:
            return SimpleNamespace(play_items=[SimpleNamespace(intime=0, outtime=45000 * 3600, clip_information_filename="00000")])

    release = tmp_path / "Example.Movie.2020.1080p.Blu-ray.AVC-GROUP"
    (release / "BDMV" / "PLAYLIST").mkdir(parents=True)
    (release / "BDMV" / "STREAM").mkdir()
    (release / "BDMV" / "PLAYLIST" / "00000.mpls").write_bytes(b"")
    (release / "BDMV" / "STREAM" / "00000.m2ts").write_bytes(b"\0" * 16)
    save_dir = tmp_path / "tmp" / "example-release"
    save_dir.mkdir(parents=True)
    # A cached report that cannot be parsed.
    report = save_dir / "Disc1_00000_FULL.txt"
    report.write_text("not a BDInfo report", encoding="utf-8")
    monkeypatch.setattr(discparse, "MplsParser", FakeMplsParser)
    meta = Meta(base_dir=str(tmp_path), uuid="example-release", path=str(release), unattended=True)
    discs = [{"path": str(release / "BDMV"), "name": release.name, "type": "BDMV", "summary": "", "bdinfo": ""}]

    parser = DiscParse({"DEFAULT": {"use_largest_playlist": True}})
    _discs, bdinfo = await asyncio.wait_for(parser.get_bdinfo(meta, discs, meta.uuid, str(tmp_path), []), timeout=10)

    assert bdinfo == ""
    # The next run must rescan instead of reusing the broken report.
    assert not report.exists()


def _bdmv_release(tmp_path: Path) -> Meta:
    release = tmp_path / "Example.Movie.2020.1080p.Blu-ray.AVC-GROUP"
    (release / "BDMV").mkdir(parents=True)
    return Meta(base_dir=str(tmp_path), uuid="example-release", path=str(release))


def _manager(monkeypatch: pytest.MonkeyPatch, config: dict, bdinfo: object) -> DiscInfoManager:
    manager = DiscInfoManager(config)
    monkeypatch.setattr(manager._parser, "get_bdinfo", AsyncMock(side_effect=lambda _meta, discs, *_args: (discs, bdinfo)))
    return manager


@pytest.mark.asyncio
async def test_configured_bdinfo_skips_managed_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    configured = tmp_path / "bdinfo"
    configured.write_bytes(b"")
    configured.chmod(0o755)
    ensure = AsyncMock(side_effect=Exception("Unsupported platform: example"))
    monkeypatch.setattr(get_disc.BDInfoBinaryManager, "ensure_bdinfo_binary", ensure)
    manager = _manager(monkeypatch, {"DEFAULT": {"bdinfo_path": str(configured)}}, {"video": []})

    is_disc, _videoloc, bdinfo, _discs = await manager.get_disc(_bdmv_release(tmp_path))

    assert is_disc == "BDMV"
    assert bdinfo == {"video": []}
    ensure.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_download_falls_back_to_bdinfo_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_disc.BDInfoBinaryManager, "ensure_bdinfo_binary", AsyncMock(side_effect=Exception("Unsupported platform: example")))
    monkeypatch.setattr(get_disc.shutil, "which", lambda command: f"/usr/bin/{command}")
    manager = _manager(monkeypatch, {"DEFAULT": {}}, {"video": []})

    _is_disc, _videoloc, bdinfo, _discs = await manager.get_disc(_bdmv_release(tmp_path))

    assert bdinfo == {"video": []}


@pytest.mark.asyncio
async def test_failed_download_without_fallback_is_raised(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_disc.BDInfoBinaryManager, "ensure_bdinfo_binary", AsyncMock(side_effect=Exception("Unsupported platform: example")))
    monkeypatch.setattr(get_disc.shutil, "which", lambda _command: None)
    manager = _manager(monkeypatch, {"DEFAULT": {}}, {"video": []})

    with pytest.raises(Exception, match="Unsupported platform"):
        await manager.get_disc(_bdmv_release(tmp_path))


@pytest.mark.asyncio
async def test_missing_bdinfo_report_fails_with_clear_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_disc.BDInfoBinaryManager, "ensure_bdinfo_binary", AsyncMock(return_value="bdinfo"))
    manager = _manager(monkeypatch, {"DEFAULT": {}}, "")

    with pytest.raises(RuntimeError, match="BDInfo did not produce a report"):
        await manager.get_disc(_bdmv_release(tmp_path))
