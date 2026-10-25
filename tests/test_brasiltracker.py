"""Focused tests for BrasilTracker payload normalization."""

# ruff: noqa: S101

import asyncio

from src.meta import Meta
from src.trackers.GAZELLE.brasiltracker import BrasilTracker


def test_brasiltracker_video_container_is_case_insensitive() -> None:
    tracker = object.__new__(BrasilTracker)

    assert asyncio.run(tracker.get_container(Meta(category="MOVIE", container="MKV"))) == "MKV"
    assert asyncio.run(tracker.get_container(Meta(category="MOVIE", container="Mp4"))) == "MP4"


def _portuguese_audio_meta(audio_tags: list[str], is_disc: str = "") -> Meta:
    tracks = [{"@type": "General"}, *({"@type": "Audio", "Language": tag} for tag in audio_tags)]
    return Meta(
        category="MOVIE",
        language_checked=True,
        audio_languages=["Portuguese"],
        original_language="pt",
        is_disc=is_disc,
        mediainfo={"media": {"track": tracks}},
    )


def test_brasiltracker_european_portuguese_audio_is_outro() -> None:
    tracker = object.__new__(BrasilTracker)

    assert asyncio.run(tracker.get_audio(_portuguese_audio_meta(["pt-PT"]))) == "Outro"
    assert asyncio.run(tracker.get_audio(_portuguese_audio_meta(["pt-BR"]))) == "Nacional"
    assert asyncio.run(tracker.get_audio(_portuguese_audio_meta(["pt"]))) == "Nacional"
    assert asyncio.run(tracker.get_audio(_portuguese_audio_meta(["pt-PT", "pt-BR"]))) == "Nacional"
    assert asyncio.run(tracker.get_audio(_portuguese_audio_meta(["pt-PT"], is_disc="BDMV"))) == "Nacional"
