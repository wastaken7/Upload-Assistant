"""Regression coverage for tracker-specific image-host reuploads."""

# ruff: noqa: S101

import asyncio
from pathlib import Path
from typing import ClassVar
from unittest.mock import AsyncMock

from src.meta import Meta
from src.rehostimages import (
    ImageHostPolicy,
    RehostImagesManager,
    check_tracker_image_hosts,
    has_restricted_image_hosts,
    select_common_image_host,
)
from src.tracker_images import get_tracker_image_collection, has_tracker_image_collection


class _Alpha:
    image_host_policy = ImageHostPolicy({}, ("imgbox", "imgbb"))


class _Beta:
    image_host_policy = ImageHostPolicy({}, ("imgbb", "ptscreens"))


class _Unrestricted:
    pass


class _LegacySetPolicy:
    approved_image_hosts: ClassVar[set[str]] = {"imgbb", "onlyimage"}

    async def check_image_hosts(self, _meta: Meta) -> None:
        pass


class _PolicyTracker:
    tracker = "TEST"
    image_host_policy = ImageHostPolicy({}, ("imgbb",))

    def __init__(self) -> None:
        self.rehost_images_manager = AsyncMock()


def test_has_restricted_image_hosts() -> None:
    tracker_map = {
        "ALPHA": _Alpha,
        "BETA": _Beta,
        "UNRESTRICTED": _Unrestricted,
        "LEGACY": _LegacySetPolicy,
    }
    assert not has_restricted_image_hosts([], tracker_map)
    assert not has_restricted_image_hosts(["UNRESTRICTED"], tracker_map)
    assert has_restricted_image_hosts(["ALPHA"], tracker_map)
    assert has_restricted_image_hosts(["UNRESTRICTED", "LEGACY"], tracker_map)


def test_select_common_image_host_uses_first_configured_shared_host() -> None:
    selected = select_common_image_host(
        {"img_host_1": "imgbox", "img_host_2": "imgbb", "img_host_3": "ptscreens"},
        ["ALPHA", "BETA", "UNRESTRICTED"],
        {"ALPHA": _Alpha, "BETA": _Beta, "UNRESTRICTED": _Unrestricted},
    )

    assert selected == "imgbb"


def test_select_common_image_host_accepts_legacy_set_policy() -> None:
    selected = select_common_image_host(
        {"img_host_1": "imgbox", "img_host_2": "imgbb"},
        ["ALPHA", "LEGACY"],
        {"ALPHA": _Alpha, "LEGACY": _LegacySetPolicy},
    )

    assert selected == "imgbb"


def test_select_common_image_host_keeps_per_tracker_fallback_without_common_host() -> None:
    selected = select_common_image_host(
        {"img_host_1": "imgbox", "img_host_2": "ptscreens"},
        ["ALPHA", "BETA"],
        {"ALPHA": _Alpha, "BETA": _Beta},
    )

    assert selected is None


def test_music_does_not_rehost_missing_screenshots() -> None:
    tracker = _PolicyTracker()

    asyncio.run(check_tracker_image_hosts(Meta(category="MUSIC"), tracker))

    tracker.rehost_images_manager.check_policy.assert_not_awaited()


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
