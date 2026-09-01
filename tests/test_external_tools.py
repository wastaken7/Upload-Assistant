from pathlib import Path

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


def test_regular_mediainfo_is_reported_as_automatic_before_download(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(external_tools, "_host", lambda: ("windows", "x86_64"))
    monkeypatch.setattr(external_tools, "_is_android", lambda: False)
    monkeypatch.setattr(external_tools.shutil, "which", lambda _command: None)

    statuses = external_tools.check_external_tools({}, state_dir=tmp_path / "state", code_dir=tmp_path / "code")

    assert statuses["mediainfo_path"]["state"] == "automatic"
    assert "26.05" in statuses["mediainfo_path"]["message"]


def test_managed_dvd_mediainfo_uses_separate_legacy_version(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(external_tools, "_host", lambda: ("windows", "x86_64"))
    monkeypatch.setattr(external_tools, "_is_android", lambda: False)
    monkeypatch.setattr(external_tools.shutil, "which", lambda _command: None)
    binary = _make_executable(tmp_path / "state" / "bin" / "MI" / "windows" / "dvd" / "MediaInfo.exe")
    (binary.parent / "version_23.04").touch()

    statuses = external_tools.check_external_tools({}, state_dir=tmp_path / "state", code_dir=tmp_path / "code")

    dvd_status = statuses["dvd_mediainfo_path"]
    assert dvd_status["state"] == "available"
    assert dvd_status["badge"] == "Managed"
    assert dvd_status["version"] == "23.04"


def test_configured_dvd_mediainfo_requires_version_confirmation(tmp_path: Path) -> None:
    binary = _make_executable(tmp_path / "MediaInfo")

    statuses = external_tools.check_external_tools(
        {"dvd_mediainfo_path": str(binary)},
        state_dir=tmp_path / "state",
        code_dir=tmp_path / "code",
    )

    dvd_status = statuses["dvd_mediainfo_path"]
    assert dvd_status["state"] == "warning"
    assert dvd_status["badge"] == "Check version"
    assert "23.04" in dvd_status["message"]
