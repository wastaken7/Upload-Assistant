# ruff: noqa: S101

import asyncio

from src.uploadscreens import _build_image_start_limiter


def test_image_start_limiter_staggers_concurrent_starts() -> None:
    async def exercise() -> list[float]:
        limiter = _build_image_start_limiter(0.02)
        starts: list[float] = []

        async def start_upload() -> None:
            await limiter()
            starts.append(asyncio.get_running_loop().time())

        await asyncio.gather(*(start_upload() for _ in range(3)))
        return starts

    starts = asyncio.run(exercise())
    assert all(later - earlier >= 0.015 for earlier, later in zip(starts, starts[1:]))
