"""Regression tests for automatic ebook category detection."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.book_prep import resolve_book_filelist
from src.meta import Meta
from src.prep_helpers import detect_disc_and_category


@pytest.mark.parametrize("extension", [".azw", ".azw3", ".fb2", ".html", ".chm", ".djvu", ".doc", ".docx", ".kfx", ".lit", ".pdb", ".txt", ".rtf"])
def test_azw_files_are_detected_as_books(extension, tmp_path):
    book = tmp_path / f"example{extension}"
    book.write_bytes(b"Kindle ebook")
    meta = Meta(path=str(book))
    prep = SimpleNamespace(disc_info_manager=SimpleNamespace(get_disc=AsyncMock(return_value=("", str(book), {}, []))))

    asyncio.run(detect_disc_and_category(prep, meta))

    assert meta.category == "BOOK"


@pytest.mark.parametrize("extension", [".azw", ".azw3", ".fb2", ".html", ".chm", ".djvu", ".doc", ".docx", ".kfx", ".lit", ".pdb", ".txt", ".rtf"])
def test_azw_files_are_included_when_resolving_book_directories(extension, tmp_path):
    book = tmp_path / f"example{extension}"
    book.write_bytes(b"Kindle ebook")
    meta = Meta()

    videopath, filelist, _, _ = resolve_book_filelist(meta, str(tmp_path))

    assert videopath == str(book.resolve())
    assert filelist == [str(book.resolve())]
    assert meta.audiobook is False


@pytest.mark.parametrize("extension", [".opus", ".alac", ".aax", ".aaxc"])
def test_new_audiobook_formats_are_detected(extension, tmp_path):
    audiobook = tmp_path / f"chapter01{extension}"
    audiobook.write_bytes(b"audiobook")
    meta = Meta()

    _, filelist, _, _ = resolve_book_filelist(meta, str(tmp_path))

    assert filelist == [str(audiobook.resolve())]
    assert meta.audiobook is True


def test_audiobook_uses_audio_file_when_pdf_is_larger(tmp_path):
    pdf = tmp_path / "book.pdf"
    audiobook = tmp_path / "book.m4b"
    pdf.write_bytes(b"x" * 100)
    audiobook.write_bytes(b"audio")

    meta = Meta()
    videopath, filelist, _, _ = resolve_book_filelist(meta, str(tmp_path))

    assert videopath == str(audiobook.resolve())  # noqa: S101
    assert filelist == [str(audiobook.resolve()), str(pdf.resolve())]  # noqa: S101
    assert meta.audiobook is True  # noqa: S101


def test_text_sidecars_are_excluded_when_a_richer_book_format_exists(tmp_path):
    book = tmp_path / "book.epub"
    readme = tmp_path / "README.txt"
    cover = tmp_path / "cover.html"
    book.write_bytes(b"ebook")
    readme.write_text("release notes")
    cover.write_text("cover page")
    meta = Meta()

    videopath, filelist, _, _ = resolve_book_filelist(meta, str(tmp_path))

    assert videopath == str(book.resolve())
    assert filelist == [str(book.resolve())]


def test_map_audiobook_keywords():
    from src.genre_map import map_audiobook_keywords

    # PT-BR compound genre
    assert map_audiobook_keywords("Ação e Aventura") == ["ação", "aventura"]
    assert map_audiobook_keywords("22. Ação e Aventura") == ["ação", "aventura"]

    # English compound genre
    assert map_audiobook_keywords("Action & Adventure") == ["action", "adventure"]
    assert map_audiobook_keywords("Science Fiction & Fantasy") == ["science fiction", "fantasy"]

    # Multiple genres in list
    assert map_audiobook_keywords(["Ação e Aventura", "Romance"]) == ["ação", "aventura", "romance"]

    # Fallback to original cleaned genre when not in map
    assert map_audiobook_keywords("Custom Unmapped Genre") == ["custom unmapped genre"]
    assert map_audiobook_keywords("Custom Genre A; Custom Genre B") == ["custom genre a", "custom genre b"]
