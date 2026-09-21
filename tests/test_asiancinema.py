# ruff: noqa: S101
import asyncio

import pytest

from src.meta import Meta
from src.trackers.UNIT3D.asiancinema import AsianCinema


def _tracker() -> AsianCinema:
    return AsianCinema({"DEFAULT": {}, "TRACKERS": {"ASIANCINEMA": {}}})


@pytest.mark.parametrize("category, expected", [("MOVIE", "1"), ("TV", "2"), ("MUSIC", "3")])
def test_category_ids(category: str, expected: str) -> None:
    tracker = _tracker()
    assert category in tracker.supported_categories
    assert asyncio.run(tracker.get_category_id(Meta(category=category))) == {"category_id": expected}


@pytest.mark.parametrize(
    "meta, expected",
    [
        (Meta(type="DISC"), "1"),
        (Meta(type="REMUX"), "7"),
        (Meta(type="WEBDL"), "9"),
        (Meta(type="HDTV", source="SDTV"), "13"),
        (Meta(type="HDTV"), "17"),
        (Meta(type="HDTV", source="UHDTV"), "19"),
        (Meta(category="MUSIC", format="FLAC"), "15"),
        (Meta(type="ENCODE"), "0"),
    ],
)
def test_type_ids(meta: Meta, expected: str) -> None:
    assert asyncio.run(_tracker().get_type_id(meta)) == {"type_id": expected}


def test_mapping_modes_and_existing_resolutions() -> None:
    tracker = _tracker()
    assert asyncio.run(tracker.get_category_id(Meta(), reverse=True))["3"] == "MUSIC"
    assert asyncio.run(tracker.get_type_id(Meta(), mapping_only=True))["UHDTV"] == "19"
    assert asyncio.run(tracker.get_type_id(Meta(), type="SDTV")) == {"type_id": "13"}
    assert asyncio.run(tracker.get_resolution_id(Meta(resolution="1080p"))) == {"resolution_id": "2"}
