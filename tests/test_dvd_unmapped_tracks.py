"""DVD IFO stream slots that no program chain plays must not count as tracks."""

# ruff: noqa: S101

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.exportmi import export_info
from src.languages import LanguagesManager
from src.meta import Meta

IFO_JSON: dict[str, Any] = {
    "media": {
        "track": [
            {"@type": "General", "Format": "DVD Video"},
            {"@type": "Video", "ID": "224"},
            {"@type": "Audio", "ID": "189-128", "Format": "AC-3", "Language": "fr"},
            {"@type": "Audio", "Format": "AC-3", "Language": "en"},
            {"@type": "Text", "ID": "189-32", "Format": "RLE", "Language": "de"},
            {"@type": "Text", "Format": "RLE"},
            {"@type": "Text", "ID": {}, "Format": "RLE"},
        ]
    }
}

IFO_TEXT = (
    "General\nFormat : DVD Video\n\n"
    "Audio #1\nID : 189 (0xBD)-128 (0x80)\nFormat : AC-3\nLanguage : French\n\n"
    "Audio #2\nFormat : AC-3\nLanguage : English\n\n"
    "Text #1\nID : 189 (0xBD)-32 (0x20)\nFormat : RLE\nLanguage : German\n\n"
    "Text #2\nFormat : RLE\n\n"
    "Text #3\nFormat : RLE\n"
)


def _fake_parse(_video: str, *, output: str, **_kwargs: object) -> str:
    return json.dumps(IFO_JSON) if output == "JSON" else IFO_TEXT


@pytest.mark.parametrize("is_dvd", [True, False])
def test_export_info_drops_dvd_tracks_without_id(tmp_path: Path, is_dvd: bool) -> None:
    (tmp_path / "tmp" / "release").mkdir(parents=True)
    with patch("src.exportmi.MediaInfo.parse", side_effect=_fake_parse):
        mi = asyncio.run(export_info(str(tmp_path / "VTS_01_0.IFO"), False, "release", str(tmp_path), is_dvd=is_dvd))

    tracks = mi["media"]["track"]
    audio = [t for t in tracks if t["@type"] == "Audio"]
    text = [t for t in tracks if t["@type"] == "Text"]
    if is_dvd:
        assert [t["ID"] for t in audio] == ["189-128"]
        assert [t["ID"] for t in text] == ["189-32"]
    else:
        assert len(audio) == 2
        assert len(text) == 3
    # The text report is the untouched MediaInfo output.
    assert (tmp_path / "tmp" / "release" / "MEDIAINFO.txt").read_text(encoding="utf-8") == IFO_TEXT


@pytest.mark.parametrize("is_disc", ["DVD", ""])
def test_parsed_mediainfo_skips_dvd_tracks_without_id(tmp_path: Path, is_disc: str) -> None:
    meta = Meta(base_dir=str(tmp_path), uuid="Fictional.Movie.2001", is_disc=is_disc)
    release_dir = tmp_path / "tmp" / meta.uuid
    release_dir.mkdir(parents=True)
    (release_dir / "MEDIAINFO.txt").write_text(IFO_TEXT, encoding="utf-8")

    parsed = asyncio.run(LanguagesManager().parsed_mediainfo(meta))

    if is_disc == "DVD":
        assert parsed["audio"] == [{"format": "AC-3", "language": "French"}]
        assert parsed["text"] == [{"format": "RLE", "language": "German"}]
    else:
        assert len(parsed["audio"]) == 2
        assert len(parsed["text"]) == 3
