# ruff: noqa: S101

from types import SimpleNamespace

import pytest

from src import disc_menus
from src.disc_menus import DiscMenus, discard_previous_menu_capture_files
from src.meta import Meta


def test_discard_previous_menu_capture_files_only_removes_the_current_vob_batch(tmp_path) -> None:
    current_first = tmp_path / "DVD-VIDEO_TS-001.png"
    current_second = tmp_path / "DVD-VIDEO_TS-002.png"
    other_vob = tmp_path / "DVD-VTS_01_0-001.png"
    current_first.write_bytes(b"old")
    current_second.write_bytes(b"old")
    other_vob.write_bytes(b"keep")

    discard_previous_menu_capture_files(tmp_path / "DVD-VIDEO_TS-%03d.png")

    assert not current_first.exists()
    assert not current_second.exists()
    assert other_vob.exists()


@pytest.mark.asyncio
async def test_dvd_menu_capture_uses_dvd_par_override(monkeypatch, tmp_path) -> None:
    disc_path = tmp_path / "VIDEO_TS"
    disc_path.mkdir()
    (disc_path / "VTS_01_0.VOB").write_bytes(b"v" * 50001)
    commands = []

    def parse_stub(_path):
        video = SimpleNamespace(track_type="Video", width=720, height=480, pixel_aspect_ratio=1.2, display_aspect_ratio=1.8, duration=1000)
        return SimpleNamespace(tracks=[video])

    async def subprocess_stub(*args, **_kwargs):
        commands.append(args)

        async def communicate():
            return b"", b""

        return SimpleNamespace(returncode=0, communicate=communicate)

    monkeypatch.setattr(disc_menus.MediaInfo, "parse", parse_stub)
    monkeypatch.setattr(disc_menus.asyncio, "create_subprocess_exec", subprocess_stub)
    meta = Meta(base_dir=str(tmp_path), uuid="dvd", discs=[{"type": "DVD", "path": str(disc_path), "name": "DVD"}])
    manager = DiscMenus(meta, {"DEFAULT": {"scale_screenshots_for_par": False, "scale_dvd_screenshots_for_par": True}})

    await manager.auto_capture_dvd_menus(meta)

    assert len(commands) == 1
    assert "scale=864:480,format=rgb24" in commands[0][commands[0].index("-vf") + 1]
