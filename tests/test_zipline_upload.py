# ruff: noqa: S101

import asyncio
from pathlib import Path
from typing import Self
from unittest.mock import patch

from src.uploadscreens import upload_image_task


class _FakeFile:
    async def __aenter__(self) -> Self:
        """Enter the fake async file context."""
        return self

    async def __aexit__(self, *_args: object) -> None:
        """Exit the fake async file context."""
        return

    async def read(self) -> bytes:
        """Return deterministic fake image bytes."""
        return b"image"


class _FakeResponse:
    status_code = 200
    text = ""

    def __init__(self, payload: object) -> None:
        """Store the fake JSON response payload."""
        self._payload = payload

    def json(self) -> object:
        """Return the stored fake JSON payload."""
        return self._payload


class _FakeHttpClient:
    def __init__(self, payload: object, requests: list[tuple[tuple[object, ...], dict[str, object]]]) -> None:
        """Create a fake HTTP client returning payload."""
        self._response = _FakeResponse(payload)
        self._requests = requests

    async def __aenter__(self) -> Self:
        """Enter the fake HTTP client context."""
        return self

    async def __aexit__(self, *_args: object) -> None:
        """Exit the fake HTTP client context."""
        return

    async def post(self, *_args: object, **_kwargs: object) -> _FakeResponse:
        """Return the configured fake upload response."""
        self._requests.append((_args, _kwargs))
        return self._response


def _run_upload(
    tmp_path: Path,
    payload: object,
    *,
    img_host: str = "zipline",
    config_defaults: dict[str, str] | None = None,
    requests: list[tuple[tuple[object, ...], dict[str, object]]] | None = None,
) -> dict[str, str]:
    """Run one mocked Zipline upload with the supplied response payload."""
    request_log = requests if requests is not None else []
    config = config_defaults if config_defaults is not None else {"zipline_url": "https://zip.example/api/upload", "zipline_api_key": "key"}

    async def exercise() -> dict[str, str]:
        """Execute the upload coroutine under test."""
        return await upload_image_task(
            (
                str(tmp_path / "image.png"),
                img_host,
                {"DEFAULT": config},
                None,
            )
        )

    with patch("src.uploadscreens.aiofiles.open", return_value=_FakeFile()), patch("src.uploadscreens.httpx.AsyncClient", return_value=_FakeHttpClient(payload, request_log)):
        return asyncio.run(exercise())


def test_zipline_upload_accepts_object_file_response(tmp_path: Path) -> None:
    """Accept Zipline's object-based file response and derive all URLs."""
    result = _run_upload(tmp_path, {"files": [{"url": "https://zip.example/u/image.png"}]})

    assert result == {
        "status": "success",
        "img_url": "https://zip.example/u/image.png",
        "raw_url": "https://zip.example/r/image.png",
        "web_url": "https://zip.example/r/image.png",
    }


def test_zipline_upload_preserves_legacy_string_response(tmp_path: Path) -> None:
    """Preserve support for Zipline's legacy string file response."""
    result = _run_upload(tmp_path, {"files": ["https://zip.example/u/image.png"]})

    assert result["status"] == "success"
    assert result["img_url"] == "https://zip.example/u/image.png"
    assert result["raw_url"] == "https://zip.example/r/image.png"
    assert result["web_url"] == "https://zip.example/r/image.png"


def test_zipline_upload_rejects_non_list_files_response(tmp_path: Path) -> None:
    """Reject malformed Zipline responses whose files value is not a list."""
    result = _run_upload(tmp_path, {"files": "not-a-list"})

    assert result == {"status": "failed", "reason": "No valid URL returned from Zipline"}


def test_midnightscene_uses_its_fixed_endpoint_and_token(tmp_path: Path) -> None:
    """Upload to MidnightScene without requiring a generic Zipline URL."""
    requests: list[tuple[tuple[object, ...], dict[str, object]]] = []
    result = _run_upload(
        tmp_path,
        {"files": [{"url": "https://img.midnightscene.cc/u/image.png"}]},
        img_host="midnightscene",
        config_defaults={"midnightscene_api_key": "midnightscene-token"},
        requests=requests,
    )

    assert result["status"] == "success"
    assert requests == [
        (
            ("https://img.midnightscene.cc/api/upload",),
            {
                "files": {"file": ("image.png", b"image")},
                "headers": {"Authorization": "midnightscene-token"},
                "timeout": 60,
            },
        )
    ]
