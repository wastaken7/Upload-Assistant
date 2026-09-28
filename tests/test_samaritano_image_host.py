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
        return

    async def read(self) -> bytes:
        return b"fictional image"


class _FakeResponse:
    text = ""

    def __init__(self, payload: object, status_code: int = 201, json_error: bool = False) -> None:
        self.payload = payload
        self.status_code = status_code
        self.json_error = json_error

    def json(self) -> object:
        if self.json_error:
            raise ValueError("invalid json")
        return self.payload


class _FakeHttpClient:
    def __init__(self, response: _FakeResponse, requests: list[tuple[tuple[object, ...], dict[str, object]]]) -> None:
        self.response = response
        self.requests = requests

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return

    async def post(self, *args: object, **kwargs: object) -> _FakeResponse:
        self.requests.append((args, kwargs))
        return self.response


def _run_upload(
    tmp_path: Path,
    payload: object,
    *,
    status_code: int = 201,
    json_error: bool = False,
    api_key: str = "fictional-image-token",
) -> tuple[dict[str, object], list[tuple[tuple[object, ...], dict[str, object]]]]:
    requests: list[tuple[tuple[object, ...], dict[str, object]]] = []
    response = _FakeResponse(payload, status_code=status_code, json_error=json_error)
    config = {"DEFAULT": {}, "TRACKERS": {"SAMARITANO": {"image_host_api_key": api_key}}}

    with (
        patch("src.uploadscreens.aiofiles.open", return_value=_FakeFile()),
        patch("src.uploadscreens.httpx.AsyncClient", return_value=_FakeHttpClient(response, requests)),
    ):
        result = asyncio.run(upload_image_task((str(tmp_path / "fictional-shot.png"), "samaritano", config, None)))
    return result, requests


def test_samaritano_upload_posts_bearer_multipart_and_maps_urls(tmp_path: Path) -> None:
    result, requests = _run_upload(
        tmp_path,
        {
            "url": "https://img.samaritano.cc/uploads/fictional-shot.png",
            "thumbnail_url": "https://img.samaritano.cc/thumbnails/fictional-shot.png",
        },
    )

    assert result == {
        "status": "success",
        "img_url": "https://img.samaritano.cc/thumbnails/fictional-shot.png",
        "raw_url": "https://img.samaritano.cc/uploads/fictional-shot.png",
        "web_url": "https://img.samaritano.cc/uploads/fictional-shot.png",
        "local_file_path": str(tmp_path / "fictional-shot.png"),
    }
    assert requests == [
        (
            ("https://img.samaritano.cc/api/v1/images",),
            {
                "headers": {"Authorization": "Bearer fictional-image-token"},
                "files": {"file": ("fictional-shot.png", b"fictional image")},
                "timeout": 60,
            },
        )
    ]


def test_samaritano_upload_uses_raw_url_without_thumbnail(tmp_path: Path) -> None:
    result, _ = _run_upload(tmp_path, {"url": "https://img.samaritano.cc/uploads/fictional-shot.png"}, status_code=200)

    assert result["status"] == "success"
    assert result["img_url"] == result["raw_url"] == result["web_url"]


def test_samaritano_upload_rejects_missing_key(tmp_path: Path) -> None:
    result, requests = _run_upload(tmp_path, {}, api_key="")

    assert result == {"status": "failed", "reason": "Missing Samaritano image host API key"}
    assert requests == []


def test_samaritano_upload_rejects_http_error(tmp_path: Path) -> None:
    result, _ = _run_upload(tmp_path, {"message": "unauthorized"}, status_code=401)

    assert result == {"status": "failed", "reason": "Samaritano upload failed: HTTP 401"}


def test_samaritano_upload_rejects_invalid_json(tmp_path: Path) -> None:
    result, _ = _run_upload(tmp_path, {}, json_error=True)

    assert result == {"status": "failed", "reason": "Invalid JSON response"}


def test_samaritano_upload_rejects_missing_response_url(tmp_path: Path) -> None:
    result, _ = _run_upload(tmp_path, {"status": True})

    assert result == {"status": "failed", "reason": "No URL in Samaritano response"}
