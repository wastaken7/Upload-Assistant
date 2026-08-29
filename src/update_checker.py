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
RELEASES_API_URL = "https://api.github.com/repos/wastaken7/Upload-Assistant/releases?per_page=100"
MAX_CHANGELOG_RELEASES = 100


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


def fetch_release_history(url: str = RELEASES_API_URL) -> list[dict[str, object]] | None:
    """Fetch a WebUI-safe subset of the upstream GitHub release history."""
    try:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "Upload-Assistant-WebUI",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310 - fixed HTTPS URL
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, UnicodeError, ValueError, urllib.error.URLError, json.JSONDecodeError):
        return None

    if not isinstance(payload, list):
        return None

    releases: list[dict[str, object]] = []
    for release in payload:
        if not isinstance(release, dict) or release.get("draft") is True:
            continue
        version = release.get("tag_name")
        if not isinstance(version, str) or not version.strip():
            continue
        release_url = release.get("html_url")
        if not isinstance(release_url, str) or not release_url.startswith(f"{RELEASES_URL}/tag/"):
            release_url = f"{RELEASES_URL}/tag/{version.strip()}"
        title = release.get("name")
        changelog = release.get("body")
        published_at = release.get("published_at")
        releases.append(
            {
                "version": version.strip(),
                "title": title.strip() if isinstance(title, str) and title.strip() else version.strip(),
                "changelog": changelog.strip() if isinstance(changelog, str) else "",
                "release_url": release_url,
                "published_at": published_at if isinstance(published_at, str) else "",
                "prerelease": release.get("prerelease") is True,
            }
        )
        if len(releases) >= MAX_CHANGELOG_RELEASES:
            break
    return releases


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


def _changelog_cache_path(state_dir: Path) -> Path:
    return state_dir / "webui_changelog.json"


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


def _read_changelog_cache(
    state_dir: Path,
    cache_hours: float | None,
) -> tuple[list[dict[str, object]], float] | None:
    try:
        cached: Any = json.loads(_changelog_cache_path(state_dir).read_text(encoding="utf-8"))
        checked_at = cached["checked_at"]
        releases = cached["releases"]
        if not isinstance(checked_at, (int, float)) or not isinstance(releases, list):
            return None
        if cache_hours is not None and time.time() - checked_at >= cache_hours * 3600:
            return None
        safe_releases = [release for release in releases if isinstance(release, dict)]
        return safe_releases[:MAX_CHANGELOG_RELEASES], float(checked_at)
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        return None


def _write_changelog_cache(state_dir: Path, releases: list[dict[str, object]]) -> float:
    checked_at = time.time()
    state_dir.mkdir(parents=True, exist_ok=True)
    cache_path = _changelog_cache_path(state_dir)
    temporary_path = cache_path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps({"checked_at": checked_at, "releases": releases}),
        encoding="utf-8",
    )
    temporary_path.replace(cache_path)
    return checked_at


def _local_release(code_dir: Path) -> dict[str, object] | None:
    version_file = code_dir / "src" / "version.py"
    try:
        content = version_file.read_text(encoding="utf-8")
    except OSError:
        return None
    version = read_local_version(version_file)
    if not version:
        return None
    return {
        "version": version,
        "title": version,
        "changelog": extract_changelog(content, version) or "",
        "release_url": f"{RELEASES_URL}/tag/{version}",
        "published_at": "",
        "prerelease": False,
    }


def get_changelog_history(
    *,
    cache_hours: float = 4,
    force: bool = False,
    code_dir: Path = CODE_DIR,
    state_dir: Path = STATE_DIR,
) -> dict[str, object]:
    """Return cached upstream releases with a bundled current-release fallback."""
    cache_hours = max(0.0, float(cache_hours))
    cached = None if force else _read_changelog_cache(state_dir, cache_hours)
    if cached:
        releases, checked_at = cached
        return {
            "success": True,
            "source": "cache",
            "releases": releases,
            "checked_at": checked_at,
            "stale": False,
        }

    releases = fetch_release_history()
    if releases:
        checked_at = _write_changelog_cache(state_dir, releases)
        return {
            "success": True,
            "source": "github",
            "releases": releases,
            "checked_at": checked_at,
            "stale": False,
        }

    stale_cache = _read_changelog_cache(state_dir, None)
    if stale_cache:
        stale_releases, checked_at = stale_cache
        return {
            "success": True,
            "source": "cache",
            "releases": stale_releases,
            "checked_at": checked_at,
            "stale": True,
            "warning": "GitHub could not be reached. Showing cached release history.",
        }

    local_release = _local_release(code_dir)
    if local_release:
        return {
            "success": True,
            "source": "local",
            "releases": [local_release],
            "checked_at": None,
            "stale": True,
            "warning": "GitHub could not be reached. Showing the bundled release notes.",
        }

    return {
        "success": False,
        "source": "none",
        "releases": [],
        "checked_at": None,
        "stale": True,
        "error": "Unable to load the release history.",
    }


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
