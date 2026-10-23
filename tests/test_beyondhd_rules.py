"""Regression tests for BeyondHD encode codec checks."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.meta import Meta
from src.trackers.beyondhd import BEYONDHD


def _check(video_encode: str, uhd: str = "") -> tuple[bool, list[str]]:
    tracker = BEYONDHD({"DEFAULT": {}, "TRACKERS": {"BEYONDHD": {}}})
    prompts: list[str] = []

    def confirm(_meta: Meta, message: str) -> bool:
        prompts.append(message)
        return False

    meta = Meta(
        type="ENCODE",
        container="mkv",
        valid_mi_settings=True,
        video_encode=video_encode,
        audio="Opus 2.0",
        uhd=uhd,
        tag="-Example",
    )
    with (
        patch.object(tracker, "get_name", AsyncMock(return_value="Fictional Movie 2001 1080p BluRay Opus 2.0 x264-Example")),
        patch.object(tracker, "_confirm_or_skip", side_effect=confirm),
        patch("src.trackers.beyondhd.Common.check_and_confirm_adult_media_upload", return_value=True),
    ):
        result = asyncio.run(tracker.get_additional_checks(meta))
    return result, prompts


@pytest.mark.parametrize("video_encode", [" x264", "Hi10P x264", "x264"])
def test_beyondhd_accepts_x264_encode_with_profile_prefix(video_encode):
    assert _check(video_encode) == (True, [])


def test_beyondhd_rejects_non_x26x_encode():
    assert _check(" H.264") == (False, [])


def test_beyondhd_prompts_for_non_uhd_x265_encode():
    result, prompts = _check(" x265")
    assert result is False
    assert any("x265 encodes" in prompt for prompt in prompts)
    assert _check(" x265", uhd="UHD") == (True, [])
