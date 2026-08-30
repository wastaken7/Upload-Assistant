from __future__ import annotations

import asyncio

import pytest

from src.audio import AudioManager
from src.meta import Meta


def _audio_track(language: str, title: str = "") -> dict[str, str]:
    return {
        "@type": "Audio",
        "Format": "AAC",
        "Channels": "2",
        "Language": language,
        "Title": title,
    }


def _classify_audio(
    tracks: list[dict[str, str]],
    *,
    no_dual: bool = False,
    dual_audio: bool = False,
) -> tuple[str, Meta]:
    mediainfo = {"media": {"track": tracks}}
    meta = Meta(
        mediainfo=mediainfo,
        original_language="ja",
        no_dual=no_dual,
        dual_audio=dual_audio,
    )

    audio, _, _ = asyncio.run(AudioManager({}).get_audio_v2(mediainfo, meta, None))
    return audio, meta


def test_two_qualifying_audio_tracks_produce_dual_audio() -> None:
    audio, meta = _classify_audio([_audio_track("ja"), _audio_track("en")])

    assert audio == "Dual-Audio AAC 2.0"
    assert meta.dual_audio is True


@pytest.mark.parametrize("track_count", [3, 4])
def test_three_or_more_qualifying_audio_tracks_produce_multi(track_count: int) -> None:
    languages = ["ja", "en", "fr", "de"]
    audio, meta = _classify_audio([_audio_track(language) for language in languages[:track_count]])

    assert audio == "MULTI AAC 2.0"
    assert meta.dual_audio is False


def test_commentary_and_compatibility_tracks_do_not_increase_count() -> None:
    audio, meta = _classify_audio(
        [
            _audio_track("ja"),
            _audio_track("en"),
            _audio_track("en", "Director Commentary"),
            _audio_track("ja", "Compatibility Track"),
        ]
    )

    assert audio == "Dual-Audio AAC 2.0"
    assert meta.dual_audio is True


@pytest.mark.parametrize("track_count", [2, 3])
def test_no_dual_suppresses_automatic_multitrack_label(track_count: int) -> None:
    languages = ["ja", "en", "fr"]
    audio, meta = _classify_audio([_audio_track(language) for language in languages[:track_count]], no_dual=True)

    assert audio == "AAC 2.0"
    assert meta.dual_audio is False


def test_explicit_dual_audio_forces_dual_audio_for_three_tracks() -> None:
    audio, meta = _classify_audio(
        [_audio_track("ja"), _audio_track("en"), _audio_track("fr")],
        dual_audio=True,
    )

    assert audio == "Dual-Audio AAC 2.0"
    assert meta.dual_audio is True
