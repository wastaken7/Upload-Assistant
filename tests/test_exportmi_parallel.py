# ruff: noqa: S101

import asyncio
import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from src.exportmi import export_info


def test_export_info_runs_text_and_json_reports_concurrently(tmp_path: Path) -> None:
    media_file = tmp_path / "Example.Movie.2001.1080p.mkv"
    media_file.write_bytes(b"movie")
    (tmp_path / "tmp" / "release").mkdir(parents=True)
    # Both reports must be in flight at once for the barrier to release.
    barrier = threading.Barrier(2, timeout=5)

    def fake_parse(video: str, *, output: str, **_kwargs: object) -> str:
        barrier.wait()
        if output == "JSON":
            return '{"media": {"track": [{"@type": "General", "Format": "Matroska"}]}}'
        return f"General\nComplete name : {video}\n"

    with patch("src.exportmi.MediaInfo.parse", side_effect=fake_parse):
        mi = asyncio.run(export_info(str(media_file), False, "release", str(tmp_path)))

    assert mi["media"]["track"][0]["Format"] == "Matroska"
    report = (tmp_path / "tmp" / "release" / "MEDIAINFO.txt").read_text(encoding="utf-8")
    assert report == f"General\nComplete name : {media_file.name}\n"
    exported = json.loads((tmp_path / "tmp" / "release" / "MediaInfo.json").read_text(encoding="utf-8"))
    assert exported["media"]["track"][0]["Format"] == "Matroska"


def _write_reports_fixture(tmp_path: Path) -> Path:
    media_file = tmp_path / "Example.Movie.2001.1080p.mkv"
    media_file.write_bytes(b"movie")
    (tmp_path / "tmp" / "release").mkdir(parents=True)
    return media_file


def _fake_parse(delay: float):
    def fake_parse(_video: str, *, output: str, **_kwargs: object) -> str:
        time.sleep(delay)
        if output == "JSON":
            return '{"media": {"track": [{"@type": "General"}]}}'
        return "General\n"

    return fake_parse


def test_export_info_warns_when_mediainfo_is_slow(tmp_path: Path) -> None:
    media_file = _write_reports_fixture(tmp_path)

    with (
        patch("src.exportmi.MEDIAINFO_SLOW_NOTICE_SECONDS", 0.05),
        patch("src.exportmi.MediaInfo.parse", side_effect=_fake_parse(0.3)),
        patch("src.exportmi.logger") as logger,
    ):
        asyncio.run(export_info(str(media_file), False, "release", str(tmp_path)))

    logger.warning.assert_called_once()
    assert "MediaInfo is still reading the file" in logger.warning.call_args.args[0]
    assert (tmp_path / "tmp" / "release" / "MediaInfo.json").exists()


def test_export_info_does_not_warn_when_mediainfo_is_fast(tmp_path: Path) -> None:
    media_file = _write_reports_fixture(tmp_path)

    with (
        patch("src.exportmi.MediaInfo.parse", side_effect=_fake_parse(0)),
        patch("src.exportmi.logger") as logger,
    ):
        asyncio.run(export_info(str(media_file), False, "release", str(tmp_path)))

    logger.warning.assert_not_called()


def test_export_info_waits_for_both_reports_before_raising(tmp_path: Path) -> None:
    media_file = _write_reports_fixture(tmp_path)
    json_finished = threading.Event()

    def fake_parse(_video: str, *, output: str, **_kwargs: object) -> str:
        if output == "JSON":
            time.sleep(0.2)
            json_finished.set()
            return '{"media": {"track": [{"@type": "General"}]}}'
        raise RuntimeError("text report failed")

    async def run_export() -> bool:
        with pytest.raises(RuntimeError, match="text report failed"):
            await export_info(str(media_file), False, "release", str(tmp_path))
        # Checked before asyncio.run joins the worker threads on shutdown.
        return json_finished.is_set()

    with patch("src.exportmi.MediaInfo.parse", side_effect=fake_parse):
        assert asyncio.run(run_export())
