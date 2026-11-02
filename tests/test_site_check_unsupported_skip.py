"""Site check mode skips BDMV discs cleanly instead of failing the item."""

# ruff: noqa: S101

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import upload
from src.exceptions import UnsupportedSiteCheckError
from src.get_disc import DiscInfoManager
from src.meta import Meta


@pytest.mark.asyncio
async def test_get_disc_rejects_bdmv_in_site_check(tmp_path):
    release = tmp_path / "Example.Movie.2020.1080p.Blu-ray.AVC-GROUP"
    (release / "BDMV").mkdir(parents=True)
    meta = Meta(base_dir=str(tmp_path), uuid="example-release", path=str(release), site_check=True)

    with pytest.raises(UnsupportedSiteCheckError):
        await DiscInfoManager({}).get_disc(meta)


@pytest.mark.asyncio
async def test_process_meta_skips_unsupported_site_check_release(tmp_path, monkeypatch):
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="example-release",
        path=str(tmp_path / "Example.Movie.2020.1080p.Blu-ray.AVC-GROUP"),
        imghost="ptscreens",
        unattended=True,
        site_check=True,
    )
    gather_prep = AsyncMock(side_effect=UnsupportedSiteCheckError("BDMV disc checking is not supported in site_check mode, yet."))
    stage = Mock()
    notice = Mock()
    monkeypatch.setattr(upload, "config", {"DEFAULT": {"img_host_1": "ptscreens"}})
    monkeypatch.setattr(upload, "Prep", lambda **_kwargs: SimpleNamespace(gather_prep=gather_prep))
    monkeypatch.setattr(upload.webui_events, "stage", stage)
    monkeypatch.setattr(upload.webui_events, "notice", notice)

    assert await upload.process_meta(meta, str(tmp_path)) is False
    assert meta.skipped_unsupported is True
    assert meta.skipped_by_user is False
    stage.assert_called_with("prep", "skip")
    notice.assert_called_once()
    assert notice.call_args.args[0] == "attention"
