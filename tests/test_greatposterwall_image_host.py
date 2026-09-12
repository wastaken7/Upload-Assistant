"""Tests for GreatPosterWall's tracker-specific image rehost API."""

# ruff: noqa: S101

import asyncio

import httpx

from src.meta import Meta
from src.tracker_images import get_tracker_image_collection
from src.trackers.GAZELLE.greatposterwall import GreatPosterWall


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
    monkeypatch.setattr("src.trackers.GAZELLE.greatposterwall.httpx.AsyncClient", _Client)
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
        {"img_url": "https://lostimg.cc/example.png", "raw_url": "https://lostimg.cc/example.png", "web_url": "https://lostimg.cc/example.png"},
        {
            "img_url": "https://img2.kshare.club/gpw/user/1/kept.png",
            "raw_url": "https://img2.kshare.club/gpw/user/1/kept.png",
            "web_url": "https://img2.kshare.club/gpw/user/1/kept.png",
        },
    ]
    assert get_tracker_image_collection(meta, tracker.tracker, "screenshots") == [
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
    assert tracker.tracker not in meta.tracker_image_collections


def test_greatposterwall_accepts_pterclub_s3_host():
    tracker = GreatPosterWall({"DEFAULT": {"tmdb_api": "test"}, "TRACKERS": {"GREATPOSTERWALL": {}}})

    assert tracker.is_approved_image_url("https://s3.pterclub.com/screenshots/example.png")


def test_greatposterwall_fallback_credit_filter_keeps_pairs_aligned():
    tracker = GreatPosterWall({"DEFAULT": {"tmdb_api": "test"}, "TRACKERS": {"GREATPOSTERWALL": {}}})
    meta = Meta(
        imdb_info={
            "directors": ["Wrong Director", "Right Director"],
            "directors_id": ["invalid", "nm0000002"],
            "writers": ["Wrong Writer", "Right Writer"],
            "writers_id": ["invalid", "nm0000003"],
            "stars": ["Wrong Star", "Right Star"],
            "stars_id": ["invalid", "nm0000004"],
        }
    )

    data = asyncio.run(tracker._get_artist_data(meta))

    assert data["artists[]"] == ["Right Director", "Right Writer", "Right Star"]
    assert data["artist_ids[]"] == ["nm0000002", "nm0000003", "nm0000004"]


def test_greatposterwall_movie_info_tries_api_after_http_failure(monkeypatch):
    class FallbackResponse:
        def __init__(self, fails: bool):
            self.fails = fails

        def raise_for_status(self):
            if self.fails:
                request = httpx.Request("GET", "https://greatposterwall.com/upload.php")
                response = httpx.Response(500, request=request)
                raise httpx.HTTPStatusError("failed", request=request, response=response)

        def json(self):
            return {"status": 200, "response": {"FullCredits": [{"id": "nm0000001"}]}}

    class FallbackClient:
        calls = 0

        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            type(self).calls += 1
            return FallbackResponse(type(self).calls == 1)

    monkeypatch.setattr("src.trackers.GAZELLE.greatposterwall.httpx.AsyncClient", FallbackClient)
    tracker = GreatPosterWall({"DEFAULT": {"tmdb_api": "test"}, "TRACKERS": {"GREATPOSTERWALL": {"api_key": "secret"}}})
    monkeypatch.setattr(tracker, "load_cookies", lambda _meta: asyncio.sleep(0, result={"session": "cookie"}))

    result = asyncio.run(tracker._fetch_gpw_movie_info(Meta(), "imdb", "tt1234567"))

    assert result == {"FullCredits": [{"id": "nm0000001"}]}
    assert FallbackClient.calls == 2


def test_greatposterwall_sets_hdr_flags_without_dolby_vision():
    tracker = GreatPosterWall({"DEFAULT": {"tmdb_api": "test"}, "TRACKERS": {"GREATPOSTERWALL": {}}})

    assert tracker.get_media_flags(Meta(hdr="HDR10+"))["hdr10plus"] == "on"
    assert tracker.get_media_flags(Meta(hdr="HDR"))["hdr10"] == "on"
