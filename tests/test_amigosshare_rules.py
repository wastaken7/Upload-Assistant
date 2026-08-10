# ruff: noqa: S101

import asyncio
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

data_config = types.ModuleType("data.config")
data_config.__file__ = str(Path(__file__).parents[1] / "data" / "config.py")
data_config.DEFAULT = {}
data_config.config = {}
sys.modules.setdefault("data.config", data_config)

from src.trackers.amigosshare import AmigosShare  # noqa: E402


def make_meta(**overrides):
    values = {
        "category": "MOVIE",
        "anime": False,
        "imdb_id": "1234567",
        "source_size": 2 * 1024 * 1024,
        "language_checked": True,
        "audio_languages": [],
        "subtitle_languages": [],
        "subtitle_files": [],
        "unattended": False,
        "unattended_confirm": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def tracker() -> AmigosShare:
    return AmigosShare({"DEFAULT": {"tmdb_api": "test-key"}, "TRACKERS": {"AMIGOSSHARE": {}}})


async def run_checks(
    meta: SimpleNamespace,
    *,
    confirm_result: bool | None = None,
    guard_language_call: bool = False,
) -> bool:
    client = tracker()
    try:
        if guard_language_call:
            client.common.check_language_requirements = AsyncMock(side_effect=AssertionError("language check should not run"))

        if confirm_result is not None:
            client.common.prompt_user_for_confirmation = AsyncMock(return_value=confirm_result)
        else:
            client.common.prompt_user_for_confirmation = AsyncMock(side_effect=AssertionError("confirmation should not run"))

        return await client.get_additional_checks(meta)
    finally:
        await client.session.aclose()


def test_movie_passes_with_portuguese_audio():
    meta = make_meta(audio_languages=["portuguese"])

    assert asyncio.run(run_checks(meta))


def test_movie_passes_with_portuguese_language_aliases():
    meta = make_meta(audio_languages=["por"])

    assert asyncio.run(run_checks(meta))


def test_movie_passes_with_portuguese_subtitles():
    meta = make_meta(subtitle_languages=["portuguese"])

    assert asyncio.run(run_checks(meta))


def test_movie_rejects_missing_language_when_unattended():
    meta = make_meta(unattended=True)

    assert not asyncio.run(run_checks(meta))


def test_movie_allows_attended_confirmation_after_missing_language():
    meta = make_meta(unattended=False)

    assert asyncio.run(run_checks(meta, confirm_result=True))


def test_movie_passes_with_portuguese_external_subtitles():
    meta = make_meta(subtitle_files=["movie.pt-BR.srt"])

    assert asyncio.run(run_checks(meta, guard_language_call=True))


def test_movie_passes_with_accented_portuguese_external_subtitles():
    meta = make_meta(subtitle_files=["movie.português.srt"])

    assert asyncio.run(run_checks(meta, guard_language_call=True))


@pytest.mark.parametrize(
    "subtitle_file",
    ["movie.pt-BR.forced.srt", "movie.portuguese.sdh.srt"],
)
def test_movie_passes_with_tagged_portuguese_external_subtitles(subtitle_file: str) -> None:
    meta = make_meta(subtitle_files=[subtitle_file])

    assert asyncio.run(run_checks(meta, guard_language_call=True))


def test_movie_does_not_treat_unidentified_external_subtitles_as_portuguese():
    meta = make_meta(subtitle_files=["external.srt"], unattended=True)

    assert not asyncio.run(run_checks(meta))


def test_movie_does_not_treat_title_words_as_language_markers():
    meta = make_meta(subtitle_files=["Amor.Por.Acaso.srt"], unattended=True)

    assert not asyncio.run(run_checks(meta))


def test_movie_prompts_when_unattended_confirmation_is_enabled():
    meta = make_meta(unattended=True, unattended_confirm=True)

    assert asyncio.run(run_checks(meta, confirm_result=True))


def test_book_and_game_bypass_video_language_validation():
    book_meta = make_meta(category="BOOK", imdb_id=None, source_size=2 * 1024 * 1024)
    game_meta = make_meta(category="GAME", imdb_id=None)

    assert asyncio.run(run_checks(book_meta, guard_language_call=True))
    assert asyncio.run(run_checks(game_meta, guard_language_call=True))


def test_book_size_rejection_happens_before_other_checks():
    meta = make_meta(category="BOOK", imdb_id=None, source_size=1024)

    assert not asyncio.run(run_checks(meta, guard_language_call=True))


def test_imdb_rejection_happens_before_language_validation():
    meta = make_meta(imdb_id=None, audio_languages=["portuguese"], subtitle_languages=["portuguese"])

    assert not asyncio.run(run_checks(meta, guard_language_call=True))
