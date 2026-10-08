# ruff: noqa: S101
"""Regression tests for TorrentHR's UNIT3D mappings."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.meta import Meta
from src.rehostimages import check_tracker_image_hosts, select_common_image_host
from src.trackers.UNIT3D.torrenthr import TorrentHR
from src.trackersetup import tracker_class_map


def _tracker() -> TorrentHR:
    return TorrentHR({"DEFAULT": {}, "TRACKERS": {"TORRENTHR": {}}})


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        (Meta(category="MOVIE", sd=1), "4"),
        (Meta(category="MOVIE", is_disc="DVD"), "14"),
        (Meta(category="MOVIE", is_disc="BDMV"), "40"),
        (Meta(category="TV", sd=1), "7"),
        (Meta(category="TV"), "34"),
        (Meta(category="TV", anime=True), "31"),
        (Meta(category="MOVIE", combined_genres="Animation"), "18"),
        (Meta(category="MOVIE", combined_genres="Documentary"), "12"),
    ],
)
def test_torrenthr_category_mappings(meta: Meta, expected: str) -> None:
    assert asyncio.run(_tracker().get_category_id(meta)) == {"category_id": expected}


def test_torrenthr_is_registered() -> None:
    assert tracker_class_map["TORRENTHR"] is TorrentHR


def test_torrenthr_selects_required_image_host() -> None:
    assert (
        select_common_image_host(
            {"img_host_1": "imgbox", "img_host_2": "thrimg"},
            ["TORRENTHR"],
            tracker_class_map,
        )
        == "thrimg"
    )


def test_torrenthr_checks_image_host_policy() -> None:
    tracker = _tracker()
    tracker.rehost_images_manager = AsyncMock()
    meta = Meta(category="MOVIE")
    asyncio.run(check_tracker_image_hosts(meta, tracker))
    tracker.rehost_images_manager.check_policy.assert_awaited_once_with(meta, "TORRENTHR", tracker.image_host_policy)
