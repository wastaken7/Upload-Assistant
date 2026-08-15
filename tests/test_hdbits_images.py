"""Regression coverage for HDBits screenshot rehosting."""

# ruff: noqa: S101

import asyncio

import pytest

from src.meta import Meta
from src.temp_paths import screenshots_dir
from src.trackers.hdbits import HDBits


class _Response:
    status_code = 200
    text = "[img]https://img.hdbits.org/screenshot.png[/img]"


class _Client:
    files: dict[str, tuple[str, bytes, str]]

    async def __aenter__(self) -> _Client:
        return self

    async def __aexit__(self, *_args: object) -> None:
        pass

    @classmethod
    async def post(cls, _url: str, **kwargs: object) -> _Response:
        cls.files = kwargs["files"]  # type: ignore[assignment,index]
        return _Response()


def test_hdbits_rehosts_screenshots_from_typed_directory(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.trackers.hdbits.httpx.AsyncClient", lambda **_kwargs: _Client())
    screenshot = screenshots_dir(tmp_path, "release") / "screen.png"
    screenshot.write_bytes(b"png")
    tracker = HDBits({"TRACKERS": {"HDBITS": {"username": "user", "passkey": "pass"}}})
    meta = Meta(base_dir=str(tmp_path), uuid="release", name="Example", category="MOVIE")

    assert asyncio.run(tracker.hdbimg_upload(meta)) == _Response.text
    assert _Client.files == {"images_files[0]": ("screen.png", b"png", "image/png")}
