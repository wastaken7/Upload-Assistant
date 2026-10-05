# ruff: noqa: S101

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from src.configvalidator import validate_config
from src.uploadscreens import upload_image_task


def _upload(tmp_path: Path, *, userhash: str = "", response_text: str = "https://files.catbox.moe/abc123.png", status: int = 200) -> tuple[dict, AsyncMock]:
    image = tmp_path / "Fictional.Release.png"
    image.write_bytes(b"image data")
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=httpx.Response(status, text=response_text))

    with patch("src.uploadscreens.httpx.AsyncClient", return_value=client):
        result = asyncio.run(upload_image_task((str(image), "catbox", {"DEFAULT": {"catbox_userhash": userhash}}, None)))
    return result, client.post


def test_catbox_anonymous_upload_uses_multipart_and_plain_url(tmp_path: Path) -> None:
    result, post = _upload(tmp_path)

    assert result == {
        "status": "success",
        "img_url": "https://files.catbox.moe/abc123.png",
        "raw_url": "https://files.catbox.moe/abc123.png",
        "web_url": "https://files.catbox.moe/abc123.png",
        "local_file_path": str(tmp_path / "Fictional.Release.png"),
    }
    post.assert_awaited_once_with(
        "https://catbox.moe/user/api.php",
        data={"reqtype": "fileupload"},
        files={"fileToUpload": ("Fictional.Release.png", b"image data")},
        timeout=60,
    )


def test_catbox_account_upload_sends_userhash(tmp_path: Path) -> None:
    result, post = _upload(tmp_path, userhash="test-userhash")

    assert result["status"] == "success"
    assert post.await_args.kwargs["data"] == {"reqtype": "fileupload", "userhash": "test-userhash"}


def test_catbox_rejects_error_text_and_other_urls(tmp_path: Path) -> None:
    for response_text, status in (("No file specified", 200), ("https://example.test/image.png", 200), ("https://files.catbox.moe/a.png", 503)):
        result, _ = _upload(tmp_path, response_text=response_text, status=status)
        assert result["status"] == "failed"


def test_catbox_is_valid_without_userhash() -> None:
    is_valid, errors, warnings = validate_config({"DEFAULT": {"tmdb_api": "test-key", "img_host_1": "catbox", "catbox_userhash": ""}, "TRACKERS": {}})

    assert is_valid
    assert not errors
    assert not any(warning.key == "img_host_1" for warning in warnings)
