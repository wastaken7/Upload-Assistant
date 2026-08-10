# ruff: noqa: S101

from src.disc_menus import discard_previous_menu_capture_files


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
