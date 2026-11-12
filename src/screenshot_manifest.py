"""UUID-addressed local screenshot inventory.

Screenshot filenames are implementation details.  Consumers select a capture
group (main video, disc, or playlist) from this manifest instead of deriving
meaning from a filename.
"""

import json
import threading
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TypeIs

from src.temp_paths import release_temp_dir, screenshots_dir

_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()


def _is_str_dict(val: object) -> TypeIs[dict[str, Any]]:
    return isinstance(val, dict)


def _lock(base_dir: str | Path | None, release_id: str) -> threading.RLock:
    key = str(_path(base_dir, release_id).resolve()).casefold()
    with _locks_guard:
        return _locks.setdefault(key, threading.RLock())


def _path(base_dir: str | Path | None, release_id: str) -> Path:
    return release_temp_dir(base_dir, release_id) / "screenshot_manifest.json"


def _load(base_dir: str | Path, release_id: str) -> dict[str, Any]:
    try:
        value: object = json.loads(_path(base_dir, release_id).read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        value = {}
    return value if _is_str_dict(value) else {}


def _save(base_dir: str | Path, release_id: str, value: dict[str, Any]) -> None:
    output = _path(base_dir, release_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(output)


def register(
    base_dir: str | Path,
    release_id: str,
    paths: Sequence[str | Path],
    group: str,
    *,
    timestamps: dict[str, float] | None = None,
    slot_timestamps: dict[str, float] | None = None,
    pages: dict[str, int] | None = None,
    details: dict[str, dict[str, Any]] | None = None,
) -> list[Path]:
    """Publish capture files under UUID names and return their new paths.

    ``details`` adds extra fields, such as what kind of image a file is, to the
    entries of the given source paths.
    """
    with _lock(base_dir, release_id):
        manifest = _load(base_dir, release_id)
        entries: object = manifest.setdefault("screenshots", {})
        if not _is_str_dict(entries):
            entries = manifest["screenshots"] = {}
        result: list[Path] = []
        for value in paths:
            source = Path(value)
            if not source.is_file():
                continue
            screenshot_id = uuid.uuid4().hex
            suffix = source.suffix.lower() or ".png"
            target = source.with_name(f"{screenshot_id}{suffix}")
            while target.exists():
                screenshot_id = uuid.uuid4().hex
                target = source.with_name(f"{screenshot_id}{suffix}")
            source.replace(target)
            entries[screenshot_id] = {"file": target.name, "group": group}
            if timestamps is not None and str(source) in timestamps:
                entries[screenshot_id]["timestamp"] = timestamps[str(source)]
            if slot_timestamps is not None and str(source) in slot_timestamps:
                entries[screenshot_id]["slot_timestamp"] = slot_timestamps[str(source)]
            if pages is not None and str(source) in pages:
                entries[screenshot_id]["page"] = pages[str(source)]
            if details is not None and str(source) in details:
                extra = {key: value for key, value in details[str(source)].items() if key not in {"file", "group"}}
                entries[screenshot_id].update(extra)
            result.append(target)
        _save(base_dir, release_id, manifest)
        return result


def entries(base_dir: str | Path, release_id: str, group: str | None = None) -> list[tuple[Path, dict[str, Any]]]:
    """Return active screenshots with a copy of their manifest entry, in registration order."""
    directory = screenshots_dir(base_dir, release_id)
    values: object = _load(base_dir, release_id).get("screenshots", {})
    if not _is_str_dict(values):
        return []
    result: list[tuple[Path, dict[str, Any]]] = []
    for screenshot_id, value in values.items():
        if not _is_str_dict(value) or (group is not None and value.get("group") != group):
            continue
        path = directory / str(value.get("file", f"{screenshot_id}.png"))
        if path.is_file():
            result.append((path, dict(value)))
    return result


def files(base_dir: str | Path, release_id: str, group: str | None = None) -> list[Path]:
    """Return active screenshots in registration order, optionally by group."""
    return [path for path, _entry in entries(base_dir, release_id, group)]


def entry_for(base_dir: str | Path, release_id: str, path: Path) -> dict[str, Any] | None:
    """Return a copy of the manifest entry of a local screenshot, if it has one."""
    values: object = _load(base_dir, release_id).get("screenshots", {})
    if _is_str_dict(values):
        for value in values.values():
            if _is_str_dict(value) and value.get("file") == path.name:
                return dict(value)
    return None


def replace_file(base_dir: str | Path, release_id: str, path: Path, new_file: Path, details: dict[str, Any] | None = None) -> Path:
    """Move ``new_file`` over an active screenshot, keeping its manifest entry.

    The file keeps its UUID name; only the extension follows ``new_file``.
    Returns the screenshot's path after the move.
    """
    with _lock(base_dir, release_id):
        manifest = _load(base_dir, release_id)
        values: object = manifest.get("screenshots")
        if not _is_str_dict(values):
            raise FileNotFoundError("Screenshot not found")
        entry = next((value for value in values.values() if _is_str_dict(value) and value.get("file") == path.name), None)
        if entry is None:
            raise FileNotFoundError("Screenshot not found")
        target = path.with_suffix(new_file.suffix.lower() or path.suffix)
        new_file.replace(target)
        if target != path:
            path.unlink(missing_ok=True)
        entry["file"] = target.name
        if details:
            entry.update({key: value for key, value in details.items() if key not in {"file", "group"}})
        _save(base_dir, release_id, manifest)
        return target


def has_flag(base_dir: str | Path, release_id: str, flag: str) -> bool:
    """Return whether a release-wide manifest flag is set."""
    flags: object = _load(base_dir, release_id).get("flags", {})
    return _is_str_dict(flags) and flags.get(flag) is True


def set_flag(base_dir: str | Path, release_id: str, flag: str) -> None:
    """Set a release-wide manifest flag; clearing a group keeps it."""
    with _lock(base_dir, release_id):
        manifest = _load(base_dir, release_id)
        flags: object = manifest.setdefault("flags", {})
        if not _is_str_dict(flags):
            flags = manifest["flags"] = {}
        if flags.get(flag) is not True:
            flags[flag] = True
            _save(base_dir, release_id, manifest)


def discard_file(base_dir: str | Path, release_id: str, path: Path) -> None:
    """Delete an active screenshot and its manifest entry."""
    with _lock(base_dir, release_id):
        path.unlink(missing_ok=True)
        forget_file(base_dir, release_id, path)


def capture_timestamps(base_dir: str | Path, release_id: str, group: str, *, original_slots: bool = False) -> list[float]:
    """Return active capture times, optionally preferring original sampling slots."""
    directory = screenshots_dir(base_dir, release_id)
    entries: object = _load(base_dir, release_id).get("screenshots", {})
    if not _is_str_dict(entries):
        return []
    result: list[float] = []
    for value in entries.values():
        if not _is_str_dict(value) or value.get("group") != group:
            continue
        timestamp = value.get("slot_timestamp", value.get("timestamp")) if original_slots else value.get("timestamp")
        if isinstance(timestamp, (int, float)) and (directory / str(value.get("file", ""))).is_file():
            result.append(float(timestamp))
    return result


def capture_pages(base_dir: str | Path, release_id: str, group: str) -> set[int]:
    """Return the book pages behind the active screenshots of one group."""
    directory = screenshots_dir(base_dir, release_id)
    entries: object = _load(base_dir, release_id).get("screenshots", {})
    if not _is_str_dict(entries):
        return set()
    return {
        value["page"]
        for value in entries.values()
        if _is_str_dict(value) and value.get("group") == group and isinstance(value.get("page"), int) and (directory / str(value.get("file", ""))).is_file()
    }


def set_page(base_dir: str | Path, release_id: str, path: Path, page: int) -> None:
    """Record the book page now shown by an existing screenshot file."""
    with _lock(base_dir, release_id):
        manifest = _load(base_dir, release_id)
        entries: object = manifest.get("screenshots")
        if not _is_str_dict(entries):
            return
        for value in entries.values():
            if _is_str_dict(value) and value.get("file") == path.name:
                value["page"] = page
        _save(base_dir, release_id, manifest)


def clear_group(base_dir: str | Path, release_id: str, group: str) -> None:
    """Delete the active files and manifest entries for one capture group."""
    with _lock(base_dir, release_id):
        manifest = _load(base_dir, release_id)
        entries: object = manifest.get("screenshots")
        if not _is_str_dict(entries):
            return
        directory = screenshots_dir(base_dir, release_id)
        for screenshot_id, value in list(entries.items()):
            if not _is_str_dict(value) or value.get("group") != group:
                continue
            path = directory / str(value.get("file", f"{screenshot_id}.png"))
            path.unlink(missing_ok=True)
            entries.pop(screenshot_id)
        _save(base_dir, release_id, manifest)


def group_for(base_dir: str | Path, release_id: str, path: Path) -> str:
    """Return the logical capture group for a local screenshot."""
    entries: object = _load(base_dir, release_id).get("screenshots", {})
    if _is_str_dict(entries):
        for value in entries.values():
            if _is_str_dict(value) and value.get("file") == path.name:
                group = value.get("group")
                if isinstance(group, str) and group:
                    return group
    return "main"


def forget_file(base_dir: str | Path, release_id: str, path: Path) -> None:
    """Remove a transient capture entry after it has been atomically moved."""
    with _lock(base_dir, release_id):
        manifest = _load(base_dir, release_id)
        entries: object = manifest.get("screenshots")
        if not _is_str_dict(entries):
            return
        for screenshot_id, value in list(entries.items()):
            if _is_str_dict(value) and value.get("file") == path.name:
                entries.pop(screenshot_id)
        _save(base_dir, release_id, manifest)
