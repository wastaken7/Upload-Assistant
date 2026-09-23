# ruff: noqa: S101

import asyncio
from pathlib import Path
from unittest.mock import patch

from src.discparse import DiscParse
from src.meta import Meta


def test_dvd_info_uses_disc_paths_without_changing_process_directory(tmp_path: Path) -> None:
    disc_dir = tmp_path / "VIDEO_TS"
    disc_dir.mkdir()
    (disc_dir / "VTS_01_1.VOB").write_bytes(b"video")
    (disc_dir / "VTS_01_0.IFO").write_bytes(b"info")

    def fake_parse(video: str, *, output: str, **_kwargs: object) -> str:
        assert Path(video).parent == disc_dir
        if output == "JSON":
            return '{"media": {"track": [{}, {"Duration": "120"}]}}'
        return "General\n"

    starting_directory = Path.cwd()
    parser = DiscParse({"DEFAULT": {}})
    with (
        patch.object(parser, "setup_mediainfo_for_dvd", return_value=None),
        patch("src.discparse.MediaInfo.parse", side_effect=fake_parse),
    ):
        result = asyncio.run(parser.get_dvdinfo([{"path": str(disc_dir)}]))

    assert Path.cwd() == starting_directory
    assert result[0]["main_set"] == ["01_1.VOB"]
    assert result[0]["disc_size"] == 0.0


def test_hddvd_fallback_uses_disc_paths_without_changing_process_directory(tmp_path: Path) -> None:
    disc_dir = tmp_path / "HDDVD_TS"
    disc_dir.mkdir()
    (disc_dir / "feature.EVO").write_bytes(b"video")

    starting_directory = Path.cwd()
    parser = DiscParse({"DEFAULT": {}})
    with patch("src.discparse.MediaInfo.parse", return_value="General\n") as parse:
        result = asyncio.run(parser.get_hddvd_info([{"path": str(disc_dir)}], Meta()))

    assert Path.cwd() == starting_directory
    assert result[0]["largest_evo"] == str(disc_dir / "feature.EVO")
    parse.assert_called_once_with(str(disc_dir / "feature.EVO"), output="STRING", full=False)
