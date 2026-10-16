# ruff: noqa: S101
"""THR image uploads must return usable URLs and preserve rejection details."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.meta import Meta
from src.uploadscreens import _upload_screens, upload_image_task


def _upload(tmp_path: Path, response: httpx.Response) -> tuple[dict, AsyncMock]:
    image = tmp_path / "Fictional.Release.png"
    image.write_bytes(b"image data")
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=response)
    with patch("src.uploadscreens.httpx.AsyncClient", return_value=client):
        result = asyncio.run(upload_image_task((str(image), "thrimg", {"DEFAULT": {"thrimg_api": "test-key"}}, None)))
    return result, client.post


def _response(payload: object) -> httpx.Response:
    return httpx.Response(200, content=json.dumps(payload), request=httpx.Request("POST", "https://slike.torrenthr.org/api/1/upload"))


def test_thrimg_upload_returns_trimmed_urls(tmp_path: Path) -> None:
    url = "https://slike.torrenthr.org/images/fictional.png"
    result, post = _upload(tmp_path, _response({"image": {"url": f" {url} "}}))
    assert result == {
        "status": "success",
        "img_url": url,
        "raw_url": url,
        "web_url": url,
        "local_file_path": str(tmp_path / "Fictional.Release.png"),
    }
    post.assert_awaited_once_with(
        "https://slike.torrenthr.org/api/1/upload",
        data={"key": "test-key"},
        files={"source": ("Fictional.Release.png", b"image data")},
        timeout=60,
    )


@pytest.mark.parametrize("value", [None, 123, True, [], {}, "", "   "])
def test_thrimg_upload_rejects_invalid_url_values(tmp_path: Path, value: object) -> None:
    result, _ = _upload(tmp_path, _response({"image": {"url": value}}))
    assert result["status"] == "failed"
    assert "image URL" in result["reason"]


@pytest.mark.parametrize("payload", [{}, {"image": {}}, {"image": None}, [], None])
def test_thrimg_upload_rejects_missing_image_data(tmp_path: Path, payload: object) -> None:
    result, _ = _upload(tmp_path, _response(payload))
    assert result["status"] == "failed"
    assert "image URL" in result["reason"]


def test_thrimg_http_failure_includes_bounded_body(tmp_path: Path) -> None:
    response = httpx.Response(
        403,
        text="Upload rejected: " + "x" * 1000,
        request=httpx.Request("POST", "https://slike.torrenthr.org/api/1/upload"),
    )
    result, _ = _upload(tmp_path, response)
    assert result["status"] == "failed"
    assert "HTTP 403" in result["reason"]
    assert "Upload rejected:" in result["reason"]
    assert len(result["reason"]) < 400


def test_thrimg_restricted_upload_does_not_fall_back_to_other_hosts(tmp_path: Path) -> None:
    upload = AsyncMock(return_value={"status": "failed", "reason": "Upload rejected"})
    config = {
        "DEFAULT": {
            "img_host_1": "thrimg",
            "img_host_2": "imgbox",
            "image_upload_concurrency": 1,
            "image_upload_delay": 0,
        }
    }
    image = tmp_path / "Fictional.Release.png"
    image.write_bytes(b"image data")
    meta = Meta(base_dir=str(tmp_path), uuid="fictional", imghost="thrimg")
    with patch("src.uploadscreens.upload_image_task", new=upload):
        _, count = asyncio.run(_upload_screens(config, meta, 1, 1, 0, 1, [str(image)], {}, allowed_hosts=["thrimg"]))
    assert count == 0
    assert upload.await_count > 0
    assert all(call.args[0][1] == "thrimg" for call in upload.await_args_list)
