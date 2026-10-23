"""Shared screenshot hosting respects trackers' direct image uploads."""

# ruff: noqa: S101

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import aiofiles
import pytest

import upload
from src.meta import Meta
from src.temp_paths import screenshots_dir


@pytest.mark.asyncio
@pytest.mark.parametrize("debug", [False, True])
@pytest.mark.parametrize(
    "trackers, tracker_config, shared_upload",
    [
        (["HDBITS"], {}, False),
        (["HDBITS"], {"HDBITS": {"img_rehost": True}}, False),
        (["HDBITS"], {"HDBITS": {"img_rehost": False}}, True),
        (["HDBITS", "AITHER"], {}, True),
        (["PTERCLUB"], {}, True),
        (["PTERCLUB"], {"PTERCLUB": {"img_rehost": True}}, False),
        (["PTERCLUB"], {"PTERCLUB": {"img_rehost": False}}, True),
        (["HDBITS", "PTERCLUB"], {"PTERCLUB": {"img_rehost": True}}, False),
        (["HDBITS", "PTERCLUB"], {}, True),
        (["HDBITS", "PTERCLUB"], {"HDBITS": {"img_rehost": False}, "PTERCLUB": {"img_rehost": True}}, True),
        (["PTERCLUB", "AITHER"], {"PTERCLUB": {"img_rehost": True}}, True),
        (["TORRENTLEECH"], {"TORRENTLEECH": {"img_rehost": True, "api_upload": False}}, True),
        (["TORRENTLEECH"], {"TORRENTLEECH": {"img_rehost": True, "api_upload": True}}, True),
        (["HDBITS", "TORRENTLEECH"], {"TORRENTLEECH": {"img_rehost": True}}, True),
        (["AITHER"], {}, True),
    ],
)
async def test_shared_screenshot_hosting(tmp_path, monkeypatch, debug, trackers, tracker_config, shared_upload):
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="example-release",
        path=str(tmp_path / "Example.Show.S02.1080p.WEB-DL.H.264-GROUP"),
        title="Example Show",
        category="TV",
        tv_pack=1,
        trackers=trackers,
        screens=12,
        cutoff=12,
        debug=debug,
        unattended=True,
        nohash=True,
        we_checked_them_all=True,
    )
    screenshot = screenshots_dir(tmp_path, meta.uuid) / "screen.png"

    def take_screenshots(*_args, **_kwargs):
        screenshot.write_bytes(b"png")

    def host_screenshots(*_args, **_kwargs):
        meta.image_list = [
            {"img_url": "https://images.example/screen.png", "raw_url": "https://images.example/screen.png", "web_url": "https://images.example/screen"}
        ] * meta.screens

    screenshots = AsyncMock(side_effect=take_screenshots)
    hosting = AsyncMock(side_effect=host_screenshots)
    monkeypatch.setattr(upload, "aiofiles", aiofiles, raising=False)
    monkeypatch.setattr(upload, "config", {"DEFAULT": {"img_host_1": "ptscreens"}, "TRACKERS": {"HDBITS": {}, "PTERCLUB": {}, **tracker_config}})
    monkeypatch.setattr(upload, "Prep", lambda **_kwargs: SimpleNamespace(gather_prep=AsyncMock(return_value=meta)))
    monkeypatch.setattr(upload.TrackerSetup, "filter_unsupported_trackers", lambda _self, _meta: None)
    monkeypatch.setattr(upload, "name_manager", SimpleNamespace(get_name=AsyncMock(return_value=("Example", "Example", "Example", []))), raising=False)
    monkeypatch.setattr(upload, "gen_desc", AsyncMock(return_value=meta))
    monkeypatch.setattr(upload.UploadHelper, "get_confirmation", AsyncMock(return_value=True))
    monkeypatch.setattr(upload, "validate_tracker_logins", AsyncMock())
    monkeypatch.setattr(upload.TrackerStatusManager, "process_all_trackers", AsyncMock(return_value=len(trackers)))
    monkeypatch.setattr(upload, "write_meta_file", AsyncMock())
    monkeypatch.setattr(upload, "_publish_webui_preview_target", Mock())
    monkeypatch.setattr(upload, "get_early_artifact_tasks", lambda _uuid: (asyncio.sleep(0), asyncio.sleep(0)))
    monkeypatch.setattr(upload, "takescreens_manager", SimpleNamespace(screenshots=screenshots), raising=False)
    monkeypatch.setattr(upload, "uploadscreens_manager", SimpleNamespace(upload_screens=hosting), raising=False)
    monkeypatch.setattr(upload.cleanup_manager, "reset_terminal", Mock())

    assert await upload.process_meta(meta, str(tmp_path)) is True
    screenshots.assert_awaited_once()
    assert screenshots.await_args.kwargs["cleanup_after_capture"] is False
    assert screenshot.read_bytes() == b"png"
    if shared_upload:
        hosting.assert_awaited_once()
    else:
        hosting.assert_not_awaited()
        assert meta.image_list == []
    assert meta.skip_imghost_upload is False
