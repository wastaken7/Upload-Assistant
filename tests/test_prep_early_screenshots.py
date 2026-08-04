# ruff: noqa: S101

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.meta import Meta
from src.prep import Prep
from src.screenshot_manifest import register
from src.takescreens import screenshots
from src.uploadscreens import _upload_screens


class _TakeScreens:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def screenshots(self, *_args: object, **_kwargs: object) -> None:
        self.calls.append((_args, _kwargs))

    async def disc_screenshots(self, *_args: object, **_kwargs: object) -> None:
        self.calls.append((_args, _kwargs))


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

    assert screenshot_spy.calls == []


def test_early_screenshots_remain_enabled_without_description_images() -> None:
    prep, screenshot_spy = _prep_with_screenshot_spy()
    meta = Meta(category="MOVIE", keep_images=False, screens=6)

    asyncio.run(prep._capture_early_screenshots(meta, "Release", "C:/media/Release.mkv", {}))

    assert len(screenshot_spy.calls) == 1
    assert screenshot_spy.calls[0][1]["capture_group"] == "main"


def test_registered_main_screenshots_are_reused_when_title_changes(tmp_path: Path) -> None:
    release_id = "release"
    screenshot_dir = tmp_path / "tmp" / release_id / "screenshots"
    screenshot_dir.mkdir(parents=True)
    original_paths = []
    for index in range(2):
        image = screenshot_dir / f"unpunctuated-title-{index}.png"
        image.write_bytes(b"image")
        original_paths.append(image)
    registered = register(tmp_path, release_id, original_paths, "main")
    meta = Meta(category="MOVIE", base_dir=str(tmp_path), uuid=release_id, screens=6, imghost="imgbb")

    with patch("src.takescreens.get_image_host", new=AsyncMock(return_value="imgbb")):
        result = asyncio.run(screenshots("unused.mkv", "Punctuated, Title", release_id, str(tmp_path), meta, manual_frames=[100, 200]))

    assert set(result or []) == {str(path) for path in registered}


def test_partial_registered_group_captures_only_missing_screenshots(tmp_path: Path) -> None:
    release_id = "release"
    release_dir = tmp_path / "tmp" / release_id
    screenshot_dir = release_dir / "screenshots"
    screenshot_dir.mkdir(parents=True)
    (release_dir / "MediaInfo.json").write_text(
        '{"media": {"track": [{"Duration": "100"}, {"Duration": "100", "Width": "1920", "Height": "1080", "PixelAspectRatio": "1", "DisplayAspectRatio": "1.777", "FrameRate": "24"}]}}',
        encoding="utf-8",
    )
    existing = []
    for index in range(2):
        image = screenshot_dir / f"existing-{index}.png"
        image.write_bytes(b"image")
        existing.append(image)
    register(tmp_path, release_id, existing, "main")
    meta = Meta(category="MOVIE", base_dir=str(tmp_path), uuid=release_id, screens=3, imghost="imgbb")
    capture_calls: list[object] = []

    async def capture_stub(args: tuple[object, ...]):
        capture_calls.append(args)
        output = Path(str(args[3]))
        output.write_bytes(b"image")
        return args[0], str(output)

    with (
        patch("src.takescreens.get_image_host", new=AsyncMock(return_value="imgbb")),
        patch("src.takescreens.capture_screenshot", new=capture_stub),
    ):
        result = asyncio.run(screenshots("unused.mkv", "Punctuated, Title", release_id, str(tmp_path), meta, manual_frames=[100, 200, 300]))

    assert len(capture_calls) == 1
    assert len(result or []) == 3


@pytest.mark.asyncio
async def test_successful_screenshot_capture_preserves_unrelated_child(tmp_path: Path) -> None:
    release_id = "release"
    release_dir = tmp_path / "tmp" / release_id
    release_dir.mkdir(parents=True)
    (release_dir / "MediaInfo.json").write_text(
        '{"media": {"track": [{"Duration": "100"}, {"Duration": "100", "Width": "1920", "Height": "1080", "PixelAspectRatio": "1", "DisplayAspectRatio": "1.777", "FrameRate": "24"}]}}',
        encoding="utf-8",
    )
    meta = Meta(category="MOVIE", base_dir=str(tmp_path), uuid=release_id, screens=1, imghost="imgbb")

    async def capture_stub(args: tuple[object, ...]):
        output = Path(str(args[3]))
        output.write_bytes(b"image" * 20000)
        return args[0], str(output)

    unrelated = await asyncio.create_subprocess_exec(sys.executable, "-c", "import time; time.sleep(60)")
    try:
        with (
            patch("src.takescreens.get_image_host", new=AsyncMock(return_value="imgbb")),
            patch("src.takescreens.capture_screenshot", new=capture_stub),
        ):
            result = await screenshots("unused.mkv", "Release", release_id, str(tmp_path), meta, manual_frames=[100], cleanup_after_capture=False)

        assert len(result or []) == 1
        for _ in range(100):
            if unrelated.returncode is not None:
                break
            await asyncio.sleep(0.01)
        assert unrelated.returncode is None, "successful screenshot capture terminated an unrelated child process"
    finally:
        if unrelated.returncode is None:
            unrelated.terminate()
        try:
            await asyncio.wait_for(unrelated.wait(), timeout=3)
        except TimeoutError:
            unrelated.kill()
            await unrelated.wait()


def test_upload_uses_only_registered_main_screenshots(tmp_path: Path, monkeypatch) -> None:
    release_id = "release"
    screenshot_dir = tmp_path / "tmp" / release_id / "screenshots"
    screenshot_dir.mkdir(parents=True)
    main_source = screenshot_dir / "main.png"
    file_source = screenshot_dir / "file.png"
    main_source.write_bytes(b"main")
    file_source.write_bytes(b"file")
    main_screen = register(tmp_path, release_id, [main_source], "main")[0]
    register(tmp_path, release_id, [file_source], "FILE_1")
    meta = Meta(base_dir=str(tmp_path), uuid=release_id, imghost="imgbb", image_list=[])
    calls: list[str] = []

    async def upload_stub(args: list[object]) -> dict[str, str]:
        calls.append(str(args[0]))
        return {"status": "success", "img_url": "https://images.example/main.png", "raw_url": "https://images.example/main.png", "web_url": "https://images.example/main.png"}

    config = {"DEFAULT": {"img_host_1": "imgbb"}, "TRACKERS": {}}
    monkeypatch.chdir(screenshot_dir)
    with patch("src.uploadscreens.upload_image_task", new=upload_stub):
        _, uploaded_count = asyncio.run(_upload_screens(config, meta, 1, 1, 0, 1, [], {}))

    assert uploaded_count == 1
    assert calls == [main_screen.name]


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

    assert len(screenshot_spy.calls) == 2
    assert screenshot_spy.calls[0][1]["capture_group"] == "main"
    assert screenshot_spy.calls[1][0][-1] == "PLAYLIST_1"


def test_early_bdmv_capture_includes_extra_discs() -> None:
    prep, screenshot_spy = _prep_with_screenshot_spy()
    meta = Meta(
        category="MOVIE",
        keep_images=False,
        screens=6,
        is_disc="BDMV",
        discs=[{"bdinfo": {}}, {"type": "BDMV", "bdinfo": {}}],
    )

    asyncio.run(prep._capture_early_screenshots(meta, "Release", "", {}))

    assert len(screenshot_spy.calls) == 2
    assert screenshot_spy.calls[1][0][-1] == "FILE_1"
