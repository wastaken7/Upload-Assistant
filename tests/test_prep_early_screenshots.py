# ruff: noqa: S101

import asyncio

from src.meta import Meta
from src.prep import Prep


class _TakeScreens:
    def __init__(self) -> None:
        self.calls = 0

    async def screenshots(self, *_args: object, **_kwargs: object) -> None:
        self.calls += 1

    async def disc_screenshots(self, *_args: object, **_kwargs: object) -> None:
        self.calls += 1


def _prep_with_screenshot_spy() -> tuple[Prep, _TakeScreens]:
    prep = Prep.__new__(Prep)
    screenshot_spy = _TakeScreens()
    prep.takescreens_manager = screenshot_spy
    prep.config = {"DEFAULT": {"multiScreens": 2}}
    return prep, screenshot_spy


def test_early_screenshots_wait_for_description_images() -> None:
    prep, screenshot_spy = _prep_with_screenshot_spy()
    meta = Meta(category="MOVIE", keep_images=True, screens=6)

    asyncio.run(prep._capture_early_screenshots(meta, "Release", "C:/media/Release.mkv", {}))

    assert screenshot_spy.calls == 0


def test_early_screenshots_remain_enabled_without_description_images() -> None:
    prep, screenshot_spy = _prep_with_screenshot_spy()
    meta = Meta(category="MOVIE", keep_images=False, screens=6)

    asyncio.run(prep._capture_early_screenshots(meta, "Release", "C:/media/Release.mkv", {}))

    assert screenshot_spy.calls == 1


def test_early_bdmv_capture_includes_alternate_playlists() -> None:
    prep, screenshot_spy = _prep_with_screenshot_spy()
    meta = Meta(
        category="MOVIE",
        keep_images=False,
        screens=6,
        is_disc="BDMV",
        discs=[{"bdinfo": {}, "bdinfo_1": {}}],
    )

    asyncio.run(prep._capture_early_screenshots(meta, "Release", "", {}))

    assert screenshot_spy.calls == 2
