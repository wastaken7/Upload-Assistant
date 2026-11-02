"""Persistent, execution-scoped description drafts for CLI and WebUI review.

The draft file is shared by two processes: the upload run that seeds, reads and
discards it, and the WebUI server that saves panel edits. Every write goes through
``review_lock`` (a file lock next to the draft) and carries the version the writer
last saw, so a save that lands after a concurrent change is refused instead of
silently resurrecting or overwriting text.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_REVIEW_FILE = "description_review.json"
_LOCK_FILE = "description_review.lock"


class ReviewConflictError(Exception):
    """The draft changed since the caller last read it; ``current_version`` is what is on disk now."""

    def __init__(self, current_version: int) -> None:
        super().__init__(f"description draft is at version {current_version}")
        self.current_version = current_version


def review_path(temp_dir: Path) -> Path:
    return temp_dir / _REVIEW_FILE


def _lock_path(temp_dir: Path) -> Path:
    return temp_dir / _LOCK_FILE


@contextmanager
def review_lock(temp_dir: Path, timeout: float = 10.0) -> Iterator[None]:
    """Serialize draft writers across threads and processes for one execution."""
    temp_dir.mkdir(parents=True, exist_ok=True)
    lock_file = _lock_path(temp_dir).open("a+b")
    started = time.monotonic()
    try:
        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if time.monotonic() - started >= timeout:
                        raise TimeoutError("Timed out waiting for the description draft lock") from exc
                    time.sleep(0.05)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            while True:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError as exc:
                    if time.monotonic() - started >= timeout:
                        raise TimeoutError("Timed out waiting for the description draft lock") from exc
                    time.sleep(0.05)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    finally:
        lock_file.close()


def load_review(temp_dir: Path) -> dict[str, Any]:
    try:
        value = json.loads(review_path(temp_dir).read_text(encoding="utf-8"))
    except OSError, ValueError, TypeError:
        return {}
    return value if isinstance(value, dict) else {}


def review_version(review: dict[str, Any]) -> int:
    try:
        return int(review.get("version", 0) or 0)
    except TypeError, ValueError:
        return 0


def _write_review(temp_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path = review_path(temp_dir)
    temporary = path.with_suffix(f".tmp.{os.getpid()}")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return payload


def _check_version(temp_dir: Path, expected_version: int | None) -> int:
    current_version = review_version(load_review(temp_dir))
    if expected_version is not None and expected_version != current_version:
        raise ReviewConflictError(current_version)
    return current_version


def save_review(temp_dir: Path, content: str, version: int | None = None, *, expected_version: int | None = None) -> dict[str, Any]:
    """Atomically persist a user draft without relying on a browser path.

    With ``expected_version`` the write is a compare-and-swap: it only happens when the
    draft on disk is still at that version, otherwise ``ReviewConflictError`` is raised. The
    new version is ``version`` when given, else the current version plus one.
    """
    with review_lock(temp_dir):
        current_version = _check_version(temp_dir, expected_version)
        payload = {"content": content, "version": current_version + 1 if version is None else version}
        return _write_review(temp_dir, payload)


def seed_review(temp_dir: Path, content: str) -> dict[str, Any] | None:
    """Store the generated description as the draft unless the user already has one.

    Returns the written payload, or ``None`` when an existing draft (or a discard) was kept.
    """
    with review_lock(temp_dir):
        review = load_review(temp_dir)
        if "content" in review:
            return None
        return _write_review(temp_dir, {"content": content, "version": review_version(review) + 1})


def discard_review(temp_dir: Path, *, expected_version: int | None = None) -> dict[str, Any]:
    """Drop the draft so nothing is applied at upload time, without resetting the version.

    A tombstone (``content`` ``None``) is written instead of deleting the file, so a panel
    save that was in flight when the user discarded fails its version check rather than
    bringing the text back.
    """
    with review_lock(temp_dir):
        current_version = _check_version(temp_dir, expected_version)
        return _write_review(temp_dir, {"content": None, "version": current_version + 1})


def source_items(meta: dict[str, Any]) -> list[dict[str, str]]:
    """Return inspectable read-only inputs used to build the base description."""
    items: list[dict[str, str]] = []
    for key, label in (
        ("description", "Tracker description"),
        ("description_link_content", "Description link"),
        ("description_file_content", "Description file"),
        ("description_template_content", "Template"),
        ("description_nfo_content", "NFO"),
    ):
        content = meta.get(key)
        if isinstance(content, str) and content.strip():
            items.append({"key": key, "label": label, "content": content})
    return items


def draft(meta: dict[str, Any], temp_dir: Path) -> tuple[str, int]:
    review = load_review(temp_dir)
    version = review_version(review)
    content = review.get("content")
    if isinstance(content, str):
        return content, version
    override = meta.get("description_override")
    if isinstance(override, str) and override:
        return override, version
    items = source_items(meta)
    return (items[0]["content"] if items else ""), version


def apply_saved_draft(meta: Any) -> None:
    """Synchronize a saved WebUI draft into the live Meta object at use time."""
    temp_dir = Path(meta.base_dir) / "tmp" / meta.uuid
    review = load_review(temp_dir)
    content = review.get("content")
    if isinstance(content, str):
        meta.description_override = content
        # Several tracker adapters use ``meta.description`` directly. Keep both
        # views synchronized so a WebUI edit
        # is honored by every tracker-specific description builder.
        meta.description = content
        meta.saved_description = bool(content)


def get_base_description(meta: Any) -> str:
    """Return the one authoritative base description for an upload."""
    apply_saved_draft(meta)
    description = getattr(meta, "description", "") or ""
    return description if isinstance(description, str) else str(description)
