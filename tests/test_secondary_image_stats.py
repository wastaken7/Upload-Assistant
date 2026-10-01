"""Tracker-specific image hosts contribute to external-operation statistics."""

# ruff: noqa: S101

import asyncio
from types import SimpleNamespace

import pytest

from src.meta import Meta
from src.temp_paths import screenshots_dir
from src.trackers.AVISTAZ import AZTrackerBase
from src.trackers.NEXUSPHP.pterclub import PTerClub
from src.uploadscreens import upload_image_task_with_stats


@pytest.mark.parametrize("succeeded", [True, False])
def test_avistaz_image_host_records_result_and_uploaded_bytes(monkeypatch, succeeded):
    class Response:
        is_success = True

        def json(self):
            return {"success": succeeded, "imageId": "fictional-image"} if succeeded else {"success": False, "error": "upload rejected"}

    async def post(_url, **_kwargs):
        return Response()

    events = []

    async def record_event(_family, **kwargs):
        events.append(kwargs)

    tracker = object.__new__(AZTrackerBase)
    tracker.tracker = "AVISTAZ"
    tracker.base_url = "https://fictional.example"
    tracker.az_class = SimpleNamespace(secret_token="fictional-token")  # noqa: S106
    tracker.session = SimpleNamespace(post=post)
    monkeypatch.setattr("src.trackers.AVISTAZ.record_event_async", record_event)

    result = asyncio.run(tracker.img_host(Meta(), "https://fictional.example/upload", b"image-bytes", "image.png"))

    assert result == ("fictional-image" if succeeded else None)
    assert [(event["service"], event["operation"], event["outcome"], event["bytes_count"]) for event in events] == [
        ("AVISTAZ", "image_upload", "success" if succeeded else "error", 11 if succeeded else 0)
    ]


@pytest.mark.parametrize("succeeded", [True, False])
def test_direct_image_task_records_one_operation(monkeypatch, tmp_path, succeeded):
    image = tmp_path / "fictional-image.png"
    image.write_bytes(b"image-bytes")
    events = []

    async def upload_task(_args):
        return {"status": "success" if succeeded else "failed"}

    async def record_event(_family, **kwargs):
        events.append(kwargs)

    monkeypatch.setattr("src.uploadscreens.upload_image_task", upload_task)
    monkeypatch.setattr("src.uploadscreens.record_event_async", record_event)

    asyncio.run(upload_image_task_with_stats((str(image), "bioma", {}, Meta())))

    assert [(event["service"], event["operation"], event["outcome"], event["bytes_count"]) for event in events] == [
        ("bioma", "image_upload", "success" if succeeded else "error", 11 if succeeded else 0)
    ]


@pytest.mark.parametrize("succeeded", [True, False])
def test_pterimg_records_validated_image_upload(monkeypatch, tmp_path, succeeded):
    class Response:
        is_success = True
        reason_phrase = "OK"
        text = ""

        def json(self):
            return {"image": {"url": "https://fictional.example/image.png"}} if succeeded else {"image": {}}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, **_kwargs):
            return Response()

    async def get_auth_token(_meta):
        return "fictional-token"

    events = []

    async def record_event(_family, **kwargs):
        events.append(kwargs)

    cookie_file = tmp_path / "Pterimg.txt"
    cookie_file.write_text("fictional cookie", encoding="utf-8")
    image = screenshots_dir(tmp_path, "fictional-release") / "Fictional.Release-01.png"
    image.write_bytes(b"image-bytes")
    meta = Meta(base_dir=str(tmp_path), uuid="fictional-release", filename="Fictional.Release")
    tracker = object.__new__(PTerClub)
    tracker.config = {"TRACKERS": {}}
    tracker.cookie_validator = SimpleNamespace(_load_cookies_dict_secure=lambda _path: {})
    tracker.get_auth_token = get_auth_token
    monkeypatch.setattr("src.cookie_auth.find_cookie_file", lambda *_args: str(cookie_file))
    monkeypatch.setattr("src.trackers.NEXUSPHP.pterclub.httpx.AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr("src.trackers.NEXUSPHP.pterclub.record_event_async", record_event)

    if succeeded:
        result = asyncio.run(tracker.pterimg_upload(meta))
        assert result == [{"web_url": "https://fictional.example/image.png", "img_url": "https://fictional.example/image.png"}]
    else:
        with pytest.raises(ValueError, match="Missing image url"):
            asyncio.run(tracker.pterimg_upload(meta))

    assert [(event["service"], event["operation"], event["outcome"], event["bytes_count"]) for event in events] == [
        ("pterimg", "image_upload", "success" if succeeded else "error", 11 if succeeded else 0)
    ]
