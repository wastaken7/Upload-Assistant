import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.configvalidator import _validate_trackers_section
from src.meta import Meta
from src.trackers.UNIT3D.capybarabr import CapybaraBR
from src.trackers.UNIT3D.samaritano import Samaritano


@pytest.mark.parametrize(
    "tracker_class",
    [CapybaraBR, Samaritano],
)
@pytest.mark.parametrize(
    ("audio_languages", "expected_tag"),
    [
        (["Japanese", "English"], ""),
        (["Portuguese", "Portuguese"], ""),
        (["Portuguese", "English"], "DUAL"),
        (["Portuguese", "English", "Japanese"], "MULTI"),
    ],
)
def test_brazilian_trackers_audio_tags_require_portuguese(tracker_class: type[CapybaraBR] | type[Samaritano], audio_languages: list[str], expected_tag: str) -> None:
    meta = Meta(
        category="TV",
        name="Example Show 2026 WEB-DL - GROUP",
        title="Example Show",
        year=2026,
        tag="-GROUP",
        audio_languages=audio_languages,
        dual_audio=True,
    )

    name = asyncio.run(tracker_class({"TRACKERS": {}}).get_name(meta))["name"]

    assert (" DUAL-" in name) == (expected_tag == "DUAL")  # noqa: S101
    assert (" MULTI-" in name) == (expected_tag == "MULTI")  # noqa: S101


def test_capybarabr_formats_dvdrips_with_resolution_before_audio_and_codec() -> None:
    meta = Meta(
        category="MOVIE",
        name="Example Movie 2001 DVD x264 DVDRip DD 2.0-DDOS",
        title="Example Movie",
        year=2001,
        type="DVDRIP",
        resolution="480p",
        audio="DD 2.0",
        video_encode="x264",
        tag="-DDOS",
    )

    name = asyncio.run(CapybaraBR({"TRACKERS": {}}).get_name(meta))["name"]

    assert name == "Example Movie 2001 480p DVDRip DD2.0 x264-DDOS"  # noqa: S101


def _samaritano_config(*, force: bool = True, image_host_api_key: str = "fictional-image-token") -> dict[str, object]:
    return {
        "DEFAULT": {"img_host_1": "imgbb"},
        "TRACKERS": {
            "SAMARITANO": {
                "api_key": "fictional-tracker-token",
                "image_host_api_key": image_host_api_key,
                "force_rehost_images": force,
            }
        },
    }


def test_samaritano_force_rehost_keeps_global_images_and_sets_tracker_collections(tmp_path) -> None:
    screenshot = tmp_path / "fictional-screen.png"
    menu = tmp_path / "fictional-menu.png"
    screenshot.write_bytes(b"screen")
    menu.write_bytes(b"menu")
    meta = Meta(
        category="MOVIE",
        image_list=[{"raw_url": "https://global.example/screen.png", "local_file_path": str(screenshot)}],
        menu_images=[{"raw_url": "https://global.example/menu.png", "local_file_path": str(menu)}],
    )
    original_screenshots = list(meta.image_list)
    original_menus = list(meta.menu_images)

    async def fake_upload(args: object) -> dict[str, str]:
        local_path = str(args[0])
        filename = local_path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
        return {
            "status": "success",
            "img_url": f"https://img.samaritano.cc/thumbnails/{filename}",
            "raw_url": f"https://img.samaritano.cc/uploads/{filename}",
            "web_url": f"https://img.samaritano.cc/uploads/{filename}",
        }

    tracker = Samaritano(_samaritano_config())
    with patch("src.trackers.UNIT3D.samaritano.upload_image_task", new=fake_upload):
        asyncio.run(tracker.check_image_hosts(meta))

    assert meta.image_list == original_screenshots  # noqa: S101
    assert meta.menu_images == original_menus  # noqa: S101
    assert meta.tracker_image_collections["SAMARITANO"]["screenshots"][0]["raw_url"].startswith("https://img.samaritano.cc/")  # noqa: S101
    assert meta.tracker_image_collections["SAMARITANO"]["menu_images"][0]["raw_url"].startswith("https://img.samaritano.cc/")  # noqa: S101


def test_samaritano_force_rehost_is_atomic_on_failure(tmp_path) -> None:
    screenshot = tmp_path / "fictional-screen.png"
    menu = tmp_path / "fictional-menu.png"
    screenshot.write_bytes(b"screen")
    menu.write_bytes(b"menu")
    meta = Meta(
        category="MOVIE",
        image_list=[{"raw_url": "https://global.example/screen.png", "local_file_path": str(screenshot)}],
        menu_images=[{"raw_url": "https://global.example/menu.png", "local_file_path": str(menu)}],
    )
    uploader = AsyncMock(
        side_effect=[
            {
                "status": "success",
                "img_url": "https://img.samaritano.cc/thumbnails/fictional-screen.png",
                "raw_url": "https://img.samaritano.cc/uploads/fictional-screen.png",
                "web_url": "https://img.samaritano.cc/uploads/fictional-screen.png",
            },
            {"status": "failed", "reason": "synthetic failure"},
        ]
    )

    tracker = Samaritano(_samaritano_config())
    with patch("src.trackers.UNIT3D.samaritano.upload_image_task", new=uploader):
        asyncio.run(tracker.check_image_hosts(meta))

    assert "SAMARITANO" not in meta.tracker_image_collections  # noqa: S101


@pytest.mark.parametrize(
    ("force", "image_host_api_key"),
    [(False, "fictional-image-token"), (True, "")],
)
def test_samaritano_does_not_rehost_when_disabled_or_unconfigured(force: bool, image_host_api_key: str) -> None:
    meta = Meta(category="MOVIE", image_list=[{"raw_url": "https://global.example/screen.png"}])
    uploader = AsyncMock()

    tracker = Samaritano(_samaritano_config(force=force, image_host_api_key=image_host_api_key))
    with patch("src.trackers.UNIT3D.samaritano.upload_image_task", new=uploader):
        asyncio.run(tracker.check_image_hosts(meta))

    uploader.assert_not_awaited()
    assert "SAMARITANO" not in meta.tracker_image_collections  # noqa: S101


def test_samaritano_force_rehost_config_must_be_boolean() -> None:
    errors, warnings = _validate_trackers_section(
        {"SAMARITANO": {"api_key": "fictional-tracker-token", "force_rehost_images": "yes"}},
        active_trackers=["SAMARITANO"],
    )

    assert errors == []  # noqa: S101
    assert any("'force_rehost_images' must be a boolean" in warning.message for warning in warnings)  # noqa: S101
