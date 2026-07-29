# ruff: noqa: S101

from pathlib import Path

from src.screenshot_review import delete_screenshot, image_version, list_screenshots, target_count


def test_delete_screenshot_compacts_numbering_and_persists_target(tmp_path: Path) -> None:
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()
    for index in range(3):
        (screenshots_dir / f"Release-{index}.png").write_bytes(b"png")

    remaining = delete_screenshot(tmp_path, {"is_disc": ""}, "generic-1")

    assert [item.id for item in remaining] == ["generic-0", "generic-1"]
    assert [item.path.name for item in remaining] == ["Release-0.png", "Release-1.png"]
    assert target_count(tmp_path, 3) == 2
    assert [item.id for item in list_screenshots(tmp_path, {"is_disc": ""})] == ["generic-0", "generic-1"]


def test_list_screenshots_excludes_disc_and_non_frame_pngs(tmp_path: Path) -> None:
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()
    (screenshots_dir / "Release-0.png").write_bytes(b"png")
    (tmp_path / "posters").mkdir()
    (tmp_path / "posters" / "POSTER.png").write_bytes(b"png")
    (screenshots_dir / "Release-libplacebo-test.png").write_bytes(b"png")

    assert [item.id for item in list_screenshots(tmp_path, {"is_disc": ""})] == ["generic-0"]
    assert list_screenshots(tmp_path, {"is_disc": "BDMV"}) == []


def test_image_version_uses_persisted_generation_over_file_timestamp(tmp_path: Path) -> None:
    (tmp_path / "screenshot_review.json").write_text('{"generations": {"generic-0": 3}}', encoding="utf-8")

    assert image_version(tmp_path, "generic-0", 123456) == 3
    assert image_version(tmp_path, "generic-1", 123456) == 123456
