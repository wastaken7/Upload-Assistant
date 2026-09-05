"""Shared, cached update status used by the CLI and WebUI."""

from __future__ import annotations

import ast
import contextlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from src.app_paths import CODE_DIR, STATE_DIR

REMOTE_VERSION_URL = "https://raw.githubusercontent.com/wastaken7/Upload-Assistant/master/src/version.py"
RELEASES_URL = "https://github.com/wastaken7/Upload-Assistant/releases"
RELEASES_API_URL = "https://api.github.com/repos/wastaken7/Upload-Assistant/releases?per_page=100"
REPOSITORY_URL = "https://github.com/wastaken7/Upload-Assistant"
COMPARE_API_URL = "https://api.github.com/repos/wastaken7/Upload-Assistant/compare"
DEVELOPMENT_BRANCH = "development"
MAX_CHANGELOG_RELEASES = 100
MAX_UNRELEASED_COMMITS = 100


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
    if not _is_https_url(url):
        return None, None
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Upload-Assistant-WebUI"})  # noqa: S310 -- validated HTTPS URL
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 -- validated HTTPS URL
            content = response.read().decode("utf-8")
    except OSError, UnicodeError, urllib.error.URLError:
        return None, None
    match = re.search(r'__version__\s*=\s*"([^"]+)"', content)
    return (match.group(1), content) if match else (None, None)


def fetch_release_history(url: str = RELEASES_API_URL) -> list[dict[str, object]] | None:
    """Fetch a WebUI-safe subset of the upstream GitHub release history."""
    if not _is_https_url(url):
        return None
    try:
        request = urllib.request.Request(  # noqa: S310 -- validated HTTPS URL
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "Upload-Assistant-WebUI",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 -- validated HTTPS URL
            payload = json.loads(response.read().decode("utf-8"))
    except OSError, UnicodeError, ValueError, urllib.error.URLError, json.JSONDecodeError:
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


def _unreleased_compare_url(base_version: str, branch: str = DEVELOPMENT_BRANCH) -> str:
    base = urllib.parse.quote(base_version.strip(), safe="")
    head = urllib.parse.quote(branch.strip(), safe="")
    return f"{REPOSITORY_URL}/compare/{base}...{head}"


def _is_https_url(url: str) -> bool:
    """Return whether a caller-provided URL has a usable HTTPS origin."""
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.hostname)


def _unavailable_unreleased_changes(base_version: str) -> dict[str, object]:
    return {
        "available": False,
        "base_version": base_version,
        "branch": DEVELOPMENT_BRANCH,
        "compare_url": _unreleased_compare_url(base_version),
        "ahead_by": None,
        "commits": [],
    }


def fetch_unreleased_changes(
    base_version: str,
    branch: str = DEVELOPMENT_BRANCH,
) -> dict[str, object] | None:
    """Fetch a safe summary of commits after the latest release tag."""
    clean_base = str(base_version or "").strip()
    clean_branch = str(branch or "").strip()
    if not clean_base or not clean_branch:
        return None

    encoded_base = urllib.parse.quote(clean_base, safe="")
    encoded_branch = urllib.parse.quote(clean_branch, safe="")
    api_url = f"{COMPARE_API_URL}/{encoded_base}...{encoded_branch}"
    try:
        request = urllib.request.Request(  # noqa: S310 -- URL is built from a fixed HTTPS origin
            api_url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "Upload-Assistant-WebUI",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 -- fixed HTTPS origin
            payload = json.loads(response.read().decode("utf-8"))
    except OSError, UnicodeError, ValueError, urllib.error.URLError, json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None

    commits: list[dict[str, object]] = []
    raw_commits = payload.get("commits")
    if isinstance(raw_commits, list):
        for commit in raw_commits:
            if not isinstance(commit, dict):
                continue
            sha = commit.get("sha")
            if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{7,40}", sha):
                continue
            commit_details = commit.get("commit")
            if not isinstance(commit_details, dict):
                continue
            message = commit_details.get("message")
            if not isinstance(message, str) or not message.strip():
                continue
            summary = next(
                (line.strip() for line in message.splitlines() if line.strip()),
                "",
            )
            if not summary:
                continue
            commit_url = commit.get("html_url")
            expected_commit_prefix = f"{REPOSITORY_URL}/commit/"
            if not isinstance(commit_url, str) or not commit_url.startswith(expected_commit_prefix):
                commit_url = f"{expected_commit_prefix}{sha}"

            author = ""
            github_author = commit.get("author")
            if isinstance(github_author, dict) and isinstance(github_author.get("login"), str):
                author = github_author["login"].strip()
            author_details = commit_details.get("author")
            if not author and isinstance(author_details, dict) and isinstance(author_details.get("name"), str):
                author = author_details["name"].strip()

            committed_at = ""
            committer_details = commit_details.get("committer")
            if isinstance(committer_details, dict) and isinstance(committer_details.get("date"), str):
                committed_at = committer_details["date"].strip()
            elif isinstance(author_details, dict) and isinstance(author_details.get("date"), str):
                committed_at = author_details["date"].strip()

            commits.append(
                {
                    "sha": sha.lower(),
                    "short_sha": sha[:7].lower(),
                    "summary": summary,
                    "commit_url": commit_url,
                    "author": author,
                    "committed_at": committed_at,
                }
            )

    ahead_by = payload.get("ahead_by")
    if not isinstance(ahead_by, int) or isinstance(ahead_by, bool) or ahead_by < 0:
        ahead_by = len(commits)
    compare_url = payload.get("html_url")
    expected_compare_prefix = f"{REPOSITORY_URL}/compare/"
    if not isinstance(compare_url, str) or not compare_url.startswith(expected_compare_prefix):
        compare_url = _unreleased_compare_url(clean_base, clean_branch)

    return {
        "available": True,
        "base_version": clean_base,
        "branch": clean_branch,
        "compare_url": compare_url,
        "ahead_by": ahead_by,
        "commits": list(reversed(commits[-MAX_UNRELEASED_COMMITS:])),
    }


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
    except OSError, TypeError, ValueError, KeyError, json.JSONDecodeError:
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
) -> tuple[list[dict[str, object]], dict[str, object] | None, float] | None:
    try:
        cached: Any = json.loads(_changelog_cache_path(state_dir).read_text(encoding="utf-8"))
        checked_at = cached["checked_at"]
        releases = cached["releases"]
        unreleased = cached.get("unreleased")
        if not isinstance(checked_at, (int, float)) or not isinstance(releases, list):
            return None
        if unreleased is not None and not isinstance(unreleased, dict):
            unreleased = None
        if cache_hours is not None and time.time() - checked_at >= cache_hours * 3600:
            return None
        safe_releases = [release for release in releases if isinstance(release, dict)]
        return safe_releases[:MAX_CHANGELOG_RELEASES], unreleased, float(checked_at)
    except OSError, TypeError, ValueError, KeyError, json.JSONDecodeError:
        return None


def _write_changelog_cache(
    state_dir: Path,
    releases: list[dict[str, object]],
    unreleased: dict[str, object] | None,
) -> float:
    checked_at = time.time()
    state_dir.mkdir(parents=True, exist_ok=True)
    cache_path = _changelog_cache_path(state_dir)
    temporary_path = cache_path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(
            {
                "checked_at": checked_at,
                "releases": releases,
                "unreleased": unreleased,
            }
        ),
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
        releases, unreleased, checked_at = cached
        if unreleased is None and releases:
            base_version = str(releases[0].get("version") or "").strip()
            unreleased = _unavailable_unreleased_changes(base_version) if base_version else None
        return {
            "success": True,
            "source": "cache",
            "releases": releases,
            "unreleased": unreleased,
            "checked_at": checked_at,
            "stale": False,
        }

    releases = fetch_release_history()
    if releases:
        base_version = str(releases[0].get("version") or "").strip()
        unreleased = fetch_unreleased_changes(base_version) if base_version else None
        if unreleased is None and base_version:
            unreleased = _unavailable_unreleased_changes(base_version)
        checked_at = time.time()
        with contextlib.suppress(OSError):
            checked_at = _write_changelog_cache(state_dir, releases, unreleased)
        return {
            "success": True,
            "source": "github",
            "releases": releases,
            "unreleased": unreleased,
            "checked_at": checked_at,
            "stale": False,
        }

    stale_cache = _read_changelog_cache(state_dir, None)
    if stale_cache:
        stale_releases, unreleased, checked_at = stale_cache
        return {
            "success": True,
            "source": "cache",
            "releases": stale_releases,
            "unreleased": unreleased,
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
            "unreleased": None,
            "checked_at": None,
            "stale": True,
            "warning": "GitHub could not be reached. Showing the bundled release notes.",
        }

    return {
        "success": False,
        "source": "none",
        "releases": [],
        "unreleased": None,
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
    cached = _read_cache(state_dir, cache_hours) if cache_hours and not force else None
    if cached:
        remote_version, remote_content, checked_at = cached
    else:
        remote_version, remote_content = fetch_remote_version()
        checked_at = time.time()
        if remote_version and remote_content:
            with contextlib.suppress(OSError):
                checked_at = _write_cache(state_dir, remote_version, remote_content)

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
