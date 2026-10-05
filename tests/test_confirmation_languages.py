"""Language metadata must survive preparation after confirmation corrections."""

# ruff: noqa: S101

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.args import Args
from src.languages import LanguagesManager
from src.meta import Meta
from src.prep_helpers import init_meta
from src.trackers.common import Common


@pytest.mark.parametrize("category,is_disc", [("MOVIE", ""), ("TV", ""), ("MOVIE", "BDMV")])
def test_detected_languages_survive_repeated_confirmation_corrections(tmp_path, monkeypatch, category, is_disc):
    config = {"DEFAULT": {"screens": 1}}
    prep = SimpleNamespace(config=config)
    original_args = [str(tmp_path / "Release.mkv")]
    meta, _, _ = Args(config).parse(original_args, Meta(base_dir=str(tmp_path), category=category, is_disc=is_disc, original_language="English"))
    init_meta(prep, meta, "cli")
    release_dir = tmp_path / "tmp" / meta.uuid
    if is_disc == "BDMV":
        (release_dir / "BD_SUMMARY_00.txt").write_text(
            "Audio: English / Dolby Digital / 2.0 / 48 kHz / 640 kbps\nSubtitle: Spanish / 20 kbps\n", encoding="utf-8"
        )
    else:
        (release_dir / "MEDIAINFO.txt").write_text(
            "Audio\nFormat : E-AC-3\nLanguage : English\nText\nFormat : UTF-8\nLanguage : Spanish\n", encoding="utf-8"
        )
    ask_string = Mock(side_effect=AssertionError("Detected languages must not prompt for manual input"))
    monkeypatch.setattr("src.languages.cli_ui.ask_string", ask_string)
    manager = LanguagesManager()
    asyncio.run(manager.process_desc_language(meta))
    assert meta.audio_languages == ["English"]
    assert meta.subtitle_languages == ["Spanish"]

    corrections = []
    for edit in (["--service", "AMZN"], ["--tag", "UpdatedGroup"]):
        corrections.extend(edit)
        meta, _, _ = Args(config).parse(original_args + corrections, meta)
        meta.edit = True
        init_meta(prep, meta, "cli")
        asyncio.run(manager.process_desc_language(meta))

        assert meta.language_checked is True
        assert meta.audio_languages == ["English"]
        assert meta.subtitle_languages == ["Spanish"]
        assert meta.service == "AMZN"
        common = Common(config)
        assert asyncio.run(common.check_language_requirements(meta, "LST", ["English"], check_audio=True, check_subtitle=True, prompt_on_failure=False))
        assert asyncio.run(common.check_language_requirements(
            meta, "AITHER", [], original_language=True, original_required=True, prompt_on_failure=False
        ))
    ask_string.assert_not_called()


def test_manually_entered_languages_survive_confirmation_correction(tmp_path, monkeypatch):
    config = {"DEFAULT": {"screens": 1}}
    prep = SimpleNamespace(config=config)
    original_args = [str(tmp_path / "Release.mkv")]
    meta, _, _ = Args(config).parse(original_args, Meta(base_dir=str(tmp_path), category="MOVIE"))
    init_meta(prep, meta, "cli")
    (tmp_path / "tmp" / meta.uuid / "MEDIAINFO.txt").write_text(
        "Audio\nFormat : E-AC-3\nText\nFormat : UTF-8\n", encoding="utf-8"
    )
    ask_string = Mock(side_effect=["English, French", "Spanish"])
    monkeypatch.setattr("src.languages.cli_ui.ask_string", ask_string)
    manager = LanguagesManager()
    asyncio.run(manager.process_desc_language(meta))
    assert ask_string.call_count == 2

    meta, _, _ = Args(config).parse([*original_args, "--service", "AMZN"], meta)
    meta.edit = True
    init_meta(prep, meta, "cli")
    asyncio.run(manager.process_desc_language(meta))

    assert meta.audio_languages == ["English", "French"]
    assert meta.subtitle_languages == ["Spanish"]
    assert meta.write_audio_languages is True
    assert meta.write_subtitle_languages is True
    assert ask_string.call_count == 2
