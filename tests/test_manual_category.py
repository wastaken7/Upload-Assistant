"""Regression tests for explicit content categories."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.meta import Meta
from src.prep import Prep
from src.prep_helpers import detect_disc_and_category
from src.video import video_manager


def test_manual_music_category_routes_to_music_before_media_processing(tmp_path):
    album = tmp_path / "Artist - Album"
    album.mkdir()
    (album / "01 - Track.flac").write_bytes(b"audio")
    meta = Meta(path=str(album), manual_category="music")
    prep = SimpleNamespace(disc_info_manager=SimpleNamespace(get_disc=AsyncMock(return_value=("", str(album), {}, []))))

    asyncio.run(detect_disc_and_category(prep, meta))

    assert meta.category == "MUSIC"  # noqa: S101


def test_manual_podcast_category_routes_before_media_processing(tmp_path):
    episode = tmp_path / "episode.mp3"
    episode.write_bytes(b"audio")
    meta = Meta(path=str(episode), manual_category="podcast")
    prep = SimpleNamespace(disc_info_manager=SimpleNamespace(get_disc=AsyncMock(return_value=("", str(episode), {}, []))))

    asyncio.run(detect_disc_and_category(prep, meta))

    assert meta.category == "PODCAST"  # noqa: S101


def test_podcast_symlinks_are_rejected_before_disc_detection(tmp_path):
    podcast = tmp_path / "podcast"
    outside = tmp_path / "outside"
    podcast.mkdir()
    outside.mkdir()
    (podcast / "BDMV").symlink_to(outside, target_is_directory=True)
    prep = Prep.__new__(Prep)
    prep.config = {"DEFAULT": {}}
    meta = Meta(manual_category="podcast", path=str(podcast), base_dir=str(tmp_path), uuid="podcast-disc-symlink")
    disc_detection = AsyncMock()

    with (
        patch("src.prep.prep_helpers.init_meta", return_value=(False, False, object(), False, [], [])),
        patch("src.prep.prep_helpers.detect_disc_and_category", new=disc_detection),
        pytest.raises(ValueError, match="symbolic links"),
    ):
        asyncio.run(prep.gather_prep(meta, "cli"))

    disc_detection.assert_not_awaited()


def test_missing_cli_video_exits_with_failure_status(tmp_path):
    with pytest.raises(SystemExit) as error:
        asyncio.run(video_manager.get_video(str(tmp_path), "cli"))

    assert error.value.code == 1  # noqa: S101
