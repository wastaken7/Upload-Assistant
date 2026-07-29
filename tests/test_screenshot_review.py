# ruff: noqa: S101

from pathlib import Path

from src.screenshot_review import (
    apply_staged_remote_uploads,
    delete_screenshot,
    image_version,
    list_review_items,
    list_screenshots,
    staged_remote_uploads,
    target_count,
    undo_remote_replacement,
)


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


def test_remote_images_are_reviewable_and_replacements_are_staged(tmp_path: Path) -> None:
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()
    replacement = screenshots_dir / "review-remote-1.png"
    replacement.write_bytes(b"png")
    (tmp_path / "screenshot_review.json").write_text('{"remote_replacements": {"remote-1": "review-remote-1.png"}}', encoding="utf-8")
    image_list = [
        {"img_url": "https://images.example/one.jpg", "raw_url": "https://images.example/one.jpg", "web_url": "https://images.example/one"},
        {"img_url": "https://images.example/two.jpg", "raw_url": "https://images.example/two.jpg", "web_url": "https://images.example/two"},
    ]

    items = list_review_items(tmp_path, {"image_list": image_list})

    assert [(item.id, item.source) for item in items] == [("remote-0", "remote"), ("remote-1", "replacement")]
    assert items[1].path == replacement
    pending = staged_remote_uploads(tmp_path, image_list)
    assert pending == [(1, replacement)]

    final_images = apply_staged_remote_uploads(
        tmp_path,
        image_list,
        [{"img_url": "https://new.example/two.jpg", "raw_url": "https://new.example/two.jpg", "web_url": "https://new.example/two"}],
        pending,
    )

    assert final_images[0] == image_list[0]
    assert final_images[1]["raw_url"] == "https://new.example/two.jpg"
    assert staged_remote_uploads(tmp_path, final_images) == []


def test_undo_remote_replacement_restores_original_remote_item(tmp_path: Path) -> None:
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()
    replacement = screenshots_dir / "review-remote-0.png"
    replacement.write_bytes(b"png")
    (tmp_path / "screenshot_review.json").write_text('{"remote_replacements": {"remote-0": "review-remote-0.png"}}', encoding="utf-8")
    meta_data = {"image_list": [{"img_url": "https://images.example/one.jpg", "raw_url": "https://images.example/one.jpg"}]}

    undo_remote_replacement(tmp_path, "remote-0")

    assert not replacement.exists()
    assert [(item.id, item.source) for item in list_review_items(tmp_path, meta_data)] == [("remote-0", "remote")]


def test_delete_remote_addition_discards_its_file_and_pending_upload(tmp_path: Path) -> None:
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()
    addition = screenshots_dir / "review-remote-add-0.png"
    addition.write_bytes(b"png")
    (tmp_path / "screenshot_review.json").write_text(
        '{"remote_additions": [{"id": "remote-add-0", "file": "review-remote-add-0.png"}], "generations": {"remote-add-0": 1}}', encoding="utf-8"
    )
    meta_data = {"image_list": [{"img_url": "https://images.example/one.jpg", "raw_url": "https://images.example/one.jpg"}]}

    remaining = delete_screenshot(tmp_path, meta_data, "remote-add-0")

    assert not addition.exists()
    assert [(item.id, item.source) for item in remaining] == [("remote-0", "remote")]
    assert staged_remote_uploads(tmp_path, meta_data["image_list"]) == []
