"""Book artwork and screenshot formats follow their source images."""

import asyncio
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from PIL import Image

from src.meta import Meta
from src.screenshot_manifest import files as manifest_files
from src.takescreens import generate_ebook_screenshots
from src.uploadscreens import _upload_screens
from upload import book_screens


def _image_bytes(image_format: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (32, 32), "purple").save(output, image_format)
    return output.getvalue()


def test_cbz_preserves_jpeg_pages_and_cover(tmp_path: Path) -> None:
    archive = tmp_path / "Invented Comic.cbz"
    pages = {"01.jpg": _image_bytes("JPEG"), "02.jpeg": _image_bytes("JPEG"), "03.png": _image_bytes("PNG")}
    with ZipFile(archive, "w") as comic:
        for name, content in pages.items():
            comic.writestr(name, content)
    meta = Meta(category="BOOK", base_dir=str(tmp_path), uuid="invented-comic", path=str(archive), screens=3)

    result = asyncio.run(generate_ebook_screenshots(str(archive), "Invented Comic", meta.uuid, meta.base_dir, meta, num_screens=3))

    assert {Path(path).suffix for path in result} == {".jpg", ".jpeg", ".png"}  # noqa: S101
    assert {Path(path).read_bytes() for path in result} == set(pages.values())  # noqa: S101
    assert set(map(Path, result)) == set(manifest_files(meta.base_dir, meta.uuid, "main"))  # noqa: S101
    assert Path(meta.artwork_path).name == "POSTER.jpg"  # noqa: S101
    assert Path(meta.artwork_path).read_bytes() == pages["01.jpg"]  # noqa: S101
    assert Path(meta.artwork_banner_path).name == "POSTER_BANNER.png"  # noqa: S101
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
        asyncio.run(_upload_screens(config, meta, 3, 1, 0, 3, [], {}))
    assert set(uploaded) == set(map(Path, result))  # noqa: S101


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
