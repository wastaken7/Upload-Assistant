"""Shared, cached update status used by the CLI and WebUI."""

from __future__ import annotations

import ast
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from src.app_paths import CODE_DIR, STATE_DIR

REMOTE_VERSION_URL = "https://raw.githubusercontent.com/wastaken7/Upload-Assistant/master/src/version.py"
RELEASES_URL = "https://github.com/wastaken7/Upload-Assistant/releases"


def parse_version_tuple(value: str) -> tuple[int, ...]:
    """Parse the numeric portion of a dotted version for comparison."""
    parts: list[int] = []
    for part in value.strip().lstrip("vV").split("."):
        if not part.isdigit():
            break
        parts.append(int(part))
    return tuple(parts)


def read_local_version(version_file: Path) -> str | None:
    try:
        content = version_file.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r'__version__\s*=\s*"([^"]+)"', content)
    return match.group(1) if match else None


def fetch_remote_version(url: str = REMOTE_VERSION_URL) -> tuple[str | None, str | None]:
    """Fetch the upstream version module without requiring third-party HTTP packages."""
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Upload-Assistant-WebUI"})
        with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310 - fixed HTTPS URL
            content = response.read().decode("utf-8")
    except (OSError, UnicodeError, urllib.error.URLError):
        return None, None
    match = re.search(r'__version__\s*=\s*"([^"]+)"', content)
    return (match.group(1), content) if match else (None, None)


def extract_changelog(content: str, version: str) -> str | None:
    """Extract the string expression following a matching ``__version__`` assignment."""
    try:
        module = ast.parse(content)
        for index, node in enumerate(module.body[:-1]):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name) or target.id != "__version__":
                continue
            if not isinstance(node.value, ast.Constant) or node.value.value not in (version, version.lstrip("v")):
                continue
            notes_node = module.body[index + 1]
            if isinstance(notes_node, ast.Expr) and isinstance(notes_node.value, ast.Constant) and isinstance(notes_node.value.value, str):
                return re.sub(r"^# ", "", notes_node.value.value.strip(), flags=re.MULTILINE)
    except SyntaxError:
        pass
    return None


def _cache_path(state_dir: Path) -> Path:
    return state_dir / "update_notification.json"


def _read_cache(state_dir: Path, cache_hours: float) -> tuple[str, str, float] | None:
    try:
        cached: Any = json.loads(_cache_path(state_dir).read_text(encoding="utf-8"))
        checked_at = cached["checked_at"]
        remote_version = cached["remote_version"]
        remote_content = cached["remote_content"]
        if not isinstance(checked_at, (int, float)) or not isinstance(remote_version, str) or not isinstance(remote_content, str):
            return None
        if time.time() - checked_at >= cache_hours * 3600:
            return None
        return remote_version, remote_content, float(checked_at)
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        return None


def _write_cache(state_dir: Path, remote_version: str, remote_content: str) -> float:
    checked_at = time.time()
    state_dir.mkdir(parents=True, exist_ok=True)
    cache_path = _cache_path(state_dir)
    temporary_path = cache_path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(
            {
                "checked_at": checked_at,
                "remote_version": remote_version,
                "remote_content": remote_content,
            }
        ),
        encoding="utf-8",
    )
    temporary_path.replace(cache_path)
    return checked_at


def get_update_status(
    *,
    enabled: bool = True,
    cache_hours: float = 4,
    force: bool = False,
    code_dir: Path = CODE_DIR,
    state_dir: Path = STATE_DIR,
) -> dict[str, object]:
    """Return a WebUI-safe update summary while sharing the CLI cache format."""
    local_version = read_local_version(code_dir / "src" / "version.py") or ""
    status: dict[str, object] = {
        "success": True,
        "enabled": bool(enabled),
        "current_version": local_version,
        "latest_version": local_version,
        "update_available": False,
        "changelog": "",
        "release_url": RELEASES_URL,
        "checked_at": None,
    }
    if not enabled or not local_version:
        return status

    cache_hours = max(0.0, float(cache_hours))
    cached = (
        _read_cache(state_dir, cache_hours)
        if cache_hours and not force
        else None
    )
    if cached:
        remote_version, remote_content, checked_at = cached
    else:
        remote_version, remote_content = fetch_remote_version()
        checked_at = time.time()
        if remote_version and remote_content:
            try:
                checked_at = _write_cache(state_dir, remote_version, remote_content)
            except OSError:
                pass

    if not remote_version or not remote_content:
        status["success"] = False
        status["error"] = "Unable to check for updates"
        return status

    status.update(
        {
            "latest_version": remote_version,
            "update_available": parse_version_tuple(remote_version) > parse_version_tuple(local_version),
            "changelog": extract_changelog(remote_content, remote_version) or "",
            "release_url": f"{RELEASES_URL}/tag/{remote_version}",
            "checked_at": checked_at,
        }
    )
    return status
