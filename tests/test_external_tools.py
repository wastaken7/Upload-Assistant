from pathlib import Path

from bin.binary_dependencies import DEPENDENCY_VERSIONS
from bin.get_mediainfo import MediaInfoBinaryManager
from src import external_tools


def _make_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    path.chmod(path.stat().st_mode | 0o111)
    return path


def test_invalid_configured_path_is_reported(tmp_path: Path) -> None:
    statuses = external_tools.check_external_tools(
        {"ffmpeg_path": str(tmp_path / "missing-ffmpeg")},
        state_dir=tmp_path / "state",
        code_dir=tmp_path / "code",
    )

    assert statuses["ffmpeg_path"]["state"] == "invalid"
    assert statuses["ffmpeg_path"]["badge"] == "Invalid path"


def test_embedded_nul_configured_path_is_reported_as_invalid(tmp_path: Path) -> None:
    statuses = external_tools.check_external_tools(
        {"ffmpeg_path": "\x00"},
        state_dir=tmp_path / "state",
        code_dir=tmp_path / "code",
    )

    assert statuses["ffmpeg_path"]["state"] == "invalid"
    assert statuses["ffmpeg_path"]["badge"] == "Invalid path"


def test_regular_mediainfo_is_reported_as_automatic_before_download(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(external_tools, "_host", lambda: ("windows", "x86_64"))
    monkeypatch.setattr(external_tools, "_is_android", lambda: False)
    monkeypatch.setattr(external_tools.shutil, "which", lambda _command: None)

    statuses = external_tools.check_external_tools({}, state_dir=tmp_path / "state", code_dir=tmp_path / "code")

    assert statuses["mediainfo_path"]["state"] == "automatic"
    assert MediaInfoBinaryManager.VERSION in statuses["mediainfo_path"]["message"]


def test_managed_tool_status_uses_centralized_versions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(external_tools, "_host", lambda: ("windows", "x86_64"))
    monkeypatch.setitem(DEPENDENCY_VERSIONS, "ffmpeg", "10.2")
    monkeypatch.setitem(DEPENDENCY_VERSIONS, "bdinfo", "v3.4.5")

    ffmpeg = external_tools._managed_paths("ffmpeg_path", tmp_path, tmp_path)[0]
    bdinfo = external_tools._managed_paths("bdinfo_path", tmp_path, tmp_path)[0]

    assert ffmpeg[1] == ffmpeg[0].parent / "version_10.2"
    assert ffmpeg[2] == "10.2"
    assert bdinfo[1] == bdinfo[0].parent / "v3.4.5"
    assert bdinfo[2] == "3.4.5"
    assert "10.2" in external_tools._automatic_message("ffmpeg_path")


def test_managed_mediainfo_is_reported_with_its_pinned_version(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(external_tools, "_host", lambda: ("windows", "x86_64"))
    monkeypatch.setattr(external_tools, "_is_android", lambda: False)
    monkeypatch.setattr(external_tools.shutil, "which", lambda _command: None)
    binary = _make_executable(tmp_path / "state" / "bin" / "MI" / "windows" / "MediaInfo.exe")
    (binary.parent / f"version_{MediaInfoBinaryManager.VERSION}").touch()

    statuses = external_tools.check_external_tools({}, state_dir=tmp_path / "state", code_dir=tmp_path / "code")

    assert "dvd_mediainfo_path" not in statuses
    assert statuses["mediainfo_path"]["state"] == "available"
    assert statuses["mediainfo_path"]["badge"] == "Managed"
    assert statuses["mediainfo_path"]["version"] == MediaInfoBinaryManager.VERSION
