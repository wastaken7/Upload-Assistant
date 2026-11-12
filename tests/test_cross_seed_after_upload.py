"""The cross-seed step leaves alone a tracker that just received this upload."""

# ruff: noqa: S101

from unittest.mock import AsyncMock

import pytest

import upload
from src.meta import Meta

DOWNLOAD_URL = "https://tracker.example/torrent/download/1.abcdef"


def _prepare(monkeypatch, tmp_path, tracker_status):
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="example-release",
        path=str(tmp_path / "Example.Show.S01.1080p.BluRay.REMUX.AVC-GROUP"),
        trackers=["LST"],
        dupe_checked_trackers=["LST"],
        tracker_status=tracker_status,
    )
    meta["LST_cross_seed"] = DOWNLOAD_URL

    download = AsyncMock(return_value=None)
    add_to_client = AsyncMock(return_value=None)
    monkeypatch.setattr(upload, "config", {"DEFAULT": {}, "TRACKERS": {}})
    monkeypatch.setattr(upload.Common, "download_tracker_torrent", download)
    monkeypatch.setattr(upload, "client", type("FakeClients", (), {"add_to_client": add_to_client})(), raising=False)
    return meta, download, add_to_client


@pytest.mark.asyncio
async def test_cross_seed_skips_tracker_that_received_the_upload(tmp_path, monkeypatch):
    meta, download, add_to_client = _prepare(
        monkeypatch,
        tmp_path,
        {"LST": {"upload": True, "upload_success": True, "torrent_id": "2"}},
    )

    await upload.process_cross_seeds(meta)

    download.assert_not_awaited()
    add_to_client.assert_not_awaited()


@pytest.mark.asyncio
async def test_cross_seed_still_runs_when_nothing_was_uploaded(tmp_path, monkeypatch):
    meta, download, add_to_client = _prepare(
        monkeypatch,
        tmp_path,
        {"LST": {"upload": False, "dupe": True}},
    )

    await upload.process_cross_seeds(meta)

    download.assert_awaited_once()
    assert download.await_args.kwargs["downurl"] == DOWNLOAD_URL
    assert download.await_args.kwargs["cross"] is True
    add_to_client.assert_awaited_once_with(meta, "LST", cross=True)


@pytest.mark.asyncio
async def test_cross_seed_still_runs_when_the_upload_failed(tmp_path, monkeypatch):
    meta, download, add_to_client = _prepare(
        monkeypatch,
        tmp_path,
        {"LST": {"upload": True, "upload_success": False}},
    )

    await upload.process_cross_seeds(meta)

    download.assert_awaited_once()
    add_to_client.assert_awaited_once_with(meta, "LST", cross=True)
