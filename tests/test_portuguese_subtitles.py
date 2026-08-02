# ruff: noqa: S101

import asyncio
from pathlib import Path
from types import SimpleNamespace

from src.trackers.common import Common


def check_subtitles(tmp_path: Path, *names: str) -> bool:
    meta = SimpleNamespace(subtitle_files=[str(tmp_path / name) for name in names])
    return asyncio.run(Common({}).has_portuguese_external_subtitle(meta))


def test_detects_portuguese_from_filename(tmp_path: Path):
    assert check_subtitles(tmp_path, "movie.pt-BR.srt")


def test_detects_portuguese_from_text_when_filename_is_ambiguous(tmp_path: Path):
    subtitle = tmp_path / "movie.external.srt"
    subtitle.write_text("Olá, você está aqui? Vamos para casa.", encoding="utf-8")

    assert check_subtitles(tmp_path, subtitle.name)


def test_does_not_accept_unidentified_text_subtitle(tmp_path: Path):
    subtitle = tmp_path / "movie.external.srt"
    subtitle.write_text("This is a subtitle. Where are you going?", encoding="utf-8")

    assert not check_subtitles(tmp_path, subtitle.name)


def test_does_not_read_binary_idx_as_text(tmp_path: Path):
    subtitle = tmp_path / "movie.external.idx"
    subtitle.write_bytes(b"Portuguese subtitle index")

    assert not check_subtitles(tmp_path, subtitle.name)
