"""Read-only availability checks for optional external tools.

The WebUI uses this module to report the same configured, PATH, and managed
binary locations that Upload Assistant uses at runtime. Checks never download
or modify a tool installation.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


EXTERNAL_TOOL_KEYS = (
    "ffmpeg_path",
    "ffprobe_path",
    "mediainfo_path",
    "dvd_mediainfo_path",
    "bdinfo_path",
    "mkbrr_path",
    "dovi_tool_path",
    "hdr10plus_tool_path",
    "unrar_path",
)

_LABELS = {
    "ffmpeg_path": "FFmpeg",
    "ffprobe_path": "FFprobe",
    "mediainfo_path": "MediaInfo",
    "dvd_mediainfo_path": "DVD MediaInfo",
    "bdinfo_path": "BDInfo",
    "mkbrr_path": "mkbrr",
    "dovi_tool_path": "Dolby Vision Tool",
    "hdr10plus_tool_path": "HDR10+ Tool",
    "unrar_path": "UnRAR",
}

_COMMANDS = {
    "ffmpeg_path": "ffmpeg",
    "ffprobe_path": "ffprobe",
    "mediainfo_path": "mediainfo",
    "bdinfo_path": "bdinfo",
    "mkbrr_path": "mkbrr",
    "dovi_tool_path": "dovi_tool",
    "hdr10plus_tool_path": "hdr10plus_tool",
    "unrar_path": "unrar",
}

_PURPOSES = {
    "ffprobe_path": "It is only required by workflows that inspect streams with FFprobe.",
    "unrar_path": "It is only required when extracting RAR-based comic archives.",
}

_VERSION_PATTERN = re.compile(r"(?<!\d)(\d+\.\d+(?:\.\d+)?)(?!\d)")


def _host() -> tuple[str, str]:
    return platform.system().lower(), platform.machine().lower()


def _is_android() -> bool:
    return sys.platform == "android" or os.environ.get("PREFIX", "").startswith("/data/data/com.termux/")


def _is_usable_file(path: Path) -> bool:
    try:
        return path.is_file() and (os.name == "nt" or os.access(path, os.X_OK))
    except (OSError, ValueError):
        return False


def _version_from_marker(marker: Path) -> str:
    match = _VERSION_PATTERN.search(marker.name)
    return match.group(1) if match else ""


def _result(
    key: str,
    *,
    state: str,
    badge: str,
    tone: str,
    message: str,
    path: str = "",
    source: str = "",
    version: str = "",
) -> dict[str, str]:
    return {
        "key": key,
        "label": _LABELS[key],
        "state": state,
        "badge": badge,
        "tone": tone,
        "message": message,
        "path": path,
        "source": source,
        "version": version,
    }


def _available_result(key: str, path: Path | str, source: str, *, version: str = "") -> dict[str, str]:
    path_text = str(path)
    if key == "dvd_mediainfo_path":
        if not version:
            return _result(
                key,
                state="warning",
                badge="Check version",
                tone="warning",
                message="The executable is available, but its version could not be confirmed. DVD parsing requires MediaInfo 23.04.",
                path=path_text,
                source=source,
            )
        if version != "23.04":
            return _result(
                key,
                state="warning",
                badge="Wrong version",
                tone="warning",
                message=f"MediaInfo {version} is available, but DVD parsing requires version 23.04.",
                path=path_text,
                source=source,
                version=version,
            )

    badge = "Configured" if source == "Configured path" else "Managed" if source == "Managed by Upload Assistant" else "Detected"
    return _result(
        key,
        state="available",
        badge=badge,
        tone="success",
        message=f"{_LABELS[key]} is ready to use.",
        path=path_text,
        source=source,
        version=version,
    )


def _configured_result(key: str, raw_path: object) -> dict[str, str] | None:
    path_text = str(raw_path or "").strip()
    if not path_text:
        return None
    path = Path(path_text).expanduser()
    if not _is_usable_file(path):
        return _result(
            key,
            state="invalid",
            badge="Invalid path",
            tone="danger",
            message="The configured path does not point to an executable file on the Upload Assistant host.",
            path=str(path),
            source="Configured path",
        )
    return _available_result(key, path, "Configured path")


def _managed_paths(key: str, state_dir: Path, code_dir: Path) -> list[tuple[Path, Path | None, str]]:
    system, machine = _host()
    executable_suffix = ".exe" if system == "windows" else ""

    if key == "ffmpeg_path" and system == "windows":
        binary = state_dir / "bin" / "ffmpeg" / "windows" / "x64" / "ffmpeg.exe"
        return [(binary, binary.parent / "version_9.0.1", "9.0.1")]

    if key == "mediainfo_path" and not _is_android():
        folder = ""
        executable = "mediainfo"
        if system == "windows" and machine in {"amd64", "x86_64"}:
            folder, executable = "windows", "MediaInfo.exe"
        elif system == "windows" and machine in {"arm64", "aarch64"}:
            folder, executable = "windows/arm64", "MediaInfo.exe"
        elif system == "linux" and machine in {"amd64", "x86_64"}:
            folder = "linux"
        elif system == "linux" and machine in {"arm64", "aarch64"}:
            folder = "linux/arm64"
        elif system == "darwin" and machine in {"amd64", "x86_64", "arm64", "aarch64"}:
            folder = "macos"
        if folder:
            binary = state_dir / "bin" / "MI" / folder / executable
            return [(binary, binary.parent / "version_26.05", "26.05")]

    if key == "dvd_mediainfo_path":
        if system == "windows" and machine in {"amd64", "x86_64"}:
            binary = state_dir / "bin" / "MI" / "windows" / "dvd" / "MediaInfo.exe"
            return [(binary, binary.parent / "version_23.04", "23.04")]
        if system == "linux" and machine in {"amd64", "x86_64", "arm64", "aarch64"}:
            binary = state_dir / "bin" / "MI" / "linux" / "dvd" / "mediainfo"
            return [(binary, binary.parent / "version_23.04", "23.04")]

    platform_folders = {
        "windows": {"amd64": "windows/x86_64", "x86_64": "windows/x86_64"},
        "darwin": {"amd64": "macos/x86_64", "x86_64": "macos/x86_64", "arm64": "macos/arm64"},
        "linux": {
            "amd64": "linux/amd64",
            "x86_64": "linux/amd64",
            "arm64": "linux/arm64",
            "aarch64": "linux/arm64",
            "armv7l": "linux/arm",
            "armv6l": "linux/arm",
            "arm": "linux/arm",
        },
    }
    folder = platform_folders.get(system, {}).get(machine, "")
    if key == "bdinfo_path" and folder:
        binary = state_dir / "bin" / "bdinfo" / folder / f"bdinfo{executable_suffix}"
        return [(binary, binary.parent / "v0.4.0", "0.4.0")]

    if key == "mkbrr_path" and folder:
        name = f"mkbrr{executable_suffix}"
        return [
            (code_dir / "bin" / name, None, ""),
            (code_dir / "bin" / "mkbrr" / name, None, ""),
            (code_dir / "bin" / "mkbrr" / folder / name, None, ""),
            (state_dir / "bin" / name, None, ""),
            (state_dir / "bin" / "mkbrr" / name, None, ""),
            (state_dir / "bin" / "mkbrr" / folder / name, state_dir / "bin" / "mkbrr" / folder / "v1.24.0", "1.24.0"),
        ]

    if key in {"dovi_tool_path", "hdr10plus_tool_path"} and system in {"windows", "darwin", "linux"} and machine in {
        "amd64",
        "x86_64",
        "arm64",
        "aarch64",
    }:
        command = _COMMANDS[key]
        version = "2.3.3" if key == "dovi_tool_path" else "1.7.2"
        binary = state_dir / "bin" / command / system / machine / f"{command}{executable_suffix}"
        return [(binary, binary.parent / version, version)]

    return []


def _automatic_message(key: str) -> str:
    messages = {
        "ffmpeg_path": "Upload Assistant will download FFmpeg 9.0.1 automatically before an upload on Windows.",
        "mediainfo_path": "Upload Assistant will download MediaInfo CLI 26.05 automatically before an upload.",
        "dvd_mediainfo_path": "Upload Assistant will download the separate MediaInfo 23.04 build automatically when a DVD is processed.",
        "bdinfo_path": "Upload Assistant will download BDInfo automatically when a Blu-ray disc is processed.",
        "mkbrr_path": "Upload Assistant will download mkbrr automatically when it is required.",
        "dovi_tool_path": "Upload Assistant will download the Dolby Vision tool automatically when a Dolby Vision plot is requested.",
        "hdr10plus_tool_path": "Upload Assistant will download the HDR10+ tool automatically when an HDR10+ plot is requested.",
    }
    return messages[key]


def _is_automatically_managed(key: str) -> bool:
    system, machine = _host()
    if key == "ffmpeg_path":
        return system == "windows" and machine in {"amd64", "x86_64"}
    if key == "mediainfo_path":
        return bool(_managed_paths(key, Path(), Path()))
    if key == "dvd_mediainfo_path":
        # The runtime downloader does not yet normalize the Linux aarch64 alias.
        if system == "linux" and machine == "aarch64":
            return False
        return bool(_managed_paths(key, Path(), Path()))
    if key in {"bdinfo_path", "mkbrr_path", "dovi_tool_path", "hdr10plus_tool_path"}:
        return bool(_managed_paths(key, Path(), Path()))
    return False


def check_external_tools(
    defaults: Mapping[str, Any],
    *,
    state_dir: str | Path,
    code_dir: str | Path,
) -> dict[str, dict[str, str]]:
    """Return availability information without downloading or modifying tools."""

    state_root = Path(state_dir)
    code_root = Path(code_dir)
    statuses: dict[str, dict[str, str]] = {}

    for key in EXTERNAL_TOOL_KEYS:
        configured = _configured_result(key, defaults.get(key, ""))
        if configured is not None:
            statuses[key] = configured
            continue

        if key == "ffmpeg_path":
            managed_environment = os.environ.get("UA_FFMPEG_PATH", "").strip()
            if managed_environment and _is_usable_file(Path(managed_environment)):
                statuses[key] = _available_result(key, managed_environment, "Upload Assistant environment")
                continue

        if key in {"dovi_tool_path", "hdr10plus_tool_path"}:
            command = _COMMANDS[key]
            if detected := shutil.which(command):
                statuses[key] = _available_result(key, detected, "System PATH")
                continue

        managed_ready = False
        for binary, marker, version in _managed_paths(key, state_root, code_root):
            marker_ready = marker is None or marker.is_file()
            if _is_usable_file(binary) and marker_ready:
                marker_version = _version_from_marker(marker) if marker is not None else version
                statuses[key] = _available_result(
                    key,
                    binary,
                    "Managed by Upload Assistant",
                    version=marker_version or version,
                )
                managed_ready = True
                break
        if managed_ready:
            continue

        if key in {"mediainfo_path", "dvd_mediainfo_path", "bdinfo_path"} and _is_automatically_managed(key):
            statuses[key] = _result(
                key,
                state="automatic",
                badge="Automatic",
                tone="accent",
                message=_automatic_message(key),
                source="Managed by Upload Assistant",
            )
            continue

        command = _COMMANDS.get(key)
        if command and (detected := shutil.which(command)):
            statuses[key] = _available_result(key, detected, "System PATH")
            continue

        if _is_automatically_managed(key):
            statuses[key] = _result(
                key,
                state="automatic",
                badge="Automatic",
                tone="accent",
                message=_automatic_message(key),
                source="Managed by Upload Assistant",
            )
            continue

        purpose = _PURPOSES.get(key, "Configure a path or install it on the Upload Assistant host.")
        statuses[key] = _result(
            key,
            state="missing",
            badge="Not found",
            tone="warning",
            message=f"{_LABELS[key]} was not found. {purpose}",
        )

    return statuses
