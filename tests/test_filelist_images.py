# ruff: noqa: S101

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.meta import Meta
from src.screenshot_manifest import register
from src.temp_paths import screenshots_dir
from src.trackers.filelist import FileList


@pytest.fixture
def image_host(monkeypatch):
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post.return_value = SimpleNamespace(text="Hosted screenshots")
    monkeypatch.setattr("src.trackers.filelist.httpx.AsyncClient", lambda **_kwargs: client)
    monkeypatch.setattr("src.trackers.filelist.get_base_description", lambda _meta: "Example description")
    return client.post


@pytest.mark.parametrize("is_disc", ["", "BDMV"])
def test_filelist_uploads_registered_primary_screenshots(tmp_path, image_host, is_disc):
    directory = screenshots_dir(tmp_path, "release")
    screenshot = directory / "Example-0.png"
    screenshot.write_bytes(b"png")
    screenshot = register(tmp_path, "release", [screenshot], "main")[0]
    (directory / "Example-1.png").write_bytes(b"stray")
    extra = directory / "extra.png"
    extra.write_bytes(b"extra")
    register(tmp_path, "release", [extra], "FILE_1")
    for name in ("MEDIAINFO_CLEANPATH.txt", "BD_SUMMARY_EXT.txt"):
        (directory.parent / name).write_text("Example summary", encoding="utf-8")
    tracker = FileList({"TRACKERS": {"FILELIST": {"fltools": {"user": "user", "pass": "password"}}}})
    meta = Meta(base_dir=str(tmp_path), uuid="release", filename="Example", is_disc=is_disc)

    asyncio.run(tracker.edit_desc(meta))

    image_host.assert_awaited_once()
    assert image_host.await_args.kwargs["files"] == [("images", (screenshot.name, b"png", "image/png"))]
    assert image_host.await_args.kwargs["data"] == (None if is_disc else {"mediainfo": "Example summary"})
    assert "Hosted screenshots" in (directory.parent / "[FILELIST]DESCRIPTION.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("is_disc", ["", "BDMV"])
@pytest.mark.parametrize("image_group", [None, "main", "FILE_1"])
def test_filelist_without_primary_pngs_only_posts_mediainfo(tmp_path, image_host, is_disc, image_group):
    directory = screenshots_dir(tmp_path, "release")
    if image_group:
        image = directory / ("page.jpg" if image_group == "main" else "extra.png")
        image.write_bytes(b"image")
        register(tmp_path, "release", [image], image_group)
    for name in ("MEDIAINFO_CLEANPATH.txt", "BD_SUMMARY_EXT.txt"):
        (directory.parent / name).write_text("Example summary", encoding="utf-8")
    tracker = FileList({"TRACKERS": {"FILELIST": {"fltools": {"user": "user", "pass": "password"}}}})
    tracker.signature = "Example signature"
    meta = Meta(base_dir=str(tmp_path), uuid="release", is_disc=is_disc)
    if is_disc:
        image_host.side_effect = AssertionError("Blu-ray without PNGs must not contact the image host")

    asyncio.run(tracker.edit_desc(meta))

    description = (directory.parent / "[FILELIST]DESCRIPTION.txt").read_text(encoding="utf-8")
    assert description.endswith(tracker.signature)
    if is_disc:
        image_host.assert_not_awaited()
        assert "Example summary" in description
    else:
        image_host.assert_awaited_once()
        assert image_host.await_args.kwargs["files"] == []
        assert image_host.await_args.kwargs["data"] == {"mediainfo": "Example summary"}
