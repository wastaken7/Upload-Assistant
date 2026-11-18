"""Browse roots, user path resolution and upload path validation."""

import hashlib
import json
import os
import re
import secrets
import shlex
import stat
import sys
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Literal, TypedDict

from src.webui_paths import InspectedDirectories, generated_queue_name, validate_argument_paths, validate_content_path
from web_ui import context as context_mod
from web_ui.context import console
from web_ui.flask_compat import safe_join


def _sanitize_relpath(rel: str) -> str:
    """Sanitize a relative path coming from user input.

    Splits the path into components, rejects empty/parent segments and
    validates each component for unsafe/control characters. Returns a
    path using the OS separator. Raises ValueError for unsafe input.
    """
    if rel == "" or rel == ".":
        return rel

    if "\x00" in rel:
        raise ValueError("Invalid path")

    # Split on both forward and backward slashes to support Windows/posix
    parts = re.split(r"[\\/]+", rel)
    clean_parts: list[str] = []
    for p in parts:
        if not p or p == "." or p == "..":
            raise ValueError("Invalid path component")
        # Reject NUL/control characters which are unsafe in file names.
        if re.search(r"[\x00-\x1f]", p):
            raise ValueError("Invalid path component")
        # Reject path-separator characters
        if "/" in p or "\\" in p:
            raise ValueError("Invalid path component")

        clean_parts.append(p)

    return str(Path(*clean_parts))


def _assert_safe_resolved_path(path: str | Path) -> None:
    """Assert that a resolved path is safe and within configured browse roots.

    Raises ValueError if the path is unsafe. This provides an explicit,
    local check at call sites to satisfy static analysis tools.
    """
    path_str = str(path)
    if not path_str or "\x00" in path_str:
        raise ValueError("Invalid path")

    # Ensure absolute and normalized
    abs_path = str(Path(path_str).resolve())
    real_path = os.path.realpath(abs_path)

    # Only queues issued by this running WebUI get an exception to content roots.
    if _is_generated_queue(real_path):
        return

    roots = _get_browse_roots()
    if not roots:
        # If no roots configured, be conservative and disallow.
        raise ValueError("Browsing is not configured")

    allowed = False
    for root in roots:
        root_abs = str(Path(root).resolve())
        root_real = os.path.realpath(root_abs)
        safe_root_prefix = root_real if root_real.endswith(os.sep) else (root_real + os.sep)
        if real_path == root_real or real_path.startswith(safe_root_prefix):
            allowed = True
            break

    if not allowed:
        raise ValueError("Path outside allowed roots")


# Supported description file extensions for WebUI description file browser
SUPPORTED_DESC_EXTS = {".txt", ".nfo", ".md"}

# Regex for splitting filenames on common separators (dots, dashes, underscores, spaces)
_BROWSE_SEARCH_SEP_RE = re.compile(r"[\s.\-_]+")

# Once search results are full, keep walking at most this many directories for
# matching folders that may displace files, instead of walking the whole tree.
_BROWSE_SEARCH_FOLDER_SCAN_DIRS = 500

# Runtime browse roots (set by upload.py when starting web UI)
_runtime_browse_roots: str | None = None
_generated_queues: dict[str, str] = {}
_generated_queues_lock = threading.Lock()


def _is_generated_queue(path: str) -> bool:
    key = os.path.normcase(os.path.realpath(path))
    with _generated_queues_lock:
        expected_hash = _generated_queues.get(key)
    if expected_hash is None:
        return False
    try:
        return secrets.compare_digest(hashlib.sha256(Path(path).read_bytes()).hexdigest(), expected_hash)
    except OSError:
        return False


def _validate_execution_path(path: str, *, inspected_directories: InspectedDirectories | None = None) -> str:
    if inspected_directories is None:
        inspected_directories = set()
    resolved = os.path.realpath(path)
    if _is_generated_queue(resolved):
        # The hash proves these are the lines save_queue fully validated. The
        # upload subprocess validates every item and folder descendant again
        # before processing the first one, so do not walk them a third time.
        for number, line in enumerate(Path(resolved).read_text(encoding="utf-8").splitlines(), 1):
            try:
                if not shlex.split(line):
                    raise ValueError("Empty queue line")
            except ValueError as error:
                raise ValueError(f"Invalid queue line {number}: {error}") from error
        return resolved
    resolved = _resolve_user_path(path, require_exists=True, require_dir=False)
    return validate_content_path(resolved, _get_browse_roots(), inspected_directories=inspected_directories)


def _remove_generated_queue_file(key: str) -> None:
    """Unlink only an issued queue entry directly inside the configured tmp dir."""
    path = Path(key)
    if (
        path.name.startswith("webui_queue_")
        and path.suffix == ".txt"
        and os.path.normcase(os.path.realpath(path.parent)) == os.path.normcase(os.path.realpath(context_mod.STATE_DIR / "tmp"))
    ):
        path.unlink(missing_ok=True)


# Logs of interrupted WebUI queues are kept so resending the selection resumes it.
WEBUI_QUEUE_LOG_RETENTION_SECONDS = 7 * 24 * 60 * 60
_WEBUI_QUEUE_LOG_RE = re.compile(r"webui_(?:[0-9a-f]{16}|queue_\d+_[0-9a-f]{8})_(?:processed_files|queue)\.log")


def _remove_generated_queue_logs(queue_hash: str, lines: Sequence[str]) -> None:
    """Drop a finished queue's logs; keep the processed list while items remain."""
    tmp_dir = context_mod.STATE_DIR / "tmp"
    name = generated_queue_name(queue_hash)
    (tmp_dir / f"{name}_queue.log").unlink(missing_ok=True)
    processed_log = tmp_dir / f"{name}_processed_files.log"
    try:
        processed = json.loads(processed_log.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return
    items = {line.strip() for line in lines if line.strip()}
    if items and isinstance(processed, list) and items <= set(processed):
        processed_log.unlink(missing_ok=True)


def _prune_stale_queue_logs() -> None:
    """Remove WebUI queue logs nobody resumed within the retention period."""
    cutoff = time.time() - WEBUI_QUEUE_LOG_RETENTION_SECONDS
    for path in (context_mod.STATE_DIR / "tmp").glob("webui_*.log"):
        try:
            if _WEBUI_QUEUE_LOG_RE.fullmatch(path.name) and path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        except OSError as error:
            console.print(f"Could not remove stale WebUI queue log: {error}", markup=False)


def _validate_upload_assistant_args(args: Sequence[object], *, inspected_directories: InspectedDirectories | None = None) -> list[str]:
    """Validate upload-assistant arguments before passing them as argv values.

    The WebUI launches the controller without a shell, so shell punctuation is
    valid data. Keep rejecting controls and arguments that are unsafe or
    unsupported for the WebUI.
    """
    safe_args: list[str] = []
    for a in args:
        if not isinstance(a, str):
            raise ValueError("Invalid arg type")
        if a == "--paths-from-stdin":
            raise ValueError("--paths-from-stdin is only available in CLI mode")
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in a):
            raise ValueError("Invalid control character in arg")
        # Disallow arguments that are just parent-directory references
        if a == ".." or a == ".":
            raise ValueError("Invalid arg")
        safe_args.append(a)
    validate_argument_paths(safe_args, _get_browse_roots(), inspected_directories=inspected_directories)
    return safe_args


class BrowseItem(TypedDict, total=False):
    """Serialized representation of an entry returned by the browse API."""

    name: str
    path: str
    type: Literal["folder", "file"]
    children: list[BrowseItem] | None
    subtitle: str  # Optional hint  (eg, when parent path when names collide)
    mtime: float
    size: int


def _get_browse_roots() -> list[str]:
    # Check environment first, then runtime browse roots (set by upload.py)
    global _runtime_browse_roots
    raw = os.environ.get("UA_BROWSE_ROOTS", "").strip() or _runtime_browse_roots or ""
    if not raw:
        # Require explicit configuration; do not default to the filesystem root.
        return []

    roots: list[str] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        root = str(Path(part).resolve())
        roots.append(root)

    return roots


def set_runtime_browse_roots(browse_roots: str) -> None:
    """Set browse roots at runtime (used by upload.py when starting web UI)"""
    global _runtime_browse_roots
    _runtime_browse_roots = browse_roots


def _resolve_user_path(
    user_path: object | None,
    *,
    require_exists: bool = True,
    require_dir: bool = False,
) -> str:
    roots = _get_browse_roots()
    if not roots:
        raise ValueError("Browsing is not configured")

    default_root = roots[0]

    if user_path is None or user_path == "":
        expanded = ""
    else:
        if not isinstance(user_path, str):
            raise ValueError("Path must be a string")
        if len(user_path) > 4096:
            raise ValueError("Invalid path")
        if "\x00" in user_path or "\n" in user_path or "\r" in user_path:
            raise ValueError("Invalid characters in path")

        expanded = os.path.expandvars(Path(user_path).expanduser())

    # Build a normalized path and validate it against allowlisted roots.
    # Use werkzeug.security.safe_join as the primary path sanitizer, with a
    # Windows fallback since safe_join uses posixpath internally.
    # Enforce a realpath+commonpath constraint to prevent symlink escapes.
    matched_root: str | None = None
    candidate_norm: str | None = None

    if expanded and Path(expanded).is_absolute():
        # If a user supplies an absolute path, only allow it if it is under
        # one of the configured browse roots (or their realpath equivalents,
        # since the browse API returns realpath-resolved paths to the frontend).
        for root in roots:
            root_abs = str(Path(root).resolve())
            root_real = os.path.realpath(root_abs)

            # Check against both the configured root and its realpath.
            # This handles the case where the frontend sends back a realpath
            # (e.g., /mnt/storage/torrents) that was returned by a previous
            # browse call, but the configured root is a symlink (e.g., /data/torrents).
            for check_root in (root_abs, root_real):
                try:
                    rel = os.path.relpath(expanded, check_root)
                except ValueError:
                    # Different drive on Windows.
                    continue

                # Sanitize the relative path components to defend against
                # path-injection (e.g. ../../../, absolute segments, nulls).
                # We reject components that resolve to '.' or '..' and use
                # Werkzeug's `secure_filename` to normalize each path segment.
                try:
                    rel = _sanitize_relpath(rel)
                except ValueError:
                    continue

                if rel == os.pardir or rel.startswith(os.pardir + os.sep) or Path(rel).is_absolute():
                    continue

                # Handle the case where the path equals the root exactly.
                # safe_join may return None for '.' in some Werkzeug versions.
                if rel == ".":
                    matched_root = check_root
                    candidate_norm = os.path.normpath(check_root)
                    break

                joined: str | Path | None = safe_join(check_root, rel)

                # Windows fallback: safe_join uses posixpath internally and returns
                # None for Windows backslash paths. Fall back to os.path.join on
                # Windows since we already validated rel above and commonpath check
                # below provides additional symlink-escape protection.
                if sys.platform == "win32" and joined is None:
                    joined = Path(check_root) / rel

                if joined is None:
                    continue

                matched_root = check_root
                candidate_norm = os.path.normpath(joined)
                break

            if matched_root:
                break
    else:
        matched_root = str(Path(default_root).resolve())
        # Handle empty path (initial browse request) - use the root directly.
        # safe_join may return None for empty strings in some Werkzeug versions.
        if not expanded:
            candidate_norm = os.path.normpath(matched_root)
        else:
            # Sanitize the incoming expanded path before joining.
            try:
                sanitized_expanded = _sanitize_relpath(expanded)
            except ValueError as err:
                raise ValueError("Browsing this path is not allowed") from err

            joined: str | Path | None = safe_join(matched_root, sanitized_expanded)

            # Windows fallback: safe_join uses posixpath internally and returns
            # None for Windows backslash paths. Fall back to manual validation
            # and os.path.join. The commonpath check below provides additional security.
            if sys.platform == "win32" and joined is None:
                expanded_norm = os.path.normpath(sanitized_expanded)
                if expanded_norm == os.pardir or expanded_norm.startswith(os.pardir + os.sep) or Path(expanded_norm).is_absolute():
                    raise ValueError("Browsing this path is not allowed")
                joined = Path(matched_root) / expanded_norm

            if joined is not None:
                candidate_norm = os.path.normpath(joined)

    if not matched_root or not candidate_norm:
        raise ValueError("Browsing this path is not allowed")

    candidate_real = os.path.realpath(candidate_norm)
    root_real = os.path.realpath(matched_root)
    try:
        if os.path.commonpath([candidate_real, root_real]) != root_real:
            raise ValueError("Browsing this path is not allowed")
    except ValueError as e:
        # ValueError can happen on Windows if drives differ.
        raise ValueError("Browsing this path is not allowed") from e

    candidate = candidate_real

    # Additional explicit validation before using `candidate` in filesystem
    # operations. This defends against accidental use of unvalidated
    # user-controlled data (helps static analysis tools and provides a
    # clear guard at the call site).
    if "\x00" in candidate:
        raise ValueError("Browsing this path is not allowed")

    # Ensure the resolved candidate path is within the resolved root path.
    safe_root_prefix = root_real if root_real.endswith(os.sep) else (root_real + os.sep)
    if not (candidate == root_real or candidate.startswith(safe_root_prefix)):
        raise ValueError("Browsing this path is not allowed")

    # Extra explicit assertion for static analysis and defense-in-depth:
    # ensure the resolved candidate is within allowed browse roots.
    try:
        _assert_safe_resolved_path(candidate)
    except ValueError as err:
        raise ValueError("Browsing this path is not allowed") from err

    # Use an explicitly-named, normalized `safe_candidate` for filesystem
    # operations so static analyzers can see the sanitized value being used.
    safe_candidate = os.path.realpath(candidate)

    # codeql[py/path-injection]
    if require_exists and not Path(safe_candidate).exists():
        raise ValueError("Path does not exist")

    # codeql[py/path-injection]
    if require_dir and not Path(safe_candidate).is_dir():
        raise ValueError("Not a directory")

    return safe_candidate


def _is_hidden_browse_entry(path: Path | os.DirEntry[str]) -> bool:
    """Hide dotfiles and OS-maintained entries consistently in browse/search."""
    if path.name.startswith(".") or path.name.casefold() in {"$recycle.bin", "system volume information"}:
        return True
    try:
        attributes = getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0)
    except OSError:
        return True
    return bool(attributes & (stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM))


def _resolve_browse_path(user_path: str | None) -> str:
    return _resolve_user_path(user_path, require_exists=True, require_dir=True)
