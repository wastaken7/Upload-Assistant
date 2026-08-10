# ruff: noqa: S101

from pathlib import Path

from src.temp_paths import artwork_dir, menu_screenshots_dir, screenshots_dir, spectrograms_dir


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
