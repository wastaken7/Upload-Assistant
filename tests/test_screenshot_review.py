# ruff: noqa: S101

import asyncio
from pathlib import Path

from src.meta import Meta
from src.screenshot_review import (
    _disc_bdinfo_for_group,
    add_screenshot,
    apply_staged_remote_uploads,
    delete_screenshot,
    image_version,
    list_review_items,
    list_screenshots,
    staged_remote_uploads,
    target_count,
    undo_remote_replacement,
)


def test_disc_group_resolves_its_own_bdinfo() -> None:
    meta = Meta(
        is_disc="BDMV",
        bdinfo={"source": "main"},
        discs=[{"bdinfo": {"source": "main"}, "bdinfo_1": {"source": "playlist"}}, {"bdinfo": {"source": "disc"}}],
    )

    assert _disc_bdinfo_for_group(meta, "main") == {"source": "main"}
    assert _disc_bdinfo_for_group(meta, "PLAYLIST_1") == {"source": "playlist"}
    assert _disc_bdinfo_for_group(meta, "FILE_1") == {"source": "disc"}
    assert _disc_bdinfo_for_group(meta, "Legacy title") == {"source": "main"}


def test_delete_screenshot_compacts_numbering_and_persists_target(tmp_path: Path) -> None:
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()
    for index in range(3):
        (screenshots_dir / f"Release-{index}.png").write_bytes(b"png")

    items = list_screenshots(tmp_path, {"is_disc": ""})
    remaining = delete_screenshot(tmp_path, {"is_disc": ""}, items[1].id)

    assert [item.path.name for item in remaining] == ["Release-0.png", "Release-1.png"]
    assert target_count(tmp_path, 3) == 2
    assert [item.path.name for item in list_screenshots(tmp_path, {"is_disc": ""})] == ["Release-0.png", "Release-1.png"]


def test_delete_disc_screenshot_does_not_renumber_other_groups(tmp_path: Path) -> None:
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()
    first = screenshots_dir / "Disc-0.png"
    second = screenshots_dir / "PLAYLIST_1-0.png"
    first.write_bytes(b"png")
    second.write_bytes(b"png")

    first_item = next(item for item in list_screenshots(tmp_path, {"is_disc": "BDMV"}) if item.path == first)
    delete_screenshot(tmp_path, {"is_disc": "BDMV"}, first_item.id)

    assert second.exists()
    assert second.name == "PLAYLIST_1-0.png"


def test_list_screenshots_includes_disc_video_frames_with_stable_opaque_ids(tmp_path: Path) -> None:
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()
    (screenshots_dir / "Release-0.png").write_bytes(b"png")
    artwork_dir = tmp_path / "artwork"
    artwork_dir.mkdir()
    (artwork_dir / "POSTER.png").write_bytes(b"png")
    (screenshots_dir / "Release-libplacebo-test.png").write_bytes(b"png")

    regular = list_screenshots(tmp_path, {"is_disc": ""})
    disc = list_screenshots(tmp_path, {"is_disc": "BDMV"})
    assert len(regular) == 1
    assert len(disc) == 1
    assert regular[0].id == disc[0].id
    assert regular[0].id.startswith("local-")


def test_add_bdmv_screenshot_uses_disc_capture_and_opaque_id(tmp_path: Path, monkeypatch) -> None:
    release_id = "release"
    screenshots_dir = tmp_path / "tmp" / release_id / "screenshots"
    screenshots_dir.mkdir(parents=True)
    existing = screenshots_dir / "Movie-0.png"
    existing.write_bytes(b"initial")
    meta_data = {"base_dir": str(tmp_path), "uuid": release_id, "is_disc": "BDMV", "bdinfo": {}, "filename": "Movie"}

    async def capture_stub(_meta, prefix, _bdinfo, folder_id, base_dir, *_args):
        path = Path(base_dir) / "tmp" / folder_id / "screenshots" / f"{prefix}-0.png"
        path.write_bytes(b"new")
        from src.screenshot_manifest import register

        return register(base_dir, folder_id, [path], "main")

    monkeypatch.setattr("src.screenshot_review.disc_screenshots", capture_stub)
    from src.screenshot_manifest import register

    register(tmp_path, release_id, [existing], "main")
    addition = asyncio.run(add_screenshot(tmp_path / "tmp" / release_id, meta_data))

    assert addition.id.startswith("local-")
    assert addition.path is not None and addition.path.is_file()
    assert addition.path.name.endswith(".png")
    assert len(addition.path.stem) == 32
    assert addition.path != screenshots_dir / existing.name


def test_disc_review_keeps_late_local_playlist_frames_visible_with_remote_images(tmp_path: Path) -> None:
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()
    (screenshots_dir / "playlist-frame-0.png").write_bytes(b"png")
    meta_data = {"is_disc": "BDMV", "image_list": [{"raw_url": "https://images.example/main.png"}]}

    items = list_review_items(tmp_path, meta_data)

    assert [(item.source, item.path is not None) for item in items] == [("remote", False), ("local", True)]


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


def test_add_after_deleting_earlier_remote_addition_uses_unique_id(tmp_path: Path, monkeypatch) -> None:
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()
    for index in range(2):
        (screenshots_dir / f"review-remote-add-{index}.png").write_bytes(b"png")
    (tmp_path / "screenshot_review.json").write_text(
        '{"remote_additions": [{"id": "remote-add-0", "file": "review-remote-add-0.png"}, {"id": "remote-add-1", "file": "review-remote-add-1.png"}]}',
        encoding="utf-8",
    )
    meta_data = {"image_list": [{"img_url": "https://images.example/one.jpg", "raw_url": "https://images.example/one.jpg"}]}

    async def capture_stub(_temp_dir, _meta_data, target):
        target.path.write_bytes(b"new png")
        return 1.0

    monkeypatch.setattr("src.screenshot_review._capture_fresh_frame", capture_stub)
    delete_screenshot(tmp_path, meta_data, "remote-add-0")
    addition = asyncio.run(add_screenshot(tmp_path, meta_data))

    assert addition.id.startswith("remote-add-")
    assert addition.id not in {"remote-add-0", "remote-add-1"}
    assert [item.id for item in list_review_items(tmp_path, meta_data)] == ["remote-0", "remote-add-1", addition.id]


def test_apply_staged_remote_uploads_preserves_later_review_changes(tmp_path: Path) -> None:
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()
    first = screenshots_dir / "review-remote-0.png"
    second = screenshots_dir / "review-remote-1.png"
    first.write_bytes(b"first")
    (tmp_path / "screenshot_review.json").write_text('{"remote_replacements": {"remote-0": "review-remote-0.png"}}', encoding="utf-8")
    image_list = [
        {"img_url": "https://images.example/one.jpg", "raw_url": "https://images.example/one.jpg"},
        {"img_url": "https://images.example/two.jpg", "raw_url": "https://images.example/two.jpg"},
    ]

    pending = staged_remote_uploads(tmp_path, image_list)
    second.write_bytes(b"second")
    (tmp_path / "screenshot_review.json").write_text('{"remote_replacements": {"remote-0": "review-remote-0.png", "remote-1": "review-remote-1.png"}}', encoding="utf-8")

    apply_staged_remote_uploads(tmp_path, image_list, [{"img_url": "https://new.example/one.jpg", "raw_url": "https://new.example/one.jpg"}], pending)

    assert staged_remote_uploads(tmp_path, image_list) == [(1, second)]
