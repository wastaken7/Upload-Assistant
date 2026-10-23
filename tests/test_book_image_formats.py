"""Book artwork and screenshot formats follow their source images."""

import asyncio
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

import pytest
from PIL import Image

from src.meta import Meta
from src.screenshot_manifest import files as manifest_files
from src.screenshot_manifest import register
from src.takescreens import generate_ebook_screenshots
from src.uploadscreens import _upload_screens
from upload import book_screens


def _image_bytes(image_format: str, color="purple") -> bytes:
    output = BytesIO()
    Image.new("RGB", (32, 32), color).save(output, image_format)
    return output.getvalue()


@pytest.mark.parametrize("upload_limit", [2, 3])
def test_cbz_preserves_page_order_formats_and_cover(tmp_path: Path, upload_limit) -> None:
    archive = tmp_path / "Invented Comic.cbz"
    pages = {"01.jpg": _image_bytes("JPEG", "red"), "02.jpeg": _image_bytes("JPEG", "green"), "03.png": _image_bytes("PNG", "blue")}
    with ZipFile(archive, "w") as comic:
        for name, content in pages.items():
            comic.writestr(name, content)
    meta = Meta(category="BOOK", base_dir=str(tmp_path), uuid="invented-comic", path=str(archive), screens=3)

    result = asyncio.run(generate_ebook_screenshots(str(archive), "Invented Comic", meta.uuid, meta.base_dir, meta, num_screens=3))

    assert {Path(path).suffix for path in result} == {".jpg", ".jpeg", ".png"}  # noqa: S101
    assert [Path(path).read_bytes() for path in result] == list(pages.values())  # noqa: S101
    assert list(map(Path, result)) == manifest_files(meta.base_dir, meta.uuid, "main")  # noqa: S101
    assert Path(meta.artwork_path).name == "POSTER.jpg"  # noqa: S101
    assert Path(meta.artwork_path).read_bytes() == pages["01.jpg"]  # noqa: S101
    assert Path(meta.artwork_banner_path).name == "POSTER_BANNER.png"  # noqa: S101
    (Path(result[0]).parent / "stray.png").write_bytes(b"unregistered")
    extra = Path(result[0]).parent / "extra.jpg"
    extra.write_bytes(_image_bytes("JPEG"))
    register(meta.base_dir, meta.uuid, [extra], "FILE_1")
    assert book_screens(meta, 4) == (3, 3)  # noqa: S101

    uploaded: list[Path] = []

    async def fake_upload(args: object) -> dict[str, str]:
        source = Path(args[0])
        uploaded.append(source)
        url = f"https://images.example/{source.name}"
        return {"status": "success", "img_url": url, "raw_url": url, "web_url": url}

    meta.imghost = "imgbox"
    config = {"DEFAULT": {"img_host_1": "imgbox", "image_upload_delay": 0}, "TRACKERS": {}}
    with patch("src.uploadscreens.upload_image_task", new=fake_upload):
        asyncio.run(_upload_screens(config, meta, upload_limit, 1, 0, upload_limit, [], {}))
    assert uploaded == list(map(Path, result[:upload_limit]))  # noqa: S101


def test_cbz_converts_webp_page_to_png(tmp_path: Path) -> None:
    archive = tmp_path / "Fictional Collection.cbz"
    with ZipFile(archive, "w") as comic:
        comic.writestr("01.webp", _image_bytes("WEBP"))
        comic.writestr("02.jpg", _image_bytes("JPEG"))
    meta = Meta(category="BOOK", base_dir=str(tmp_path), uuid="fictional-collection", path=str(archive), screens=2)

    result = asyncio.run(generate_ebook_screenshots(str(archive), "Fictional Collection", meta.uuid, meta.base_dir, meta, num_screens=2))

    assert {Path(path).suffix for path in result} == {".png", ".jpg"}  # noqa: S101
    assert Path(meta.artwork_path).suffix == ".png"  # noqa: S101
    assert Path(meta.artwork_banner_path).suffix == ".jpg"  # noqa: S101
