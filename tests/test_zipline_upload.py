# ruff: noqa: S101

import asyncio
from pathlib import Path
from typing import Self
from unittest.mock import patch

from src.uploadscreens import upload_image_task


class _FakeFile:
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def read(self) -> bytes:
        return b"image"


class _FakeResponse:
    status_code = 200
    text = ""

    def __init__(self, payload: object) -> None:
        self._payload = payload

    def json(self) -> object:
        return self._payload


class _FakeHttpClient:
    def __init__(self, payload: object) -> None:
        self._response = _FakeResponse(payload)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def post(self, *_args: object, **_kwargs: object) -> _FakeResponse:
        return self._response


def _run_upload(tmp_path: Path, payload: object) -> dict[str, str]:
    async def exercise() -> dict[str, str]:
        return await upload_image_task(
            (
                str(tmp_path / "image.png"),
                "zipline",
                {"DEFAULT": {"zipline_url": "https://zip.example/api/upload", "zipline_api_key": "key"}},
                None,
            )
        )

    with patch("src.uploadscreens.aiofiles.open", return_value=_FakeFile()), patch(
        "src.uploadscreens.httpx.AsyncClient", return_value=_FakeHttpClient(payload)
    ):
        return asyncio.run(exercise())


def test_zipline_upload_accepts_object_file_response(tmp_path: Path) -> None:
    result = _run_upload(tmp_path, {"files": [{"url": "https://zip.example/u/image.png"}]})

    assert result == {
        "status": "success",
        "img_url": "https://zip.example/u/image.png",
        "raw_url": "https://zip.example/r/image.png",
        "web_url": "https://zip.example/r/image.png",
    }


def test_zipline_upload_preserves_legacy_string_response(tmp_path: Path) -> None:
    result = _run_upload(tmp_path, {"files": ["https://zip.example/u/image.png"]})

    assert result["status"] == "success"
    assert result["img_url"] == "https://zip.example/u/image.png"


def test_zipline_upload_rejects_non_list_files_response(tmp_path: Path) -> None:
    result = _run_upload(tmp_path, {"files": "not-a-list"})

    assert result == {"status": "failed", "reason": "No valid URL returned from Zipline"}
