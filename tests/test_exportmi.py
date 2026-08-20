# ruff: noqa: S101
import asyncio
import ntpath
import subprocess
from unittest.mock import Mock, patch

import pytest

from bin.download_integrity import SHA256_BY_ASSET
from src.mediainfo import MediaInfo, _binary, _input_path, strip_report_by_line


def test_cli_backed_mediainfo_preserves_track_access() -> None:
    report = '{"media": {"track": [{"@type": "General", "Duration": "120.5"}, {"@type": "Audio", "BitRate": "640000"}]}}'

    with patch("src.mediainfo.run_mediainfo", return_value=report):
        parsed = MediaInfo.parse("audio.mka")

    general, audio = parsed.tracks
    assert general.track_type == "General"
    assert general.duration == 120500.0
    assert audio.to_data()["bit_rate"] == "640000"


def test_cli_backed_mediainfo_returns_requested_text() -> None:
    with patch("src.mediainfo.run_mediainfo", return_value="General\nComplete name") as run:
        report = MediaInfo.parse("video.mkv", output="STRING", full=False)

    assert report == "General\nComplete name"
    run.assert_called_once_with("video.mkv", output="STRING", full=False, inform=None)


@pytest.mark.parametrize(
    "report_by_line",
    [
        "ReportBy: MediaInfoLib - v26.05\n",
        "ReportBy                                 : MediaInfoLib - v26.05\r\n",
        "  reportby : MediaInfoLib - v27.01\n",
    ],
)
def test_strip_report_by_line_handles_mediainfo_formatting(report_by_line: str) -> None:
    report = f"General\nComplete name : example.mkv\n\n{report_by_line}Video\nFormat : AVC\n"

    assert strip_report_by_line(report) == "General\nComplete name : example.mkv\n\nVideo\nFormat : AVC\n"


def test_strip_report_by_line_handles_bare_carriage_return_boundaries() -> None:
    report = "General\rComplete name : example.mkv\rReportBy : MediaInfoLib - v26.05\rVideo\rFormat : AVC\r"

    assert strip_report_by_line(report) == "General\rComplete name : example.mkv\rVideo\rFormat : AVC\r"


def test_text_reports_always_request_mediainfo_version() -> None:
    completed = Mock(returncode=0, stdout="General", stderr="")
    with patch("src.mediainfo._binary", return_value="mediainfo"), patch("src.mediainfo.subprocess.run", return_value=completed) as run:
        from src.mediainfo import run_mediainfo

        run_mediainfo("video.mkv", output="STRING", full=False)

    assert run.call_args.args[0] == ["mediainfo", "--inform_version=1", "video.mkv"]


def test_mediainfo_uses_extended_windows_path_for_long_local_files() -> None:
    path = "C:\\" + "a" * 257

    with patch("src.mediainfo.platform.system", return_value="Windows"):
        assert _input_path(path) == f"\\\\?\\{path}"


def test_mediainfo_uses_extended_windows_path_for_long_unc_files() -> None:
    path = "\\\\server\\share\\" + "a" * 250

    with patch("src.mediainfo.platform.system", return_value="Windows"):
        assert _input_path(path) == f"\\\\?\\UNC\\{path[2:]}"


@pytest.mark.parametrize(
    ("path", "prefix"),
    [
        ("C:/" + "segment/" * 90 + "./nested/../file.m4b", "\\\\?\\"),
        ("//server/share/" + "segment/" * 90 + "./nested/../file.m4b", "\\\\?\\UNC\\"),
    ],
)
def test_mediainfo_normalizes_long_windows_paths_before_prefixing(path: str, prefix: str) -> None:
    normalized = ntpath.normpath(path)

    with patch("src.mediainfo.platform.system", return_value="Windows"):
        assert _input_path(path) == f"{prefix}{normalized[2:] if prefix.endswith('UNC\\') else normalized}"


def test_mediainfo_does_not_modify_short_or_non_windows_paths() -> None:
    short_path = "C:\\short\\file.m4b"
    long_path = "C:\\" + "a" * 257

    with patch("src.mediainfo.platform.system", return_value="Windows"):
        assert _input_path(short_path) == short_path
        assert _input_path(f"\\\\?\\{long_path}") == f"\\\\?\\{long_path}"
    with patch("src.mediainfo.platform.system", return_value="Linux"):
        assert _input_path(long_path) == long_path


def test_mediainfo_passes_extended_path_to_cli() -> None:
    path = "C:\\" + "a" * 257
    completed = Mock(returncode=0, stdout="General", stderr="")

    with (
        patch("src.mediainfo.platform.system", return_value="Windows"),
        patch("src.mediainfo._binary", return_value="mediainfo"),
        patch("src.mediainfo.subprocess.run", return_value=completed) as run,
    ):
        from src.mediainfo import run_mediainfo

        run_mediainfo(path, output="STRING", full=False)

    assert run.call_args.args[0][-1] == f"\\\\?\\{path}"


def test_mediainfo_prefers_configured_binary(tmp_path) -> None:
    executable = tmp_path / "MediaInfo.exe"
    executable.touch()

    with patch("src.mediainfo.configured_binary", return_value=str(executable)):
        from src.mediainfo import _binary

        assert _binary() == str(executable)


def test_mediainfo_uses_tolerant_utf8_output_decoding() -> None:
    completed = Mock(returncode=0, stdout="General", stderr="")
    with patch("src.mediainfo._binary", return_value="mediainfo"), patch("src.mediainfo.subprocess.run", return_value=completed) as run:
        from src.mediainfo import run_mediainfo

        run_mediainfo("audio.m4b")

    assert run.call_args.kwargs["encoding"] == "utf-8"
    assert run.call_args.kwargs["errors"] == "replace"


def test_mediainfo_uses_state_managed_binary_before_system_path() -> None:
    with patch("src.mediainfo.MediaInfoBinaryManager.find_existing_binary", return_value="/home/user/.local/share/Upload-Assistant/bin/MI/linux/mediainfo") as find_existing:
        assert _binary() == "/home/user/.local/share/Upload-Assistant/bin/MI/linux/mediainfo"

    find_existing.assert_called_once()


def test_mediainfo_failure_reports_command_and_both_output_streams() -> None:
    completed = Mock(returncode=1, stdout="could not parse file", stderr="input error")
    with patch("src.mediainfo._binary", return_value="mediainfo"), patch("src.mediainfo.subprocess.run", return_value=completed):
        from src.mediainfo import run_mediainfo

        with pytest.raises(RuntimeError) as exc_info:
            run_mediainfo("video.mkv", output="STRING", full=False)

    assert str(exc_info.value) == (
        "MediaInfo failed with exit code 1\nCommand: ['mediainfo', '--inform_version=1', 'video.mkv']\nstdout:\ncould not parse file\nstderr:\ninput error"
    )


def test_mediainfo_timeout_becomes_runtime_error() -> None:
    with patch("src.mediainfo._binary", return_value="mediainfo"), patch("src.mediainfo.subprocess.run", side_effect=subprocess.TimeoutExpired("mediainfo", 900)):
        from src.mediainfo import run_mediainfo

        with pytest.raises(RuntimeError, match="timed out"):
            run_mediainfo("video.mkv")


def test_all_supported_mediainfo_downloads_have_pinned_hashes() -> None:
    assert {
        "MediaInfo_CLI_26.05_Windows_x64.zip",
        "MediaInfo_CLI_26.05_Windows_ARM64.zip",
        "MediaInfo_CLI_26.05_Lambda_x86_64.zip",
        "MediaInfo_CLI_26.05_Lambda_arm64.zip",
        "MediaInfo_CLI_26.05_Mac.dmg",
    } <= SHA256_BY_ASSET.keys()


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("Windows", "AMD64", ("windows", "MediaInfo_CLI_26.05_Windows_x64.zip", "MediaInfo.exe", "zip")),
        ("Windows", "ARM64", ("windows/arm64", "MediaInfo_CLI_26.05_Windows_ARM64.zip", "MediaInfo.exe", "zip")),
        ("Darwin", "arm64", ("macos", "MediaInfo_CLI_26.05_Mac.dmg", "mediainfo", "dmg")),
    ],
)
def test_mediainfo_platform_info_uses_official_asset(system, machine, expected) -> None:
    from bin.get_mediainfo import MediaInfoBinaryManager

    with patch("bin.get_mediainfo.platform.system", return_value=system), patch("bin.get_mediainfo.platform.machine", return_value=machine):
        assert MediaInfoBinaryManager._platform_info() == expected


def test_android_uses_mediainfo_from_path(tmp_path) -> None:
    from bin.get_mediainfo import MediaInfoBinaryManager

    with (
        patch.object(MediaInfoBinaryManager, "_is_android", return_value=True),
        patch("bin.get_mediainfo.shutil.which", return_value="/data/data/com.termux/files/usr/bin/mediainfo"),
    ):
        assert asyncio.run(MediaInfoBinaryManager.ensure_mediainfo_binary(tmp_path)) == "/data/data/com.termux/files/usr/bin/mediainfo"


def test_android_without_mediainfo_has_install_instruction(tmp_path) -> None:
    from bin.get_mediainfo import MediaInfoBinaryManager

    with (
        patch.object(MediaInfoBinaryManager, "_is_android", return_value=True),
        patch("bin.get_mediainfo.shutil.which", return_value=None),
        pytest.raises(RuntimeError, match=r"pkg install mediainfo"),
    ):
        asyncio.run(MediaInfoBinaryManager.ensure_mediainfo_binary(tmp_path))


def test_macos_uses_downloaded_binary_before_path(tmp_path) -> None:
    from bin.get_mediainfo import MediaInfoBinaryManager

    with (
        patch.object(MediaInfoBinaryManager, "_is_android", return_value=False),
        patch.object(MediaInfoBinaryManager, "_is_macos", return_value=True),
        patch("bin.get_mediainfo.shutil.which", return_value="/opt/homebrew/bin/mediainfo"),
        patch.object(MediaInfoBinaryManager, "_platform_info", return_value=("macos", "MediaInfo_CLI_26.05_Mac.dmg", "mediainfo", "dmg")),
    ):
        binary = tmp_path / "bin" / "MI" / "macos" / "mediainfo"
        binary.parent.mkdir(parents=True)
        binary.touch()
        (binary.parent / f"version_{MediaInfoBinaryManager.VERSION}").touch()
        assert asyncio.run(MediaInfoBinaryManager.ensure_mediainfo_binary(tmp_path)) == str(binary)


def test_macos_falls_back_to_path_when_downloaded_binary_is_unavailable(tmp_path) -> None:
    from bin.get_mediainfo import MediaInfoBinaryManager

    with (
        patch.object(MediaInfoBinaryManager, "_is_android", return_value=False),
        patch.object(MediaInfoBinaryManager, "_is_macos", return_value=True),
        patch.object(MediaInfoBinaryManager, "_platform_info", return_value=("macos", "MediaInfo_CLI_26.05_Mac.dmg", "mediainfo", "dmg")),
        patch("bin.get_mediainfo.shutil.which", return_value="/opt/homebrew/bin/mediainfo"),
    ):
        assert MediaInfoBinaryManager.find_existing_binary(tmp_path) == "/opt/homebrew/bin/mediainfo"


def test_linux_falls_back_to_path_when_downloaded_binary_is_unavailable(tmp_path) -> None:
    from bin.get_mediainfo import MediaInfoBinaryManager

    with (
        patch.object(MediaInfoBinaryManager, "_is_android", return_value=False),
        patch.object(MediaInfoBinaryManager, "_is_macos", return_value=False),
        patch.object(MediaInfoBinaryManager, "_platform_info", return_value=("linux", "MediaInfo_CLI_26.05_Lambda_x86_64.zip", "mediainfo", "zip")),
        patch("bin.get_mediainfo.shutil.which", return_value="/usr/bin/mediainfo"),
    ):
        assert MediaInfoBinaryManager.find_existing_binary(tmp_path) == "/usr/bin/mediainfo"
