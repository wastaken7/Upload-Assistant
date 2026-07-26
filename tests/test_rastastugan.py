"""Regression tests for Rastastugan MUSIC type mappings."""

import asyncio

from src.meta import Meta
from src.trackers.UNIT3D.rastastugan import Rastastugan


def _tracker() -> Rastastugan:
    return Rastastugan({"DEFAULT": {"tmdb_api": "test-key"}, "TRACKERS": {"RASTASTUGAN": {}}})


def test_rastastugan_music_types_use_music_format():
    tracker = _tracker()

    assert asyncio.run(tracker.get_type_id(Meta(category="MUSIC", format="FLAC"))) == {"type_id": "7"}
    assert asyncio.run(tracker.get_type_id(Meta(category="MUSIC", format="MP3"))) == {"type_id": "8"}
    assert asyncio.run(tracker.get_type_id(Meta(category="MUSIC", format="M4A"))) == {"type_id": "14"}
    assert asyncio.run(tracker.get_type_id(Meta(category="MUSIC", format="M4B"))) == {"type_id": "20"}


def test_rastastugan_unknown_music_format_uses_other():
    assert asyncio.run(_tracker().get_type_id(Meta(category="MUSIC", format="OPUS"))) == {"type_id": "19"}
