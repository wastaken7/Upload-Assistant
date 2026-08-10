import stat
from pathlib import Path

import pytest

from bin.get_mkbrr import MkbrrBinaryManager
from src.meta import Meta
from src.torrentcreate import TorrentCreator


@pytest.mark.asyncio
async def test_existing_local_mkbrr_is_used_on_unsupported_platform(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binary_path = tmp_path / "bin" / "mkbrr"
    binary_path.parent.mkdir()
    binary_path.write_text("#!/bin/sh\n", encoding="utf-8")
    binary_path.chmod(binary_path.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr("bin.get_mkbrr.platform.system", lambda: "Android")
    monkeypatch.setattr("bin.get_mkbrr.platform.machine", lambda: "aarch64")

    assert await MkbrrBinaryManager.ensure_mkbrr_binary(tmp_path, "v1.24.0") == str(binary_path)
    assert TorrentCreator.get_mkbrr_path(Meta(base_dir=str(tmp_path))) == str(binary_path)
