# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import ast
import os
from pathlib import Path, PureWindowsPath
from typing import cast


def coerce_str_list(value: object) -> list[str]:
    """Coerce a configured path value into a list of non-empty strings."""
    if isinstance(value, (list, tuple)):
        values = cast(list[object] | tuple[object, ...], value)
        return [str(item) for item in values if item is not None and str(item)]
    if isinstance(value, str):
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            try:
                parsed = ast.literal_eval(value)
            except SyntaxError, ValueError:
                parsed = None
            if isinstance(parsed, (list, tuple)):
                parsed_values = cast(list[object] | tuple[object, ...], parsed)
                return [str(item) for item in parsed_values if item is not None and str(item)]
        return [value] if value else []
    return [str(value)] if value is not None else []


def is_path_under(path: str | Path, root: str | Path) -> bool:
    """Return whether path is within root using case-insensitive boundaries."""
    return _relative_path_parts(path, root) is not None


def _relative_path_parts(path: str | Path, root: str | Path) -> tuple[str, ...] | None:
    """Return path components below root, or None when root is not a prefix."""
    path_parts = Path(os.path.normpath(str(path))).parts
    root_parts = Path(os.path.normpath(str(root))).parts
    if len(path_parts) < len(root_parts):
        return None
    if not all(
        os.path.normcase(path_part).casefold() == os.path.normcase(root_part).casefold() for path_part, root_part in zip(path_parts[: len(root_parts)], root_parts, strict=True)
    ):
        return None
    return path_parts[len(root_parts) :]


def map_save_path(
    save_path: str | Path,
    local_path: str | Path | None,
    remote_path: str | Path | None,
    *,
    trailing_slash: bool = True,
) -> str:
    """Map a local path to a client path and format it with a trailing slash."""
    mapped_path = str(save_path)
    local_path_str = str(local_path) if local_path is not None else ""
    remote_path_str = str(remote_path) if remote_path is not None else ""

    paths_differ = os.path.normcase(local_path_str) != os.path.normcase(remote_path_str)
    relative_parts = _relative_path_parts(mapped_path, local_path_str) if local_path_str and remote_path_str and paths_differ else None
    if relative_parts is not None:
        mapped_path_obj = Path(remote_path_str)
        if relative_parts:
            mapped_path_obj /= Path(*relative_parts)
        mapped_path = str(mapped_path_obj)

    mapped_path = mapped_path.replace("\\", "/").replace(os.sep, "/")
    if not trailing_slash:
        return mapped_path
    return mapped_path if mapped_path.endswith("/") else f"{mapped_path}/"


def tracker_directory(link_target: str | Path, link_dir_name: str, tracker: str) -> Path:
    """Build a safe tracker link directory and reject unsafe Windows names."""
    directory_name = link_dir_name.strip() or tracker
    windows_path = PureWindowsPath(directory_name)
    windows_device_name = directory_name.split(".", 1)[0].rstrip(" .").casefold()
    reserved_device_names = {"con", "prn", "aux", "nul", *(f"com{index}" for index in range(1, 10)), *(f"lpt{index}" for index in range(1, 10))}
    unsafe_name = (
        not directory_name
        or directory_name in {".", ".."}
        or "/" in directory_name
        or "\\" in directory_name
        or Path(directory_name).is_absolute()
        or windows_path.drive
        or windows_path.anchor
        or windows_device_name in reserved_device_names
    )
    if unsafe_name:
        raise ValueError(f"Invalid tracker link directory name: {directory_name!r}")
    return Path(link_target) / directory_name
