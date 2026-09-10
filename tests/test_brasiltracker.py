"""Focused tests for BrasilTracker payload normalization."""

# ruff: noqa: S101

import asyncio

from src.meta import Meta
from src.trackers.GAZELLE.brasiltracker import BrasilTracker


def test_brasiltracker_video_container_is_case_insensitive() -> None:
    tracker = object.__new__(BrasilTracker)

    assert asyncio.run(tracker.get_container(Meta(category="MOVIE", container="MKV"))) == "MKV"
    assert asyncio.run(tracker.get_container(Meta(category="MOVIE", container="Mp4"))) == "MP4"
