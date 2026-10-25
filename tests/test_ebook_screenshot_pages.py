"""Ebook screenshots always include the cover and the ISBN or copyright page."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import fitz
import pytest

from src.book_extractors import find_copyright_page, find_isbn_page
from src.meta import Meta
from src.prep import Prep
from src.screenshot_manifest import capture_pages
from src.screenshot_manifest import files as manifest_files
from src.screenshot_manifest import register as register_screenshots
from src.screenshot_review import add_screenshot, list_screenshots, replace_screenshot
from src.temp_paths import screenshots_dir
from src.takescreens import find_ebook_info_page, generate_ebook_screenshots, select_ebook_pages


def _make_pdf(path: Path, pages: list[str]) -> None:
    doc = fitz.open()
    for text in pages:
        doc.new_page().insert_text((72, 72), text)
    doc.save(path)
    doc.close()


@pytest.mark.parametrize("num_screens", [1, 2, 4, 10])
def test_select_ebook_pages_keeps_fixed_pages(num_screens: int) -> None:
    selected = select_ebook_pages(6, num_screens, [0, 3, 3, 99])

    assert selected == sorted(set(selected))  # noqa: S101
    assert len(selected) == min(num_screens, 6)  # noqa: S101
    assert selected[0] == 0  # noqa: S101
    if num_screens > 1:
        assert 3 in selected  # noqa: S101


def test_find_isbn_page_prefers_front_pages(tmp_path: Path) -> None:
    pdf = tmp_path / "Invented Book.pdf"
    pages = ["Cover", "Chapter one"] + ["Story"] * 70 + ["ISBN 978-0-306-40615-7"]
    pages[3] = "Imaginary Press\nISBN 0-306-40615-2"
    _make_pdf(pdf, pages)

    with fitz.open(pdf) as doc:
        assert find_isbn_page(doc) == (3, "0306406152")  # noqa: S101


def test_find_copyright_page_without_isbn(tmp_path: Path) -> None:
    pdf = tmp_path / "Invented Book.pdf"
    _make_pdf(pdf, ["Cover", "Title", "Copyright 2020 Fictional Author. All rights reserved.", "Chapter one"])

    with fitz.open(pdf) as doc:
        assert find_isbn_page(doc) is None  # noqa: S101
        assert find_copyright_page(doc) == 2  # noqa: S101


def test_info_page_prefers_copyright_page_with_isbn(tmp_path: Path) -> None:
    pdf = tmp_path / "Invented Book.pdf"
    pages = ["Cover", "Back cover blurb\nISBN 978-0-306-40615-7", "Title", "Copyright 2021 Imaginary Press\nISBN 978-0-306-40615-7", "Chapter one"]
    _make_pdf(pdf, pages)

    with fitz.open(pdf) as doc:
        assert find_isbn_page(doc) == (1, "9780306406157")  # noqa: S101
        assert find_ebook_info_page(doc) == 3  # noqa: S101


def test_pdf_screenshots_include_cover_and_isbn_page(tmp_path: Path) -> None:
    pdf = tmp_path / "Invented Book.pdf"
    pages = [f"Page {i}" for i in range(40)]
    pages[5] = "Imaginary Press\nISBN 978-0-306-40615-7"
    _make_pdf(pdf, pages)
    meta = Meta(category="BOOK", base_dir=str(tmp_path), uuid="invented-book", path=str(pdf), screens=3)

    result = asyncio.run(generate_ebook_screenshots(str(pdf), "Invented Book", meta.uuid, meta.base_dir, meta, num_screens=3))

    assert len(result) == 3  # noqa: S101
    with fitz.open(pdf) as doc:
        cover = doc[0].get_pixmap(matrix=fitz.Matrix(2.0, 2.0)).tobytes("png")
        isbn_page = doc[5].get_pixmap(matrix=fitz.Matrix(2.0, 2.0)).tobytes("png")
    rendered = [fitz.Pixmap(path).tobytes("png") for path in result]
    assert rendered[0] == cover  # noqa: S101
    assert isbn_page in rendered  # noqa: S101


def _book_meta(tmp_path: Path, pdf: Path, **kwargs: object) -> Meta:
    return Meta(category="BOOK", base_dir=str(tmp_path), uuid="invented-book", path=str(pdf), filelist=[str(pdf)], screens=3, **kwargs)


def test_pages_only_capture_is_reused_by_the_full_pass(tmp_path: Path) -> None:
    pdf = tmp_path / "Invented Book.pdf"
    _make_pdf(pdf, [f"Page {i}" for i in range(12)])
    meta = _book_meta(tmp_path, pdf)

    early = asyncio.run(generate_ebook_screenshots(str(pdf), "Invented Book", meta.uuid, meta.base_dir, meta, num_screens=3, artwork=False))

    assert len(early) == 3  # noqa: S101
    assert not meta.artwork_path  # noqa: S101
    assert 0 in capture_pages(meta.base_dir, meta.uuid, "main")  # noqa: S101

    with patch("src.takescreens.download_artwork_from_meta", new=AsyncMock(return_value=False)):
        final = asyncio.run(generate_ebook_screenshots(str(pdf), "Invented Book", meta.uuid, meta.base_dir, meta, num_screens=3))

    assert final == early  # noqa: S101
    assert Path(meta.artwork_path).is_file()  # noqa: S101
    assert Path(meta.artwork_banner_path).is_file()  # noqa: S101


def test_review_adds_and_replaces_unused_book_pages(tmp_path: Path) -> None:
    pdf = tmp_path / "Invented Book.pdf"
    _make_pdf(pdf, [f"Page {i}" for i in range(4)])
    meta = _book_meta(tmp_path, pdf)
    asyncio.run(generate_ebook_screenshots(str(pdf), "Invented Book", meta.uuid, meta.base_dir, meta, num_screens=2, artwork=False))
    temp_dir = tmp_path / "tmp" / meta.uuid
    meta_data = {"category": "BOOK", "uuid": meta.uuid, "base_dir": meta.base_dir, "path": str(pdf), "filelist": [str(pdf)]}

    added = asyncio.run(add_screenshot(temp_dir, meta_data))

    assert len(capture_pages(meta.base_dir, meta.uuid, "main")) == 3  # noqa: S101
    assert added.id in {item.id for item in list_screenshots(temp_dir, meta_data)}  # noqa: S101

    unused = {0, 1, 2, 3} - capture_pages(meta.base_dir, meta.uuid, "main")
    replaced = asyncio.run(replace_screenshot(temp_dir, meta_data, added.id))

    assert replaced.id == added.id  # noqa: S101
    assert unused <= capture_pages(meta.base_dir, meta.uuid, "main")  # noqa: S101
    assert len(list_screenshots(temp_dir, meta_data)) == 3  # noqa: S101


class _EbookSpy:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def ebook_page_screenshots(self, *_args: object) -> None:
        self.calls.append("ebook")

    async def screenshots(self, *_args: object, **_kwargs: object) -> None:
        self.calls.append("video")


@pytest.mark.parametrize(("audiobook", "expected"), [(False, ["ebook"]), (True, [])])
def test_early_capture_takes_ebook_pages_but_not_audiobooks(audiobook: bool, expected: list[str]) -> None:
    prep = Prep.__new__(Prep)
    prep.takescreens_manager = _EbookSpy()
    prep.config = {"DEFAULT": {}}
    meta = Meta(category="BOOK", audiobook=audiobook, screens=4)

    asyncio.run(prep._capture_early_screenshots(meta, "Invented Book", "C:/books/Invented Book.pdf", {}))

    assert prep.takescreens_manager.calls == expected  # noqa: S101


def test_screenshots_without_page_numbers_are_recaptured(tmp_path: Path) -> None:
    pdf = tmp_path / "Invented Book.pdf"
    _make_pdf(pdf, [f"Page {i}" for i in range(6)])
    meta = _book_meta(tmp_path, pdf)
    legacy = screenshots_dir(meta.base_dir, meta.uuid) / "legacy.png"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(b"not a page")
    register_screenshots(meta.base_dir, meta.uuid, [legacy], "main")

    result = asyncio.run(generate_ebook_screenshots(str(pdf), "Invented Book", meta.uuid, meta.base_dir, meta, num_screens=2, artwork=False))

    assert len(result) == 2  # noqa: S101
    assert len(capture_pages(meta.base_dir, meta.uuid, "main")) == 2  # noqa: S101
    assert manifest_files(meta.base_dir, meta.uuid, "main") == [Path(path) for path in result]  # noqa: S101
