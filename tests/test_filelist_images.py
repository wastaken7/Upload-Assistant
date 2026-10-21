# ruff: noqa: S101

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.meta import Meta
from src.screenshot_manifest import register
from src.temp_paths import screenshots_dir
from src.trackers.filelist import FileList


@pytest.mark.parametrize("is_disc", ["", "BDMV"])
def test_filelist_uploads_registered_primary_screenshots(tmp_path, monkeypatch, is_disc):
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
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post.return_value = SimpleNamespace(text="Hosted screenshots")
    monkeypatch.setattr("src.trackers.filelist.httpx.AsyncClient", lambda **_kwargs: client)
    monkeypatch.setattr("src.trackers.filelist.get_base_description", lambda _meta: "Example description")
    tracker = FileList({"TRACKERS": {"FILELIST": {"fltools": {"user": "user", "pass": "password"}}}})
    meta = Meta(base_dir=str(tmp_path), uuid="release", filename="Example", is_disc=is_disc)

    asyncio.run(tracker.edit_desc(meta))

    client.post.assert_awaited_once()
    assert client.post.await_args.kwargs["files"] == [("images", (screenshot.name, b"png", "image/png"))]
    assert client.post.await_args.kwargs["data"] == (None if is_disc else {"mediainfo": "Example summary"})
    assert "Hosted screenshots" in (directory.parent / "[FILELIST]DESCRIPTION.txt").read_text(encoding="utf-8")
