# ruff: noqa: S101

import asyncio
from itertools import pairwise
from pathlib import Path
from unittest.mock import patch

import pytest

from src.meta import Meta
from src.uploadscreens import _build_image_start_limiter, _upload_screens


def test_image_start_limiter_staggers_concurrent_starts() -> None:
    async def exercise() -> list[float]:
        limiter = _build_image_start_limiter(0.02)
        starts: list[float] = []

        async def start_upload() -> None:
            await limiter()
            starts.append(asyncio.get_running_loop().time())

        await asyncio.gather(*(start_upload() for _ in range(3)))
        return starts

    starts = sorted(asyncio.run(exercise()))
    assert all(later - earlier >= 0.015 for earlier, later in pairwise(starts))


def test_upload_screens_does_not_reupload_source_on_fallback(tmp_path: Path) -> None:
    calls: list[str] = []

    async def fake_upload(args: object) -> dict[str, str]:
        image = str(args[0]) if isinstance(args, list) else ""
        calls.append(image)
        return {
            "status": "success",
            "img_url": f"https://img.example/{len(calls)}.png",
            "raw_url": f"https://img.example/{len(calls)}.png",
            "web_url": f"https://img.example/{len(calls)}.png",
        }

    async def exercise() -> None:
        image_path = tmp_path / "image-1.png"
        image_path.write_bytes(b"image")
        meta = Meta({"base_dir": str(tmp_path), "uuid": "test", "imghost": "imgbox"})
        config = {
            "DEFAULT": {
                "img_host_1": "imgbox",
                "img_host_2": "ptscreens",
                "image_upload_concurrency": 1,
                "image_upload_delay": 0,
            },
            "TRACKERS": {},
        }
        shared_return_dict: dict[str, object] = {}
        with (
            patch("src.uploadscreens.screenshots_dir", return_value=tmp_path),
            patch("src.uploadscreens.os.chdir"),
            patch("src.uploadscreens.Path.cwd", return_value=tmp_path),
            patch("src.uploadscreens.upload_image_task", new=fake_upload),
        ):
            await _upload_screens(config, meta, 1, 1, 0, 1, [], shared_return_dict)
            meta.image_list = []
            meta.imghost = "ptscreens"
            await _upload_screens(config, meta, 1, 2, 0, 1, [], shared_return_dict)

    asyncio.run(exercise())
    assert calls == ["image-1.png"]


def test_upload_screens_accepts_manifest_paths_outside_working_directory(tmp_path: Path) -> None:
    uploaded: list[str] = []

    async def fake_upload(args: object) -> dict[str, str]:
        assert isinstance(args, list)
        uploaded.append(str(args[0]))
        return {
            "status": "success",
            "img_url": "https://img.example/image.png",
            "raw_url": "https://img.example/image.png",
            "web_url": "https://img.example/image.png",
        }

    async def exercise() -> None:
        source_screenshots = tmp_path / "source" / "screenshots"
        state_screenshots = tmp_path / "state" / "tmp" / "release" / "screenshots"
        source_screenshots.mkdir(parents=True)
        state_screenshots.mkdir(parents=True)
        screenshot = state_screenshots / "image.png"
        screenshot.write_bytes(b"image")
        meta = Meta({"base_dir": str(tmp_path), "uuid": "release", "imghost": "imgbox"})
        config = {"DEFAULT": {"img_host_1": "imgbox", "image_upload_delay": 0}, "TRACKERS": {}}

        with (
            patch("src.uploadscreens.screenshots_dir", return_value=source_screenshots),
            patch("src.uploadscreens.os.chdir"),
            patch("src.uploadscreens.Path.cwd", return_value=source_screenshots),
            patch("src.uploadscreens.manifest_files", return_value=[screenshot]),
            patch("src.uploadscreens.upload_image_task", new=fake_upload),
        ):
            await _upload_screens(config, meta, 1, 1, 0, 1, [], {})

        assert uploaded == [str(screenshot)]

    asyncio.run(exercise())


def test_upload_screens_preserves_partial_successes_across_fallback(tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []

    async def fake_upload(args: object) -> dict[str, str]:
        assert isinstance(args, list)
        image = str(args[0])
        host = str(args[1])
        filename = Path(image).name
        calls.append((filename, host))
        if filename == "image-2.png" and host == "imgbox":
            return {"status": "failed", "reason": "duplicate image"}
        return {
            "status": "success",
            "img_url": f"https://img.example/{filename}/{host}",
            "raw_url": f"https://img.example/{filename}/{host}",
            "web_url": f"https://img.example/{filename}/{host}",
        }

    async def exercise() -> tuple[list[dict[str, str]], int]:
        for filename in ("image-1.png", "image-2.png"):
            (tmp_path / filename).write_bytes(b"image")
        meta = Meta({"base_dir": str(tmp_path), "uuid": "test", "imghost": "imgbox"})
        config = {
            "DEFAULT": {
                "img_host_1": "imgbox",
                "img_host_2": "ptscreens",
                "image_upload_concurrency": 1,
                "image_upload_delay": 0,
            },
            "TRACKERS": {},
        }
        with (
            patch("src.uploadscreens.screenshots_dir", return_value=tmp_path),
            patch("src.uploadscreens.os.chdir"),
            patch("src.uploadscreens.Path.cwd", return_value=tmp_path),
            patch("src.uploadscreens.upload_image_task", new=fake_upload),
        ):
            return await _upload_screens(config, meta, 1, 1, 0, 2, [], {})

    image_list, uploaded_count = asyncio.run(exercise())
    assert uploaded_count == 2
    assert len(image_list) == 2
    assert calls == [("image-1.png", "imgbox"), ("image-2.png", "imgbox"), ("image-2.png", "ptscreens")]


def test_upload_screens_handles_infinite_concurrency(tmp_path: Path) -> None:
    async def fake_upload(_: object) -> dict[str, str]:
        return {
            "status": "success",
            "img_url": "https://img.example/image.png",
            "raw_url": "https://img.example/image.png",
            "web_url": "https://img.example/image.png",
        }

    async def exercise() -> tuple[list[dict[str, str]], int]:
        meta = Meta({"base_dir": str(tmp_path), "uuid": "test", "imghost": "imgbox"})
        config = {
            "DEFAULT": {
                "img_host_1": "imgbox",
                "image_upload_concurrency": float("inf"),
                "image_upload_delay": 0,
            },
            "TRACKERS": {},
        }
        with (
            patch("src.uploadscreens.screenshots_dir", return_value=tmp_path),
            patch("src.uploadscreens.os.chdir"),
            patch("src.uploadscreens.upload_image_task", new=fake_upload),
        ):
            return await _upload_screens(config, meta, 1, 1, 0, 1, ["image.png"], {})

    result = asyncio.run(exercise())
    assert result[1] == 1


@pytest.mark.parametrize(
    ("configured_delay", "expected_delay"),
    [
        (float("inf"), 0.0),
        (float("-inf"), 0.0),
        (float("nan"), 0.0),
        (0.75, 0.75),
    ],
)
def test_upload_screens_normalizes_image_upload_delay_before_limiter(
    tmp_path: Path,
    configured_delay: float,
    expected_delay: float,
) -> None:
    async def fake_upload(_: object) -> dict[str, str]:
        return {
            "status": "success",
            "img_url": "https://img.example/image.png",
            "raw_url": "https://img.example/image.png",
            "web_url": "https://img.example/image.png",
        }

    async def exercise() -> tuple[list[float], int]:
        meta = Meta({"base_dir": str(tmp_path), "uuid": "test", "imghost": "imgbox"})
        config = {
            "DEFAULT": {
                "img_host_1": "imgbox",
                "image_upload_concurrency": 1,
                "image_upload_delay": configured_delay,
            },
            "TRACKERS": {},
        }
        captured_delays: list[float] = []

        def fake_build_image_start_limiter(delay: float):
            captured_delays.append(delay)

            async def wait_for_start_slot() -> None:
                return None

            return wait_for_start_slot

        with (
            patch("src.uploadscreens.screenshots_dir", return_value=tmp_path),
            patch("src.uploadscreens.os.chdir"),
            patch("src.uploadscreens.upload_image_task", new=fake_upload),
            patch("src.uploadscreens._build_image_start_limiter", side_effect=fake_build_image_start_limiter),
        ):
            return captured_delays, (await _upload_screens(config, meta, 1, 1, 0, 1, ["image.png"], {}))[1]

    delays, uploaded_count = asyncio.run(exercise())
    assert delays == [expected_delay]
    assert uploaded_count == 1
