# ruff: noqa: S101

from pathlib import Path

import src.temp_paths as temp_paths
from src.temp_paths import artwork_dir, menu_screenshots_dir, music_release_snapshot_path, screenshots_dir, spectrograms_dir


def test_typed_image_directories_are_isolated_per_release(tmp_path: Path) -> None:
    directories = {
        screenshots_dir(tmp_path, "release"),
        artwork_dir(tmp_path, "release"),
        menu_screenshots_dir(tmp_path, "release"),
        spectrograms_dir(tmp_path, "release"),
    }
    other_directories = {
        screenshots_dir(tmp_path, "other-release"),
        artwork_dir(tmp_path, "other-release"),
        menu_screenshots_dir(tmp_path, "other-release"),
        spectrograms_dir(tmp_path, "other-release"),
    }

    assert len(directories) == 4
    assert {path.parent.name for path in directories} == {"release"}
    assert {path.parent.name for path in other_directories} == {"other-release"}
    assert directories.isdisjoint(other_directories)
    assert {path.name for path in directories} == {"screenshots", "artwork", "menu_screenshots", "spectrograms"}
    assert all(path.is_dir() for path in directories)


def test_music_release_snapshot_uses_state_dir_when_base_dir_is_empty(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    monkeypatch.setattr(temp_paths, "STATE_DIR", state_dir)

    assert music_release_snapshot_path("", "release") == state_dir / "tmp" / "release" / "music_release.json"
    assert music_release_snapshot_path(None, "release") == state_dir / "tmp" / "release" / "music_release.json"


def test_temp_and_image_dirs_use_state_dir_when_base_dir_is_empty_or_none(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    monkeypatch.setattr(temp_paths, "STATE_DIR", state_dir)

    assert temp_paths.release_temp_dir("", "release") == state_dir / "tmp" / "release"
    assert temp_paths.release_temp_dir(None, "release") == state_dir / "tmp" / "release"
    assert artwork_dir("", "release") == state_dir / "tmp" / "release" / "artwork"
    assert artwork_dir(None, "release") == state_dir / "tmp" / "release" / "artwork"
    assert screenshots_dir("", "release") == state_dir / "tmp" / "release" / "screenshots"
    assert screenshots_dir(None, "release") == state_dir / "tmp" / "release" / "screenshots"
    assert (state_dir / "tmp" / "release" / "artwork").is_dir()
    assert (state_dir / "tmp" / "release" / "screenshots").is_dir()
