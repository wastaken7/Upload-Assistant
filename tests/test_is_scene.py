# ruff: noqa: S101

from pathlib import Path
from typing import Any

import pytest

from src.is_scene import SceneManager
from src.meta import Meta


class _Response:
    def __init__(self, payload: dict[str, Any] | None = None, content: bytes = b"") -> None:
        self.status_code = 200
        self._payload = payload
        self.content = content

    def json(self) -> dict[str, Any]:
        assert self._payload is not None
        return self._payload


class _FakeAsyncClient:
    def __init__(self) -> None:
        self.requested_urls: list[str] = []

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def get(self, url: str, **_kwargs: Any) -> _Response:
        self.requested_urls.append(url)
        if "/v1/search/" in url:
            return _Response(
                {
                    "resultsCount": 1,
                    "results": [
                        {
                            "release": "Example.Release.2024.1080p.WEB.H264-GROUP",
                            "hasNFO": "yes",
                            "imdbId": "1234567",
                        }
                    ],
                }
            )
        if "/v1/details/" in url:
            return _Response({"files": [{"name": "example.release.2024.1080p.web.h264-group.nfo"}]})
        if "/download/file/" in url:
            return _Response(content=b"scene nfo contents")
        raise AssertionError(f"Unexpected request: {url}")


@pytest.mark.asyncio
async def test_default_meta_searches_srrdb_and_downloads_nfo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeAsyncClient()
    monkeypatch.setattr("src.is_scene.httpx.AsyncClient", lambda: client)
    meta = Meta(base_dir=str(tmp_path), uuid="scene-test", category="MOVIE")

    video, scene, imdb = await SceneManager({"DEFAULT": {}}).is_scene(
        "/downloads/Example.Release.2024.1080p.WEB.H264-GROUP.mkv",
        meta,
    )

    release = "Example.Release.2024.1080p.WEB.H264-GROUP"
    nfo_path = tmp_path / "tmp" / "scene-test" / "example.release.2024.1080p.web.h264-group.nfo"

    assert client.requested_urls == [
        f"https://api.srrdb.com/v1/search/r:{release}",
        f"https://api.srrdb.com/v1/details/{release}",
        f"https://www.srrdb.com/download/file/{release}/example.release.2024.1080p.web.h264-group.nfo",
    ]
    assert (video, scene, imdb) == (f"{release}.mkv", True, 1234567)
    assert meta.scene_name == release
    assert meta.scene_nfo_file == nfo_path
    assert meta.nfo is True
    assert meta.auto_nfo is True
    assert nfo_path.read_bytes() == b"scene nfo contents"
