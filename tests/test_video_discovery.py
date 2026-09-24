"""Regression coverage for AVI season packs and empty video discovery."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.meta import Meta
from src.prep_helpers import detect_disc_and_category, process_media_files
from src.video import VideoManager


@pytest.mark.parametrize("sort_by_size", [False, True])
def test_avi_season_pack_discovery(tmp_path, sort_by_size):
    release = tmp_path / "Eyewitness.S03.DVDRip.XviD-aAF"
    release.mkdir()
    episodes = []
    for episode in range(1, 14):
        path = release / f"aaf-eyewitness.s03e{episode:02}.avi"
        path.write_bytes(b"video" * episode)
        episodes.append(str(path.resolve()))
    (release / "sample.avi").write_bytes(b"sample")
    (release / "release.nfo").write_text("release notes")
    (release / "subtitles.srt").write_text("subtitles")
    (release / "directory.avi").mkdir()

    video, filelist = asyncio.run(VideoManager().get_video(str(release), sort_by_size))

    expected = episodes[::-1] if sort_by_size else episodes
    assert filelist == expected
    assert video == expected[0]


def test_uppercase_avi_extension_and_explicit_sample_override(tmp_path):
    video = tmp_path / "episode.!sample.AVI"
    video.write_bytes(b"video")

    assert asyncio.run(VideoManager().get_video(str(tmp_path))) == (str(video.resolve()), [str(video.resolve())])


@pytest.mark.parametrize("sidecar", ["readme.txt", "extras.rar"])
def test_avi_with_sidecars_is_not_classified_as_book_or_game(tmp_path, sidecar):
    (tmp_path / "episode.avi").write_bytes(b"video")
    (tmp_path / sidecar).write_bytes(b"sidecar")
    meta = Meta(path=str(tmp_path))
    prep = SimpleNamespace(disc_info_manager=SimpleNamespace(get_disc=AsyncMock(return_value=("", str(tmp_path), {}, []))))

    asyncio.run(detect_disc_and_category(prep, meta))

    assert meta.category not in ("BOOK", "GAME", "MUSIC")


def test_empty_directory_stops_before_scene_or_mediainfo_processing(tmp_path, monkeypatch):
    meta = Meta(path=str(tmp_path), category="TV", isdir=True)
    scene = AsyncMock()
    export = AsyncMock()
    prep = SimpleNamespace(scene_manager=SimpleNamespace(is_scene=scene))
    monkeypatch.setattr("src.prep_helpers.export_info", export)

    with pytest.raises(ValueError, match="No video files found"):
        asyncio.run(process_media_files(prep, meta, str(tmp_path), {}))

    scene.assert_not_awaited()
    export.assert_not_awaited()
