"""Regression coverage for AVI season packs and empty video discovery."""

import asyncio
import os
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


@pytest.mark.parametrize("sort_by_size", [False, True])
def test_video_discovery_ignores_macos_sidecars(tmp_path, sort_by_size):
    video = tmp_path / "movie.2000.mkv"
    video.write_bytes(b"video")
    (tmp_path / "._movie.2000.mkv").write_bytes(b"macOS metadata" * 10)

    assert asyncio.run(VideoManager().get_video(str(tmp_path), sort_by_size)) == (str(video), [str(video)])


@pytest.mark.parametrize("sidecar", ["readme.txt", "extras.rar"])
def test_avi_with_sidecars_is_not_classified_as_book_or_game(tmp_path, sidecar):
    (tmp_path / "episode.avi").write_bytes(b"video")
    (tmp_path / sidecar).write_bytes(b"sidecar")
    meta = Meta(path=str(tmp_path))
    prep = SimpleNamespace(disc_info_manager=SimpleNamespace(get_disc=AsyncMock(return_value=("", str(tmp_path), {}, []))))

    asyncio.run(detect_disc_and_category(prep, meta))

    assert meta.category not in ("BOOK", "GAME", "MUSIC")


@pytest.mark.parametrize("with_sidecar", [False, True])
def test_empty_directory_stops_before_scene_or_mediainfo_processing(tmp_path, monkeypatch, with_sidecar):
    if with_sidecar:
        (tmp_path / "._movie.2000.mkv").write_bytes(b"macOS metadata")
    meta = Meta(path=str(tmp_path), category="TV", isdir=True)
    scene = AsyncMock()
    export = AsyncMock()
    prep = SimpleNamespace(scene_manager=SimpleNamespace(is_scene=scene))
    monkeypatch.setattr("src.prep_helpers.export_info", export)

    with pytest.raises(ValueError, match="No video files found"):
        asyncio.run(process_media_files(prep, meta, str(tmp_path), {}))

    scene.assert_not_awaited()
    export.assert_not_awaited()


def _make_nested_pack(root):
    """Build a fictional site-rip pack: one root video, two part folders, extras."""
    files = {
        "Root.Scene_1080p.mp4": b"root",
        "Part 1/Alpha.Scene_1080p.mp4": b"alpha",
        "Part 2/Beta.Scene_1080p.mp4": b"beta",
        "Part 2/Deeper/Gamma.Scene_1080p.mp4": b"gamma",
        "Screens/Alpha.Scene.jpg": b"image",
        "Sample/Alpha.Scene_1080p.mp4": b"sample",
        "._Part 3/Delta.Scene_1080p.mp4": b"sidecar",
    }
    for relative, payload in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    return root.resolve()


def test_recursive_discovery_collects_videos_from_subfolders(tmp_path):
    root = _make_nested_pack(tmp_path / "Studio Pack")

    video, filelist = asyncio.run(VideoManager().get_video(str(root), recursive=True))

    expected = sorted(str(root / relative) for relative in ("Root.Scene_1080p.mp4", "Part 1/Alpha.Scene_1080p.mp4", "Part 2/Beta.Scene_1080p.mp4", "Part 2/Deeper/Gamma.Scene_1080p.mp4"))
    assert filelist == expected
    assert video == expected[0]


def test_default_discovery_still_reads_only_the_release_root(tmp_path):
    root = _make_nested_pack(tmp_path / "Studio Pack")

    assert asyncio.run(VideoManager().get_video(str(root))) == (str(root / "Root.Scene_1080p.mp4"), [str(root / "Root.Scene_1080p.mp4")])


def test_recursive_discovery_finds_videos_below_an_empty_root(tmp_path):
    root = tmp_path / "Studio Pack"
    nested = root / "Studio 2012-2020 Part 1"
    nested.mkdir(parents=True)
    (nested / "Scene_1080p.mp4").write_bytes(b"video")

    assert asyncio.run(VideoManager().get_video(str(root), recursive=True)) == (str((nested / "Scene_1080p.mp4").resolve()), [str((nested / "Scene_1080p.mp4").resolve())])


@pytest.mark.parametrize(("category", "recursive"), [("XXX", True), ("MOVIE", False), ("TV", False)])
def test_only_xxx_scans_subfolders_for_videos(tmp_path, monkeypatch, category, recursive):
    meta = Meta(path=str(tmp_path), category=category, isdir=True)
    get_video = AsyncMock(return_value=("", []))
    monkeypatch.setattr("src.prep_helpers.video_manager.get_video", get_video)

    with pytest.raises(ValueError, match="No video files found"):
        asyncio.run(process_media_files(SimpleNamespace(), meta, str(tmp_path), {}))

    assert get_video.await_args.kwargs == {"recursive": recursive}


def test_xxx_pack_keeps_every_nested_video_in_the_file_list(tmp_path):
    root = _make_nested_pack(tmp_path / "Studio Pack")
    meta = Meta(path=str(root), category="XXX", isdir=True)
    # Stop right after discovery; the rest of preparation is not under test.
    scene = AsyncMock(side_effect=RuntimeError("stop after discovery"))
    prep = SimpleNamespace(scene_manager=SimpleNamespace(is_scene=scene))

    with pytest.raises(RuntimeError, match="stop after discovery"):
        asyncio.run(process_media_files(prep, meta, str(root), {}))

    assert meta.filelist == sorted(str(root / relative) for relative in ("Root.Scene_1080p.mp4", "Part 1/Alpha.Scene_1080p.mp4", "Part 2/Beta.Scene_1080p.mp4", "Part 2/Deeper/Gamma.Scene_1080p.mp4"))


def test_recursive_discovery_stops_when_a_subfolder_cannot_be_read(tmp_path, monkeypatch):
    root = _make_nested_pack(tmp_path / "Studio Pack")
    real_walk = os.walk

    def walk_with_unreadable_folder(top, onerror=None, **kwargs):
        yield from real_walk(top, onerror=onerror, **kwargs)
        # Like os.walk, an unreadable folder is skipped silently unless onerror is given.
        if onerror is not None:
            onerror(PermissionError(13, "Permission denied", str(root / "Part 3")))

    monkeypatch.setattr("src.video.os.walk", walk_with_unreadable_folder)

    assert asyncio.run(VideoManager().get_video(str(root), recursive=True)) == ("", [])
