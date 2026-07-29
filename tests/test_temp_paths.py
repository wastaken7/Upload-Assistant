# ruff: noqa: S101

from pathlib import Path

from src.temp_paths import covers_dir, menu_screenshots_dir, posters_dir, screenshots_dir, spectrograms_dir


def test_typed_image_directories_are_isolated_per_release(tmp_path: Path) -> None:
    directories = {
        screenshots_dir(tmp_path, "release"),
        posters_dir(tmp_path, "release"),
        covers_dir(tmp_path, "release"),
        menu_screenshots_dir(tmp_path, "release"),
        spectrograms_dir(tmp_path, "release"),
    }

    assert len(directories) == 5
    assert {path.parent.name for path in directories} == {"release"}
    assert {path.name for path in directories} == {"screenshots", "posters", "covers", "menu_screenshots", "spectrograms"}
    assert all(path.is_dir() for path in directories)
