"""Regression tests for automatic ebook category detection."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.book_prep import resolve_book_filelist
from src.meta import Meta
from src.prep_helpers import detect_disc_and_category


@pytest.mark.parametrize("extension", [".azw", ".azw3"])
def test_azw_files_are_detected_as_books(extension, tmp_path):
    book = tmp_path / f"example{extension}"
    book.write_bytes(b"Kindle ebook")
    meta = Meta(path=str(book))
    prep = SimpleNamespace(disc_info_manager=SimpleNamespace(get_disc=AsyncMock(return_value=("", str(book), {}, []))))

    asyncio.run(detect_disc_and_category(prep, meta))

    assert meta.category == "BOOK"


@pytest.mark.parametrize("extension", [".azw", ".azw3"])
def test_azw_files_are_included_when_resolving_book_directories(extension, tmp_path):
    book = tmp_path / f"example{extension}"
    book.write_bytes(b"Kindle ebook")
    meta = Meta()

    videopath, filelist, _, _ = resolve_book_filelist(meta, str(tmp_path))

    assert videopath == str(book.resolve())
    assert filelist == [str(book.resolve())]
    assert meta.audiobook is False
