# ruff: noqa: S101

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src import disc_menus
from src.disc_menus import DiscMenus, discard_previous_menu_capture_files
from src.meta import Meta


@pytest.mark.asyncio
async def test_local_menu_images_keep_filename_order_through_upload_and_save(monkeypatch, tmp_path) -> None:
    menu_dir = tmp_path / "menus"
    menu_dir.mkdir()
    image_paths = [menu_dir / name for name in ("menu-02.png", "menu-01.png", "menu-03.png", "notes.txt")]
    for path in image_paths:
        path.write_bytes(b"image")

    monkeypatch.setattr(Path, "iterdir", lambda _path: iter(image_paths))
    expected_names = ["menu-01.png", "menu-02.png", "menu-03.png"]
    uploaded_images = [{"raw_url": f"https://img.example/{name}"} for name in expected_names]
    upload = AsyncMock(return_value=(uploaded_images, len(uploaded_images)))
    meta = Meta(base_dir=str(tmp_path), uuid="menu-order", path_to_menu_screenshots=str(menu_dir))
    manager = DiscMenus(meta, {})
    monkeypatch.setattr(manager.uploadscreens_manager, "upload_screens", upload)

    await manager.get_local_images(meta)

    upload.assert_awaited_once()
    assert [path.name for path in upload.await_args.kwargs["custom_img_list"]] == expected_names
    assert meta.menu_images == uploaded_images
    saved_images = json.loads((tmp_path / "tmp" / "menu-order" / "menu_images.json").read_text())
    assert saved_images == {"menu_images": uploaded_images}


def test_discard_previous_menu_capture_files_only_removes_the_current_vob_batch(tmp_path) -> None:
    current_first = tmp_path / "DVD-VIDEO_TS-001.png"
    current_second = tmp_path / "DVD-VIDEO_TS-002.png"
    other_vob = tmp_path / "DVD-VTS_01_0-001.png"
    current_first.write_bytes(b"old")
    current_second.write_bytes(b"old")
    other_vob.write_bytes(b"keep")

    discard_previous_menu_capture_files(tmp_path / "DVD-VIDEO_TS-%03d.png")

    assert not current_first.exists()
    assert not current_second.exists()
    assert other_vob.exists()


@pytest.mark.asyncio
async def test_dvd_menu_capture_uses_dvd_par_override(monkeypatch, tmp_path) -> None:
    disc_path = tmp_path / "VIDEO_TS"
    disc_path.mkdir()
    (disc_path / "VTS_01_0.VOB").write_bytes(b"v" * 50001)
    commands = []

    def parse_stub(_path):
        video = SimpleNamespace(track_type="Video", width=720, height=480, pixel_aspect_ratio=1.2, display_aspect_ratio=1.8, duration=1000)
        return SimpleNamespace(tracks=[video])

    async def subprocess_stub(*args, **_kwargs):
        commands.append(args)

        async def communicate():
            return b"", b""

        return SimpleNamespace(returncode=0, communicate=communicate)

    monkeypatch.setattr(disc_menus.MediaInfo, "parse", parse_stub)
    monkeypatch.setattr(disc_menus.asyncio, "create_subprocess_exec", subprocess_stub)
    meta = Meta(base_dir=str(tmp_path), uuid="dvd", discs=[{"type": "DVD", "path": str(disc_path), "name": "DVD"}])
    manager = DiscMenus(meta, {"DEFAULT": {"scale_screenshots_for_par": False, "scale_dvd_screenshots_for_par": True}})

    await manager.auto_capture_dvd_menus(meta)

    assert len(commands) == 1
    assert "scale=864:480,format=rgb24" in commands[0][commands[0].index("-vf") + 1]
