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
        with patch("src.uploadscreens.screenshots_dir", return_value=tmp_path), patch("src.uploadscreens.os.chdir"), patch(
            "src.uploadscreens.upload_image_task", new=fake_upload
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

        with patch("src.uploadscreens.screenshots_dir", return_value=tmp_path), patch("src.uploadscreens.os.chdir"), patch(
            "src.uploadscreens.upload_image_task", new=fake_upload
        ), patch("src.uploadscreens._build_image_start_limiter", side_effect=fake_build_image_start_limiter):
            return captured_delays, (await _upload_screens(config, meta, 1, 1, 0, 1, ["image.png"], {}))[1]

    delays, uploaded_count = asyncio.run(exercise())
    assert delays == [expected_delay]
    assert uploaded_count == 1
