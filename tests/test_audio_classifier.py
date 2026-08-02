"""Tests for audio category classification (BOOK/audiobook vs MUSIC vs ambiguous)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.meta import Meta
from src.prep_helpers import detect_disc_and_category


def test_m4b_audiobook_detected_as_book(tmp_path):
    m4b_file = tmp_path / "testbook.m4b"
    m4b_file.write_bytes(b"dummy m4b content")
    meta = Meta(path=str(tmp_path))
    prep = SimpleNamespace(disc_info_manager=SimpleNamespace(get_disc=AsyncMock(return_value=("", str(tmp_path), {}, []))))

    asyncio.run(detect_disc_and_category(prep, meta))

    assert meta.category == "BOOK"
    assert meta.audiobook is True


def test_mp3_audiobook_with_part_filenames_detected_as_book(tmp_path):
    p1 = tmp_path / "Book-Part01.mp3"
    p2 = tmp_path / "Book-Part02.mp3"
    p3 = tmp_path / "Book-Part03.mp3"
    p1.write_bytes(b"dummy mp3 content 1")
    p2.write_bytes(b"dummy mp3 content 2")
    p3.write_bytes(b"dummy mp3 content 3")

    meta = Meta(path=str(tmp_path))
    prep = SimpleNamespace(disc_info_manager=SimpleNamespace(get_disc=AsyncMock(return_value=("", str(tmp_path), {}, []))))

    asyncio.run(detect_disc_and_category(prep, meta))

    assert meta.category == "BOOK"
    assert meta.audiobook is True


def test_mixed_ebook_and_audiobook_folder_detected_as_book(tmp_path):
    epub = tmp_path / "Book.epub"
    mp3 = tmp_path / "Book-Part01.mp3"
    epub.write_bytes(b"dummy epub")
    mp3.write_bytes(b"dummy mp3")

    meta = Meta(path=str(tmp_path))
    prep = SimpleNamespace(disc_info_manager=SimpleNamespace(get_disc=AsyncMock(return_value=("", str(tmp_path), {}, []))))

    asyncio.run(detect_disc_and_category(prep, meta))

    assert meta.category == "BOOK"
    assert meta.audiobook is True


def test_explicit_book_category_override_takes_priority(tmp_path):
    mp3 = tmp_path / "audio.mp3"
    mp3.write_bytes(b"dummy mp3")

    meta = Meta(path=str(tmp_path), manual_category="book")
    prep = SimpleNamespace(disc_info_manager=SimpleNamespace(get_disc=AsyncMock(return_value=("", str(tmp_path), {}, []))))

    asyncio.run(detect_disc_and_category(prep, meta))

    assert meta.category == "BOOK"
    assert meta.audiobook is True


def test_explicit_music_category_override_takes_priority(tmp_path):
    m4b = tmp_path / "book.m4b"
    m4b.write_bytes(b"dummy m4b")

    meta = Meta(path=str(tmp_path), manual_category="music")
    prep = SimpleNamespace(disc_info_manager=SimpleNamespace(get_disc=AsyncMock(return_value=("", str(tmp_path), {}, []))))

    asyncio.run(detect_disc_and_category(prep, meta))

    assert meta.category == "MUSIC"
    assert meta.audiobook is False


def test_ambiguous_audio_folder_prompts_in_interactive_mode(tmp_path):
    t1 = tmp_path / "track_alpha.mp3"
    t2 = tmp_path / "track_beta.mp3"
    t1.write_bytes(b"dummy mp3 1")
    t2.write_bytes(b"dummy mp3 2")

    meta = Meta(path=str(tmp_path), unattended=False)
    prep = SimpleNamespace(disc_info_manager=SimpleNamespace(get_disc=AsyncMock(return_value=("", str(tmp_path), {}, []))))

    with patch("cli_ui.ask_choice", return_value="2. Audiobook"):
        asyncio.run(detect_disc_and_category(prep, meta))

    assert meta.category == "BOOK"
    assert meta.audiobook is True


def test_ambiguous_audio_prompt_does_not_hide_unexpected_errors(tmp_path):
    t1 = tmp_path / "track_alpha.mp3"
    t2 = tmp_path / "track_beta.mp3"
    t1.write_bytes(b"dummy mp3 1")
    t2.write_bytes(b"dummy mp3 2")

    meta = Meta(path=str(tmp_path), unattended=False)
    prep = SimpleNamespace(disc_info_manager=SimpleNamespace(get_disc=AsyncMock(return_value=("", str(tmp_path), {}, []))))

    with patch("cli_ui.ask_choice", side_effect=RuntimeError("unexpected prompt failure")), pytest.raises(RuntimeError, match="unexpected prompt failure"):
        asyncio.run(detect_disc_and_category(prep, meta))


def test_ambiguous_audio_folder_fails_in_unattended_mode(tmp_path):
    t1 = tmp_path / "track_alpha.mp3"
    t2 = tmp_path / "track_beta.mp3"
    t1.write_bytes(b"dummy mp3 1")
    t2.write_bytes(b"dummy mp3 2")

    meta = Meta(path=str(tmp_path), unattended=True, unattended_confirm=False)
    prep = SimpleNamespace(disc_info_manager=SimpleNamespace(get_disc=AsyncMock(return_value=("", str(tmp_path), {}, []))))

    with pytest.raises(SystemExit):
        asyncio.run(detect_disc_and_category(prep, meta))
