"""BDMV preparation resolves BDInfo without blocking on the managed download."""

# ruff: noqa: S101

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src import get_disc
from src.get_disc import DiscInfoManager
from src.meta import Meta


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
