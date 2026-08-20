"""Compatibility layer backed by the official MediaInfo CLI."""

import json
import ntpath
import platform
import re
import subprocess
from pathlib import Path
from typing import Any

from bin.get_mediainfo import MediaInfoBinaryManager
from src.app_paths import STATE_DIR
from src.binaries import configured_binary

_REPORT_BY_LINE = re.compile(r"(?<![^\r\n])[ \t]*ReportBy[ \t]*:[^\r\n]*(?:\r\n?|\n)?", re.IGNORECASE)


def strip_report_by_line(report: str) -> str:
    """Remove MediaInfo's optional ReportBy version line from a text report."""
    return _REPORT_BY_LINE.sub("", report)


def _binary() -> str:
    if configured := configured_binary("mediainfo_path"):
        return configured
    binary = MediaInfoBinaryManager.find_existing_binary(STATE_DIR)
    if binary is None:
        raise RuntimeError("MediaInfo CLI is not installed; run Upload Assistant so it can download bin/MI first")
    return binary


def _input_path(path: str | Path) -> str:
    """Return a Windows extended-length path when MediaInfo needs one."""
    value = str(path)
    if platform.system() != "Windows" or value.startswith("\\\\?\\") or not ntpath.isabs(value):
        return value
    normalized = ntpath.normpath(value)
    if len(normalized) < 260:
        return value
    if normalized.startswith("\\\\"):
        return f"\\\\?\\UNC\\{normalized[2:]}"
    return f"\\\\?\\{normalized}"


def run_mediainfo(path: str | Path, *, output: str | None = None, full: bool = True, inform: str | None = None) -> str:
    command = [_binary()]
    if output != "JSON":
        command.append("--inform_version=1")
    if full:
        command.append("--Full")
    if inform:
        command.append(f"--Inform={inform}")
    elif output and output != "STRING":
        command.append(f"--Output={output}")
    command.append(_input_path(path))
    try:
        result = subprocess.run(  # noqa: S603
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=900,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("MediaInfo timed out after 15 minutes") from exc
    if result.returncode != 0:
        raise RuntimeError(
            f"MediaInfo failed with exit code {result.returncode}\n"
            f"Command: {command!r}\n"
            f"stdout:\n{result.stdout.strip() or '(empty)'}\n"
            f"stderr:\n{result.stderr.strip() or '(empty)'}"
        )
    return result.stdout


def _snake_case(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).replace("@", "").strip("_").lower()


class MediaInfoTrack:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @property
    def track_type(self) -> str | None:
        value = self._data.get("@type")
        return str(value) if value is not None else None

    def to_data(self) -> dict[str, Any]:
        return {_snake_case(key): value for key, value in self._data.items()}

    def __getattr__(self, name: str) -> Any:
        for key, value in self._data.items():
            if _snake_case(key) == name:
                if name == "duration" and value is not None:
                    try:
                        return float(value) * 1000
                    except TypeError, ValueError:
                        return value
                return value
        return None


class MediaInfoResult:
    def __init__(self, report: dict[str, Any]) -> None:
        tracks = report.get("media", {}).get("track", [])
        self.tracks = [MediaInfoTrack(track) for track in tracks if isinstance(track, dict)]


class MediaInfo:
    """Subset of the previous Python binding API used by Upload Assistant."""

    @staticmethod
    def parse(
        filename: str | Path,
        *,
        output: str | None = None,
        full: bool = True,
        mediainfo_options: dict[str, str] | None = None,
        **_kwargs: Any,
    ) -> MediaInfoResult | str:
        inform = (mediainfo_options or {}).get("inform")
        if output is not None or inform:
            return run_mediainfo(filename, output=output, full=full, inform=inform)
        return MediaInfoResult(json.loads(run_mediainfo(filename, output="JSON", full=full)))
