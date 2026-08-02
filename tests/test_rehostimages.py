"""Regression coverage for tracker-specific image-host reuploads."""

# ruff: noqa: S101

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

from src.meta import Meta
from src.rehostimages import ImageHostPolicy, RehostImagesManager
from src.tracker_images import get_tracker_image_collection, has_tracker_image_collection


def test_rehosts_menu_and_spectrogram_images_without_touching_main_screens(tmp_path: Path):
    menu_source = tmp_path / "menu.png"
    spectrogram_source = tmp_path / "spectrogram.png"
    menu_source.write_bytes(b"menu")
    spectrogram_source.write_bytes(b"spectrogram")

    manager = RehostImagesManager({"DEFAULT": {"img_host_1": "imgbb"}})
    manager.uploadscreens_manager.upload_screens = AsyncMock(
        side_effect=[
            ([{"img_url": "https://i.ibb.co/menu.png", "raw_url": "https://i.ibb.co/menu.png", "web_url": "https://ibb.co/menu"}], 1),
            ([{"img_url": "https://i.ibb.co/spectrogram.png", "raw_url": "https://i.ibb.co/spectrogram.png", "web_url": "https://ibb.co/spectrogram"}], 1),
        ]
    )
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="release",
        imghost="lostimg",
        image_list=[{"raw_url": "https://i.ibb.co/main.png"}],
        menu_images=[{"raw_url": "https://lostimg.cc/menu.png", "local_file_path": str(menu_source)}],
        spectrograms_images=[{"raw_url": "https://lostimg.cc/spectrogram.png", "local_file_path": str(spectrogram_source)}],
    )

    assert not has_tracker_image_collection(meta, "TEST", "screenshots")

    result, _, _ = asyncio.run(
        manager.check_policy(
            meta,
            "TEST",
            ImageHostPolicy({"i.ibb.co": "imgbb", "lostimg.cc": "lostimg"}, ("imgbb",)),
        )
    )

    assert result == meta.image_list
    assert meta.image_list == [{"raw_url": "https://i.ibb.co/main.png"}]
    assert meta.menu_images[0]["raw_url"] == "https://lostimg.cc/menu.png"
    assert meta.spectrograms_images[0]["raw_url"] == "https://lostimg.cc/spectrogram.png"
    tracker_images = meta.tracker_image_collections["TEST"]
    assert has_tracker_image_collection(meta, "TEST", "screenshots")
    assert tracker_images["screenshots"] == meta.image_list
    assert tracker_images["screenshots"] is not meta.image_list
    assert tracker_images["screenshots"][0] is not meta.image_list[0]
    assert tracker_images["menu_images"][0]["raw_url"] == "https://i.ibb.co/menu.png"
    assert tracker_images["menu_images"][0]["local_file_path"] == str(menu_source)
    assert tracker_images["spectrograms_images"][0]["raw_url"] == "https://i.ibb.co/spectrogram.png"
    assert tracker_images["spectrograms_images"][0]["local_file_path"] == str(spectrogram_source)
    assert get_tracker_image_collection(meta, "TEST", "menu_images") == tracker_images["menu_images"]
    assert get_tracker_image_collection(meta, "OTHER", "menu_images") == meta.menu_images
    assert meta.imghost == "lostimg"

    calls = manager.uploadscreens_manager.upload_screens.await_args_list
    assert [call.args[5] for call in calls] == [[str(menu_source)], [str(spectrogram_source)]]
    assert all(call.kwargs["allowed_hosts"] == ["imgbb"] for call in calls)
