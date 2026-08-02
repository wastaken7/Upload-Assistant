"""Regression tests for secure MUSIC artwork hosting."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

from src.meta import Meta
from upload import _host_music_cover, _is_public_music_cover_url


def test_music_cover_reuses_cached_hosted_url_before_downloading(tmp_path):
    cache_path = tmp_path / "tmp" / "music-cover" / "covers.json"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text(json.dumps([{"raw_url": "https://images.example/cover.jpg"}]), encoding="utf-8")
    meta = Meta(base_dir=str(tmp_path), uuid="music-cover", artwork_url="https://unavailable.example/cover.jpg", music_release={"fields": {}})
    manager = AsyncMock()

    with patch("upload._download_music_cover") as download:
        asyncio.run(_host_music_cover(meta, manager))

    download.assert_not_called()
    manager.upload_screens.assert_not_called()
    assert meta.artwork_url == "https://images.example/cover.jpg"  # noqa: S101
    assert meta.music_release["fields"]["cover_url"]["value"] == meta.artwork_url  # noqa: S101


def test_music_cover_rejects_private_download_host():
    with patch("src.artwork.socket.getaddrinfo", return_value=[(None, None, None, None, ("127.0.0.1", 0))]):
        assert not _is_public_music_cover_url("http://localhost/cover.jpg")  # noqa: S101
