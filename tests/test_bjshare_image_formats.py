"""BJShare image uploads use MIME types matching their bytes."""

import asyncio
from io import BytesIO

import pytest
from PIL import Image

from src.meta import Meta
from src.trackers.GAZELLE.bjshare import BJShare


class _Response:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, str]:
        return {"url": "https://images.example/uploaded"}


class _Session:
    def __init__(self) -> None:
        self.files = None

    async def post(self, _url, **kwargs):
        self.files = kwargs["files"]
        return _Response()


@pytest.mark.parametrize(
    ("image_format", "input_name", "expected_name", "expected_type"),
    [
        ("JPEG", "page.jpeg", "page.jpeg", "image/jpeg"),
        ("JPEG", "page.jfif", "page.jfif", "image/jpeg"),
        ("PNG", "page.png", "page.png", "image/png"),
        ("GIF", "page.gif", "page.gif", "image/gif"),
        ("WEBP", "page.webp", "page.png", "image/png"),
    ],
)
def test_bjshare_upload_uses_supported_image_format(image_format: str, input_name: str, expected_name: str, expected_type: str) -> None:
    image = BytesIO()
    Image.new("RGB", (16, 16), "green").save(image, image_format)
    tracker = object.__new__(BJShare)
    tracker.base_url = "https://bjshare.example"
    tracker.tracker = "BJSHARE"
    tracker.session = _Session()

    result = asyncio.run(tracker.img_host(image.getvalue(), input_name))

    assert result == "https://images.example/uploaded"  # noqa: S101
    filename, content, mime = tracker.session.files["file"]
    assert (filename, mime) == (expected_name, expected_type)  # noqa: S101
    with Image.open(BytesIO(content)) as uploaded:
        assert uploaded.format == ("PNG" if image_format == "WEBP" else image_format)  # noqa: S101


def test_bjshare_finds_local_jpeg_screenshot(tmp_path) -> None:
    from src.temp_paths import screenshots_dir

    screenshot = screenshots_dir(tmp_path, "fictional-release") / "page-01.jpg"
    screenshot.write_bytes(_jpeg_bytes())
    tracker = object.__new__(BJShare)
    uploaded: list[str] = []

    async def fake_img_host(_content: bytes, filename: str) -> str:
        uploaded.append(filename)
        return "https://images.example/page-01.jpg"

    tracker.img_host = fake_img_host
    result = asyncio.run(tracker.get_screenshots(Meta(base_dir=str(tmp_path), uuid="fictional-release")))

    assert result == ["https://images.example/page-01.jpg"]  # noqa: S101
    assert uploaded == ["page-01.jpg"]  # noqa: S101


def _jpeg_bytes() -> bytes:
    image = BytesIO()
    Image.new("RGB", (16, 16), "blue").save(image, "JPEG")
    return image.getvalue()
