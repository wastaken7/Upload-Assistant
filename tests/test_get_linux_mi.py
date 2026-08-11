# ruff: noqa: S101
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from bin.get_linux_mi import download_dvd_mediainfo, extract_linux


def test_dvd_extraction_does_not_overwrite_regular_linux_cli(tmp_path: Path) -> None:
    linux_dir = tmp_path / "bin" / "MI" / "linux"
    dvd_dir = linux_dir / "dvd"
    dvd_dir.mkdir(parents=True)
    regular_cli = linux_dir / "mediainfo"
    regular_cli.write_bytes(b"26.05")
    cli_archive = tmp_path / "cli.zip"
    lib_archive = tmp_path / "lib.zip"
    with ZipFile(cli_archive, "w") as archive:
        archive.writestr("mediainfo", b"23.04")
    with ZipFile(lib_archive, "w") as archive:
        archive.writestr("lib/libmediainfo.so.0.0.0", b"dvd-library")

    extract_linux(cli_archive, lib_archive, dvd_dir)

    assert regular_cli.read_bytes() == b"26.05"
    assert (dvd_dir / "mediainfo").read_bytes() == b"23.04"
    assert (dvd_dir / "libmediainfo.so.0").read_bytes() == b"dvd-library"


def test_dvd_download_keeps_its_version_marker_separate(tmp_path: Path) -> None:
    linux_dir = tmp_path / "bin" / "MI" / "linux"
    linux_dir.mkdir(parents=True)
    (linux_dir / "mediainfo").write_bytes(b"26.05")
    (linux_dir / "version_26.05").touch()

    def write_archive(url: str, destination: Path) -> None:
        with ZipFile(destination, "w") as archive:
            if "libmediainfo0" in url:
                archive.writestr("lib/libmediainfo.so.0.0.0", b"dvd-library")
            else:
                archive.writestr("mediainfo", b"23.04")

    with (
        patch("bin.get_linux_mi.platform.system", return_value="Linux"),
        patch("bin.get_linux_mi.platform.machine", return_value="x86_64"),
        patch("bin.get_linux_mi.download_file", side_effect=write_archive),
    ):
        assert download_dvd_mediainfo(str(tmp_path)) == str(linux_dir / "dvd" / "mediainfo")

    assert (linux_dir / "mediainfo").read_bytes() == b"26.05"
    assert (linux_dir / "version_26.05").is_file()
    assert not (linux_dir / "version_23.04").exists()
    assert (linux_dir / "dvd" / "version_23.04").is_file()
