# ruff: noqa: S101

import asyncio
from pathlib import Path
from unittest.mock import patch

from src.exportmi import export_info


def test_export_info_keeps_process_directory_for_next_queue_item(tmp_path: Path) -> None:
    media_file = tmp_path / "source" / "book.m4b"
    media_file.parent.mkdir()
    media_file.write_bytes(b"book")
    (tmp_path / "tmp" / "release").mkdir(parents=True)

    def fake_parse(_video: str, *, output: str, **_kwargs: object) -> str:
        if output == "JSON":
            return '{"media": {"track": [{"@type": "General"}]}}'
        return "General\n"

    starting_directory = Path.cwd()
    with patch("src.exportmi.MediaInfo.parse", side_effect=fake_parse):
        asyncio.run(export_info(str(media_file), False, "release", str(tmp_path)))

    assert Path.cwd() == starting_directory
    assert (tmp_path / "tmp" / "release" / "MediaInfo.json").exists()
