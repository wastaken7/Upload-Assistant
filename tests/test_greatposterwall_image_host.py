"""Tests for GreatPosterWall's tracker-specific image rehost API."""

# ruff: noqa: S101

import asyncio

from src.meta import Meta
from src.trackers.greatposterwall import GreatPosterWall


class _Response:
    status_code = 200

    @staticmethod
    def json():
        return {"status": 200, "response": {"files": [{"name": "https://img2.kshare.club/gpw/user/1/test.png"}]}}


class _Client:
    request_params = None
    request_data = None

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, _url, **kwargs):
        self.__class__.request_params = kwargs["params"]
        self.__class__.request_data = kwargs["data"]
        return _Response()


def test_greatposterwall_rehosts_only_unapproved_urls(monkeypatch):
    monkeypatch.setattr("src.trackers.greatposterwall.httpx.AsyncClient", _Client)
    tracker = GreatPosterWall({"DEFAULT": {"tmdb_api": "test"}, "TRACKERS": {"GREATPOSTERWALL": {"api_key": "test-key"}}})
    meta = Meta(
        image_list=[
            {"img_url": "https://lostimg.cc/example.png", "raw_url": "https://lostimg.cc/example.png", "web_url": "https://lostimg.cc/example.png"},
            {
                "img_url": "https://img2.kshare.club/gpw/user/1/kept.png",
                "raw_url": "https://img2.kshare.club/gpw/user/1/kept.png",
                "web_url": "https://img2.kshare.club/gpw/user/1/kept.png",
            },
        ]
    )

    asyncio.run(tracker.rehost_unapproved_images(meta))

    assert meta.image_list == [
        {
            "img_url": "https://img2.kshare.club/gpw/user/1/test.png",
            "raw_url": "https://img2.kshare.club/gpw/user/1/test.png",
            "web_url": "https://img2.kshare.club/gpw/user/1/test.png",
        },
        {
            "img_url": "https://img2.kshare.club/gpw/user/1/kept.png",
            "raw_url": "https://img2.kshare.club/gpw/user/1/kept.png",
            "web_url": "https://img2.kshare.club/gpw/user/1/kept.png",
        },
    ]
    assert _Client.request_params == {"action": "img_upload", "api_key": "test-key"}
    assert _Client.request_data == {"urls[]": "https://lostimg.cc/example.png"}


def test_greatposterwall_leaves_images_unchanged_without_api_key():
    tracker = GreatPosterWall({"DEFAULT": {"tmdb_api": "test"}, "TRACKERS": {"GREATPOSTERWALL": {}}})
    meta = Meta(image_list=[{"raw_url": "https://lostimg.cc/example.png"}])

    asyncio.run(tracker.rehost_unapproved_images(meta))

    assert meta.image_list == [{"raw_url": "https://lostimg.cc/example.png"}]
