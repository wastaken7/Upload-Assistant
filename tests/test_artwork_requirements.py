# ruff: noqa: S101
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from src.args import Args
from src.meta import Meta
from src.trackers.UNIT3D import UNIT3D
from upload import _prompt_book_meta, _prompt_music_meta


@pytest.mark.asyncio
async def test_prompt_book_meta_accepts_file_path(tmp_path: Path) -> None:
    cover_file = tmp_path / "cover.jpg"
    Image.new("RGB", (32, 48), "red").save(cover_file)

    meta = Meta(category="BOOK", title="Test Book", author="Test Author", year=2024, book_language="English", book_language_iso="eng")

    with patch("upload.CLI_UI.ask_string", return_value=str(cover_file)):
        await _prompt_book_meta(meta)

    assert meta.artwork_path == str(cover_file.resolve())


@pytest.mark.asyncio
async def test_prompt_book_meta_accepts_url() -> None:
    meta = Meta(category="BOOK", title="Test Book", author="Test Author", year=2024, book_language="English", book_language_iso="eng")

    with patch("upload.CLI_UI.ask_string", return_value="https://example.com/cover.jpg"):
        await _prompt_book_meta(meta)

    assert meta.artwork_url == "https://example.com/cover.jpg"


@pytest.mark.asyncio
async def test_prompt_music_meta_accepts_file_path(tmp_path: Path) -> None:
    cover_file = tmp_path / "album_cover.png"
    Image.new("RGB", (32, 48), "purple").save(cover_file)

    meta = Meta(
        category="MUSIC",
        artist="Test Artist",
        title="Test Album",
        year=2024,
        source="CD",
        music_release={"fields": {"release_type": {"value": "Album"}}},
    )

    with patch("upload.CLI_UI.ask_string", return_value=str(cover_file)):
        await _prompt_music_meta(meta)

    assert meta.artwork_path == str(cover_file.resolve())


@pytest.mark.asyncio
async def test_prompt_music_meta_rejects_invalid_file_before_accepting_cover(tmp_path: Path) -> None:
    invalid_file = tmp_path / "invalid.png"
    invalid_file.write_bytes(b"not an image")
    valid_file = tmp_path / "valid.png"
    Image.new("RGB", (32, 48), "orange").save(valid_file)

    meta = Meta(
        category="MUSIC",
        artist="Test Artist",
        title="Test Album",
        year=2024,
        source="CD",
        music_release={"fields": {"release_type": {"value": "Album"}}},
    )

    with patch("upload.CLI_UI.ask_string", side_effect=[str(invalid_file), str(valid_file)]):
        await _prompt_music_meta(meta)

    assert meta.artwork_path == str(valid_file.resolve())


def test_book_cover_cli_arg(tmp_path: Path) -> None:
    cover_file = tmp_path / "cli_cover.png"
    Image.new("RGB", (32, 48), "blue").save(cover_file)

    parser = Args({"DEFAULT": {"screens": 4, "img_host_1": "imgbox"}})
    meta = Meta(category="BOOK")
    parser.parse([str(tmp_path), "--book-cover", str(cover_file)], meta)

    assert meta.artwork_path == str(cover_file.resolve())


def test_invalid_cover_is_not_accepted() -> None:
    from src.artwork import is_valid_cover_image

    assert not is_valid_cover_image(None)


@pytest.mark.asyncio
async def test_unit3d_attaches_only_a_decodable_book_cover(tmp_path: Path) -> None:
    cover_file = tmp_path / "cover.png"
    Image.new("RGB", (32, 48), "green").save(cover_file)
    meta = Meta(category="BOOK", base_dir=str(tmp_path), uuid="book-1", artwork_path=str(cover_file))
    tracker = UNIT3D({"DEFAULT": {}, "TRACKERS": {"TEST": {}}}, "TEST")

    files = await tracker.get_additional_files(meta)

    assert "torrent-cover" in files
    assert files["torrent-cover"][2] == "image/png"

    cover_file.write_bytes(b"not an image")
    files = await tracker.get_additional_files(meta)
    assert "torrent-cover" not in files
