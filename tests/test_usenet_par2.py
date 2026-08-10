# ruff: noqa: S101

import hashlib
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


@pytest.mark.asyncio
async def test_archive_retry_removes_only_stale_current_archive_volumes_before_7z(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "release.mkv").write_bytes(b"video")

    staging_root = tmp_path / "staging"
    release_uuid = "retry-test"
    uuid_hash = hashlib.sha256(release_uuid.encode("utf-8")).hexdigest()[:8]
    usenet_dir = staging_root / f"{release_uuid}_{uuid_hash}" / "usenet"
    usenet_dir.mkdir(parents=True)
    stale_volume = usenet_dir / "release.7z.001"
    stale_volume.write_bytes(b"partial")
    unrelated_file = usenet_dir / "keep.txt"
    unrelated_file.write_bytes(b"unrelated")

    async def fake_check_binary(binary_name, *_args, **_kwargs):
        return binary_name

    async def fake_run_7z(cmd, *_args):
        archive_out = Path(cmd[-2])
        fresh_volume = Path(f"{archive_out}.001")
        assert not fresh_volume.exists(), "stale current-attempt archive volume still exists when 7z starts"
        fresh_volume.write_bytes(b"fresh")

    async def fake_run_par2(cmd, cwd=None):
        del cwd
        Path(cmd[4]).write_bytes(b"par2")

    monkeypatch.setattr(usenetcreate, "check_binary", fake_check_binary)
    monkeypatch.setattr(usenetcreate, "run_7z_with_progress", fake_run_7z)
    monkeypatch.setattr(usenetcreate, "run_par2_with_progress", fake_run_par2)

    meta = Meta({"base_dir": str(tmp_path), "path": str(source_dir), "uuid": release_uuid, "basename_no_ext": "release"})
    result = await usenetcreate.prepare_and_upload_usenet(
        meta,
        {"USENET": {"usenet_tmp_dir": str(staging_root), "rar_volume_size": "100m"}},
        prepare_only=True,
    )

    assert result == str(usenet_dir)
    assert stale_volume.read_bytes() == b"fresh"
    assert unrelated_file.read_bytes() == b"unrelated"
