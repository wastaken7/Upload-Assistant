"""UUID-addressed local screenshot inventory.

Screenshot filenames are implementation details.  Consumers select a capture
group (main video, disc, or playlist) from this manifest instead of deriving
meaning from a filename.
"""

import json
import threading
import uuid
from pathlib import Path
from typing import Any

from src.temp_paths import screenshots_dir

_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()


def _lock(base_dir: str | Path, release_id: str) -> threading.RLock:
    key = str(_path(base_dir, release_id).resolve()).casefold()
    with _locks_guard:
        return _locks.setdefault(key, threading.RLock())


def _path(base_dir: str | Path, release_id: str) -> Path:
    return Path(base_dir) / "tmp" / release_id / "screenshot_manifest.json"


def _load(base_dir: str | Path, release_id: str) -> dict[str, Any]:
    try:
        value = json.loads(_path(base_dir, release_id).read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        value = {}
    return value if isinstance(value, dict) else {}


def _save(base_dir: str | Path, release_id: str, value: dict[str, Any]) -> None:
    output = _path(base_dir, release_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(output)


def register(base_dir: str | Path, release_id: str, paths: list[str | Path], group: str) -> list[Path]:
    """Publish capture files under UUID names and return their new paths."""
    with _lock(base_dir, release_id):
        manifest = _load(base_dir, release_id)
        entries = manifest.setdefault("screenshots", {})
        if not isinstance(entries, dict):
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
            result.append(target)
        _save(base_dir, release_id, manifest)
        return result


def files(base_dir: str | Path, release_id: str, group: str | None = None) -> list[Path]:
    """Return active UUID screenshots, optionally limited to a capture group."""
    directory = screenshots_dir(base_dir, release_id)
    entries = _load(base_dir, release_id).get("screenshots", {})
    if not isinstance(entries, dict):
        return []
    result = []
    for screenshot_id, value in entries.items():
        if not isinstance(value, dict) or (group is not None and value.get("group") != group):
            continue
        path = directory / str(value.get("file", f"{screenshot_id}.png"))
        if path.is_file():
            result.append(path)
    return sorted(result, key=lambda path: path.name)


def clear_group(base_dir: str | Path, release_id: str, group: str) -> None:
    """Delete the active files and manifest entries for one capture group."""
    with _lock(base_dir, release_id):
        manifest = _load(base_dir, release_id)
        entries = manifest.get("screenshots")
        if not isinstance(entries, dict):
            return
        directory = screenshots_dir(base_dir, release_id)
        for screenshot_id, value in list(entries.items()):
            if not isinstance(value, dict) or value.get("group") != group:
                continue
            path = directory / str(value.get("file", f"{screenshot_id}.png"))
            path.unlink(missing_ok=True)
            entries.pop(screenshot_id)
        _save(base_dir, release_id, manifest)


def group_for(base_dir: str | Path, release_id: str, path: Path) -> str:
    """Return the logical capture group for a local screenshot."""
    entries = _load(base_dir, release_id).get("screenshots", {})
    if isinstance(entries, dict):
        for value in entries.values():
            if isinstance(value, dict) and value.get("file") == path.name:
                group = value.get("group")
                if isinstance(group, str) and group:
                    return group
    return "main"


def forget_file(base_dir: str | Path, release_id: str, path: Path) -> None:
    """Remove a transient capture entry after it has been atomically moved."""
    with _lock(base_dir, release_id):
        manifest = _load(base_dir, release_id)
        entries = manifest.get("screenshots")
        if not isinstance(entries, dict):
            return
        for screenshot_id, value in list(entries.items()):
            if isinstance(value, dict) and value.get("file") == path.name:
                entries.pop(screenshot_id)
        _save(base_dir, release_id, manifest)
