# Assertions are the idiomatic pytest checks for this focused payload test.
# ruff: noqa: S101

from unittest.mock import AsyncMock

import pytest

from src.get_desc import DescriptionBuilder
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


@pytest.mark.asyncio
async def test_hawkeuno_respects_configured_screenshot_rows():
    config = {
        "DEFAULT": {"screens_per_row": "1000", "thumbnail_size": "350"},
        "TRACKERS": {"HAWKEUNO": {}},
    }
    builder = DescriptionBuilder("HAWKEUNO", config)

    screens_per_row = await builder.get_screens_per_row()

    assert screens_per_row == 1000
    parts = []
    for index in range(9):
        parts.append(builder.format_screenshot(f"https://example.com/{index}", f"https://example.com/{index}.png"))
        builder._append_screenshot_row_separator(parts, index, screens_per_row)

    assert "\n" not in "".join(parts)


@pytest.mark.asyncio
async def test_hawkeuno_supplies_missing_web_service_and_release_group():
    tracker = HawkeUno({"TRACKERS": {"HAWKEUNO": {}}})
    meta = Meta(
        type="WEBDL",
        service=None,
        tag=None,
        name="Movie 2026 1080p WEB-DL DDP5.1 x265",
        clean_name="Movie.2026.1080p.WEB-DL.DDP5.1.x265",
    )

    assert await tracker.get_name(meta) == {"name": "Movie 2026 1080p NADA WEB-DL DDP5.1 x265-NOGROUP"}
    assert tracker._normalize_upload_name(meta.clean_name, meta) == "Movie.2026.1080p.NADA.WEB-DL.DDP5.1.x265-NOGROUP"


@pytest.mark.asyncio
async def test_hawkeuno_keeps_detected_service_and_group():
    tracker = HawkeUno({"TRACKERS": {"HAWKEUNO": {}}})
    meta = Meta(
        type="WEBDL",
        service="AMZN",
        tag="-GROUP",
        name="Movie 2026 1080p AMZN WEB-DL DDP5.1 x265-GROUP",
    )

    assert await tracker.get_name(meta) == {"name": meta.name}


async def _noop():
    return None
