# ruff: noqa: S101

import asyncio
import json
from pathlib import Path

import pytest

from src.meta import Meta
from src.screenshot_manifest import files as manifest_files
from src.screenshot_manifest import register
from src.screenshot_review import (
    ReviewedScreenshot,
    _capture_fresh_frame,
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
from src.takescreens import disc_screenshots, screenshots
from src.temp_paths import screenshots_dir
from src.uploadscreens import _upload_screens


@pytest.fixture
def release_dir(tmp_path):
    return screenshots_dir(tmp_path, "release").parent


def _register_images(release_dir, names, group="main"):
    paths = [release_dir / "screenshots" / name for name in names]
    for path in paths:
        path.write_bytes(b"png")
    return register(release_dir.parent.parent, release_dir.name, paths, group)


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


@pytest.mark.parametrize("is_disc", ["", "BDMV"])
def test_delete_registered_screenshot_preserves_other_files_and_target(release_dir, is_disc):
    paths = _register_images(release_dir, ["first.png", "second.png", "third.png"])
    extra = _register_images(release_dir, ["extra.png"], "FILE_1")[0]
    items = list_screenshots(release_dir, {"is_disc": is_disc})
    target = next(item for item in items if item.path == paths[1])

    remaining = delete_screenshot(release_dir, {"is_disc": is_disc}, target.id)

    assert {item.path for item in remaining} == {paths[0], paths[2], extra}
    assert set(manifest_files(release_dir.parent.parent, release_dir.name, "main")) == {paths[0], paths[2]}
    assert not target.path.exists()
    assert target_count(release_dir, 3) == 2
    manifest = json.loads((release_dir / "screenshot_manifest.json").read_text())
    assert len(manifest["screenshots"]) == 3


def test_delete_disc_screenshot_preserves_main_target_and_other_groups(release_dir):
    main = _register_images(release_dir, ["main.png"])[0]
    extra = _register_images(release_dir, ["extra.png"], "PLAYLIST_1")[0]
    target = next(item for item in list_screenshots(release_dir, {}) if item.path == extra)

    remaining = delete_screenshot(release_dir, {"is_disc": "BDMV"}, target.id)

    assert [item.path for item in remaining] == [main]
    assert target_count(release_dir, 6) == 6
    assert manifest_files(release_dir.parent.parent, release_dir.name, "PLAYLIST_1") == []


def test_list_screenshots_only_includes_registered_frames_with_stable_ids(release_dir):
    screenshot = _register_images(release_dir, ["frame.png"])[0]
    for name in ("stray.png", "POSTER.jpg", "frame-libplacebo-test.png"):
        (release_dir / "screenshots" / name).write_bytes(b"png")
    _register_images(release_dir, ["old.png"], "Example Title")

    regular = list_screenshots(release_dir, {"is_disc": ""})
    disc = list_screenshots(release_dir, {"is_disc": "BDMV"})
    assert len(regular) == 1
    assert len(disc) == 1
    assert regular[0].path == screenshot
    assert regular[0].id == disc[0].id
    assert regular[0].id.startswith("local-")


def test_list_screenshots_includes_registered_webp_contact_sheets(release_dir):
    webp = _register_images(release_dir, ["contact-sheet.webp"])[0]

    items = list_screenshots(release_dir, {"category": "XXX"})

    assert [item.path for item in items] == [webp]


def test_list_screenshots_uses_manifest_order_for_jpeg_and_webp_frames(release_dir):
    _register_images(release_dir, ["first.jpg", "second.webp"])

    items = list_screenshots(release_dir, {"category": "XXX"})

    assert [item.path for item in items] == manifest_files(release_dir.parent.parent, release_dir.name)


@pytest.mark.parametrize("group", ["main", "FILE_1"])
def test_add_bdmv_screenshot_uses_disc_capture_and_updates_main_target(tmp_path: Path, monkeypatch, group) -> None:
    release_id = "release"
    screenshots_dir = tmp_path / "tmp" / release_id / "screenshots"
    screenshots_dir.mkdir(parents=True)
    existing = screenshots_dir / "Movie-0.png"
    existing.write_bytes(b"initial")
    meta_data = {"base_dir": str(tmp_path), "uuid": release_id, "is_disc": "BDMV", "bdinfo": {}, "discs": [{"bdinfo": {}}, {"bdinfo": {}}], "filename": "Movie"}

    async def capture_stub(_meta, prefix, _bdinfo, folder_id, base_dir, *_args):
        path = Path(base_dir) / "tmp" / folder_id / "screenshots" / f"{prefix}-0.png"
        path.write_bytes(b"new")
        return register(base_dir, folder_id, [path], _args[-1])

    monkeypatch.setattr("src.screenshot_review.disc_screenshots", capture_stub)
    register(tmp_path, release_id, [existing], "main")
    addition = asyncio.run(add_screenshot(tmp_path / "tmp" / release_id, meta_data, group))

    assert addition.id.startswith("local-")
    assert addition.path is not None and addition.path.is_file()
    assert addition.path.name.endswith(".png")
    assert len(addition.path.stem) == 32
    assert addition.path != screenshots_dir / existing.name
    assert addition.group == group
    assert target_count(screenshots_dir.parent, 6) == (2 if group == "main" else 6)


@pytest.mark.asyncio
@pytest.mark.parametrize("is_disc", ["", "BDMV"])
async def test_local_add_delete_survive_capture_reuse_and_upload(release_dir, monkeypatch, is_disc):
    paths = _register_images(release_dir, ["first.png", "second.png"])
    meta = Meta(base_dir=str(release_dir.parent.parent), uuid=release_dir.name, screens=6, imghost="imgbox", is_disc=is_disc)

    async def capture(_temp_dir, _meta_data, target):
        target.path.write_bytes(b"added")
        return 12.5

    uploaded = []

    async def host(args):
        uploaded.append(Path(args[0]))
        url = f"https://images.example/{Path(args[0]).name}"
        return {"status": "success", "img_url": url, "raw_url": url, "web_url": url}

    monkeypatch.setattr("src.screenshot_review._capture_fresh_frame", capture)
    monkeypatch.setattr("src.uploadscreens.upload_image_task", host)
    addition = await add_screenshot(release_dir, {**meta.to_dict(), "is_disc": ""})
    assert len(addition.path.stem) == 32
    assert addition.path in manifest_files(meta.base_dir, meta.uuid, "main")
    assert target_count(release_dir, 6) == 3
    target = next(item for item in list_screenshots(release_dir, {}) if item.path == paths[0])
    delete_screenshot(release_dir, meta.to_dict(), target.id)

    if is_disc:
        bdinfo = {"files": [], "video": [{"codec": "AVC", "hdr_dv": ""}]}
        await disc_screenshots(meta, "Changed Title", bdinfo, meta.uuid, meta.base_dir, False)
    else:
        reused = await screenshots("unused.mkv", "Changed Title", meta.uuid, meta.base_dir, meta)
        assert set(reused) == {str(paths[1]), str(addition.path)}
    images, count = await _upload_screens({"DEFAULT": {"img_host_1": "imgbox", "image_upload_delay": 0}}, meta, 2, 1, 0, 2, [], {})

    assert meta.screens == 2
    assert set(uploaded) == {paths[1], addition.path}
    assert len(images) == count == 2
    manifest = json.loads((release_dir / "screenshot_manifest.json").read_text())
    assert len(manifest["screenshots"]) == 2
    assert manifest["screenshots"][addition.path.stem]["timestamp"] == 12.5


def test_review_capture_uses_shared_tonemapping_decision(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.mkv"
    source.write_bytes(b"video")
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()
    target = ReviewedScreenshot("local-test", screenshots_dir / "frame.png", 0)
    captured: dict[str, object] = {}

    monkeypatch.setattr("src.screenshot_review._video_properties", lambda _temp_dir: (1920, 1080, 1, 1, 100, 24))

    async def determine_stub(*_args):
        meta = _args[-1]
        meta.tonemapped = True
        meta.libplacebo = True
        return True

    async def capture_stub(args):
        captured["tonemapped"] = args[-1].tonemapped
        captured["libplacebo"] = args[-1].libplacebo
        captured["hdr_tonemap"] = args[-2]
        Path(args[3]).write_bytes(b"tonemapped")
        return args[0], args[3]

    monkeypatch.setattr("src.screenshot_review.determine_tonemapping", determine_stub)
    monkeypatch.setattr("src.screenshot_review.capture_screenshot", capture_stub)

    asyncio.run(_capture_fresh_frame(tmp_path, {"filelist": [str(source)], "hdr": "HDR"}, target))

    assert captured == {"tonemapped": True, "libplacebo": True, "hdr_tonemap": True}
    assert target.path.read_bytes() == b"tonemapped"


def test_disc_review_keeps_local_playlist_frames_visible_with_remote_images(release_dir):
    _register_images(release_dir, ["playlist-frame.png"], "PLAYLIST_1")
    meta_data = {"is_disc": "BDMV", "image_list": [{"raw_url": "https://images.example/main.png"}]}

    items = list_review_items(release_dir, meta_data)

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


def test_undo_remote_replacement_removes_registered_frame(release_dir):
    replacement = _register_images(release_dir, ["replacement.png"])[0]
    (release_dir / "screenshot_review.json").write_text(json.dumps({"remote_replacements": {"remote-0": replacement.name}}), encoding="utf-8")
    meta_data = {"image_list": [{"img_url": "https://images.example/one.jpg", "raw_url": "https://images.example/one.jpg"}]}

    undo_remote_replacement(release_dir, "remote-0")

    assert not replacement.exists()
    assert [(item.id, item.source) for item in list_review_items(release_dir, meta_data)] == [("remote-0", "remote")]
    assert json.loads((release_dir / "screenshot_manifest.json").read_text())["screenshots"] == {}


def test_delete_remote_addition_discards_manifest_entry_and_pending_upload(release_dir):
    addition = _register_images(release_dir, ["addition.png"])[0]
    (release_dir / "screenshot_review.json").write_text(
        json.dumps({"remote_additions": [{"id": "remote-add-0", "file": addition.name}], "generations": {"remote-add-0": 1}}), encoding="utf-8"
    )
    meta_data = {"image_list": [{"img_url": "https://images.example/one.jpg", "raw_url": "https://images.example/one.jpg"}]}

    remaining = delete_screenshot(release_dir, meta_data, "remote-add-0")

    assert not addition.exists()
    assert [(item.id, item.source) for item in remaining] == [("remote-0", "remote")]
    assert staged_remote_uploads(release_dir, meta_data["image_list"]) == []
    assert json.loads((release_dir / "screenshot_manifest.json").read_text())["screenshots"] == {}


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
