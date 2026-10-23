"""Regression coverage for HDBits screenshot rehosting."""

# ruff: noqa: S101

import asyncio
from unittest.mock import ANY, AsyncMock

import httpx
import pytest

from src.meta import Meta
from src.screenshot_manifest import register
from src.temp_paths import screenshots_dir
from src.trackers.hdbits import HDBits


BBCODE = "[url=https://images.example/screenshot][img]https://images.example/screenshot.png[/img][/url]"


@pytest.fixture
def image_uploads(monkeypatch):
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post.return_value = httpx.Response(200, text=BBCODE)
    record_event = AsyncMock()
    monkeypatch.setattr("src.trackers.hdbits.httpx.AsyncClient", lambda **_kwargs: client)
    monkeypatch.setattr("src.trackers.hdbits.record_event_async", record_event)
    return client.post, record_event


def test_hdbits_rehosts_registered_screenshots(tmp_path, image_uploads) -> None:
    upload, record_event = image_uploads
    directory = screenshots_dir(tmp_path, "release")
    screenshot = directory / "screen.png"
    screenshot.write_bytes(b"png")
    screenshot = register(tmp_path, "release", [screenshot], "main")[0]
    for group in ("FILE_1", "PLAYLIST_1"):
        extra = directory / f"{group}.png"
        extra.write_bytes(b"extra")
        register(tmp_path, "release", [extra], group)
    (directory / "stray.png").write_bytes(b"stray")
    jpeg = directory / "screen.jpg"
    jpeg.write_bytes(b"jpeg")
    register(tmp_path, "release", [jpeg], "main")
    tracker = HDBits({"TRACKERS": {"HDBITS": {"username": "user", "passkey": "pass"}}})
    meta = Meta(base_dir=str(tmp_path), uuid="release", name="Example", category="MOVIE")

    assert asyncio.run(tracker.hdbimg_upload(meta)) == BBCODE
    upload.assert_awaited_once()
    assert upload.await_args.kwargs["files"] == {"images_files[0]": (screenshot.name, b"png", "image/png")}
    record_event.assert_awaited_once_with("api", service="hdbimg", operation="image_upload", outcome="success", duration_ms=ANY, bytes_count=3)


def test_hdbits_reads_comparisons_from_their_own_directory(tmp_path, image_uploads) -> None:
    upload, record_event = image_uploads
    comparison = tmp_path / "comparison"
    comparison.mkdir()
    for name in ("1-source.png", "1-encode.png"):
        (comparison / name).write_bytes(b"png")
    tracker = HDBits({"TRACKERS": {"HDBITS": {}}})
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="release",
        comparison=str(comparison),
        comparison_groups={"1": {"files": ["1-source.png"]}, "2": {"files": ["1-encode.png"]}},
    )

    assert asyncio.run(tracker.hdbimg_upload(meta)) == BBCODE
    upload.assert_awaited_once()
    assert list(upload.await_args.kwargs["files"].values()) == [("1-source.png", b"png", "image/png"), ("1-encode.png", b"png", "image/png")]
    record_event.assert_awaited_once_with("api", service="hdbimg", operation="image_upload", outcome="success", duration_ms=ANY, bytes_count=6)
