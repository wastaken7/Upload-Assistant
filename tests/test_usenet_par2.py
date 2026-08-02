# ruff: noqa: S101

from pathlib import Path

import pytest

from src import usenetcreate
from src.meta import Meta


@pytest.mark.asyncio
async def test_skip_archive_sets_par2_base_path_to_source_directory(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source_file = source_dir / "release.mkv"
    source_file.write_bytes(b"video")
    staging_dir = tmp_path / "staging"

    captured: dict[str, object] = {}

    async def fake_check_binary(*_args, **_kwargs):
        return "par2"

    async def fake_run_par2(cmd, cwd=None):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        par2_file = Path(cmd[-2])
        par2_file.write_bytes(b"par2")

    monkeypatch.setattr(usenetcreate, "check_binary", fake_check_binary)
    monkeypatch.setattr(usenetcreate, "run_par2_with_progress", fake_run_par2)

    meta = Meta({"base_dir": str(tmp_path), "path": str(source_file), "uuid": "test", "basename_no_ext": "release"})
    result = await usenetcreate.prepare_and_upload_usenet(
        meta,
        {"USENET": {"skip_archive": True, "usenet_tmp_dir": str(staging_dir)}},
        prepare_only=True,
    )

    assert result == str(source_dir)
    assert captured["cwd"] == str(source_dir)
    assert f"-B{source_dir}" in captured["cmd"]
