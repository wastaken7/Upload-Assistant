"""Regression tests for explicit content categories."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.meta import Meta
from src.prep_helpers import detect_disc_and_category
from src.video import video_manager


def test_manual_music_category_routes_to_music_before_media_processing(tmp_path):
    album = tmp_path / "Artist - Album"
    album.mkdir()
    (album / "01 - Track.flac").write_bytes(b"audio")
    meta = Meta(path=str(album), manual_category="music")
    prep = SimpleNamespace(disc_info_manager=SimpleNamespace(get_disc=AsyncMock(return_value=("", str(album), {}, []))))

    asyncio.run(detect_disc_and_category(prep, meta))

    assert meta.category == "MUSIC"


def test_missing_cli_video_exits_with_failure_status(tmp_path):
    with pytest.raises(SystemExit) as error:
        asyncio.run(video_manager.get_video(str(tmp_path), "cli"))

    assert error.value.code == 1
