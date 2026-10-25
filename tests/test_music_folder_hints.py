"""Edition details found only in the folder name are confirmed before upload."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

import upload
from src.meta import Meta
from src.music.models import MusicRelease
from src.music.validation import resolve_orpheus_edition
from upload import _confirm_music_folder_hints


@pytest.fixture(autouse=True)
def setup_globals() -> None:
    upload.load_heavy_globals()


def _meta(**overrides: Any) -> Meta:
    values: dict[str, Any] = {
        "category": "MUSIC",
        "trackers": ["ORPHEUS"],
        "music_release": {
            "root": "/music/Fictional Band - Paper Moons (2019) [FLAC] {FIC001}",
            "fields": {
                "media": {"value": "WEB", "source": "user", "confidence": 1.0},
                "edition_year": {"value": 2019, "source": "user", "confidence": 1.0},
                "catalogue_number": {"value": "FIC001", "source": "directory", "confidence": 0.6},
            },
        },
    }
    values.update(overrides)
    return Meta(**values)


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", [True, False])
async def test_folder_catalogue_number_is_sent_only_when_confirmed(answer: bool) -> None:
    meta = _meta()

    with (
        patch("upload.CLI_UI.ask_yes_no", return_value=answer) as ask,
        patch("upload._refresh_music_meta", new=AsyncMock()) as refresh,
    ):
        await _confirm_music_folder_hints(meta)

    ask.assert_called_once()
    assert "FIC001" in ask.call_args.args[0]
    fields = meta.music_release["fields"]
    if answer:
        assert fields["release_catalogue_number"] == {"value": "FIC001", "source": "user", "confidence": 1.0}
        refresh.assert_awaited_once()
        # Validation now treats it as confirmed and stops warning about it.
        edition = resolve_orpheus_edition(MusicRelease.from_dict(meta.music_release))
        assert edition.catalogue_number == "FIC001"
        assert edition.folder_hints == ()
    else:
        assert "release_catalogue_number" not in fields
        refresh.assert_not_awaited()
    assert fields["catalogue_number"]["source"] == "directory"


@pytest.mark.asyncio
@pytest.mark.parametrize("overrides", [{"unattended": True}, {"trackers": ["FAKE"]}])
async def test_folder_hints_are_not_asked_unattended_or_without_orpheus(overrides: dict[str, Any]) -> None:
    meta = _meta(**overrides)

    with patch("upload.CLI_UI.ask_yes_no") as ask:
        await _confirm_music_folder_hints(meta)

    ask.assert_not_called()
