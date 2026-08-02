# Assertions are the idiomatic pytest checks for this focused payload test.
# ruff: noqa: S101

from unittest.mock import AsyncMock

import pytest

from src.meta import Meta
from src.rehostimages import check_tracker_image_hosts
from src.trackers.UNIT3D.hawkeuno import HawkeUno


@pytest.mark.asyncio
async def test_hawkeuno_uses_api_release_tag_for_repack(monkeypatch):
    tracker = HawkeUno({"TRACKERS": {"HAWKEUNO": {}}})
    monkeypatch.setattr(tracker, "get_description", lambda _meta: _noop())
    meta = Meta(category="TV", type="WEBDL", tmdb=123, repack="REPACK")

    data = await tracker.get_data(meta)

    assert data["release_tag"] == "REPACK"
    assert "repack" not in data


@pytest.mark.asyncio
async def test_hawkeuno_image_host_policy_does_not_require_legacy_method():
    tracker = HawkeUno({"TRACKERS": {"HAWKEUNO": {}}})
    tracker.rehost_images_manager.check_policy = AsyncMock()
    meta = Meta(category="TV", type="WEBDL", tmdb=123)

    await check_tracker_image_hosts(meta, tracker)

    tracker.rehost_images_manager.check_policy.assert_awaited_once_with(meta, "HAWKEUNO", tracker.image_host_policy)


async def _noop():
    return None
