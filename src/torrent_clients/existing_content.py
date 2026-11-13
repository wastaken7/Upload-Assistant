# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Find a client's own copy of a torrent's files so the new torrent can seed from it."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

EXISTING_CONTENT_MODES = ("prefer", "require")
# A torrent in one of these states cannot vouch for its files.
UNUSABLE_STATES = frozenset({"error", "missingFiles", "moving", "unknown", "metaDL"})
# Extra files (NFO, sample, artwork) the client's copy may hold besides ours.
EXTRA_SIZE_RATIO = 0.10
EXTRA_SIZE_FLOOR = 512 * 1024 * 1024
MAX_CANDIDATES = 25


@dataclass(frozen=True)
class ExistingContentMatch:
    """Where the client already holds every file of the torrent being added."""

    torrent_hash: str
    torrent_name: str
    save_path: str
    content_layout: str


def existing_content_mode(client: Mapping[str, Any]) -> str:
    """Return "prefer", "require", or "" (disabled) from a client's `match_existing_content`."""
    raw = client.get("match_existing_content")
    if raw is True:
        return "prefer"
    value = str(raw or "").strip().lower()
    return value if value in EXISTING_CONTENT_MODES else ""


def torrent_file_entries(torrent: Any) -> list[tuple[str, int]]:
    """List a torrent's files as (posix path, size), using its Original layout."""
    return [(PurePosixPath(*file.parts).as_posix(), int(file.size)) for file in torrent.files]


def select_candidates(torrents: Iterable[Mapping[str, Any]], expected_size: int, torrent_name: str) -> list[Mapping[str, Any]]:
    """Pick complete client torrents large enough to hold the content.

    Torrents with the same name come first, so a renamed or busy library cannot
    push the likeliest copy past the candidate limit; then the closest size wins.
    """
    allowance = max(int(expected_size * EXTRA_SIZE_RATIO), EXTRA_SIZE_FLOOR)
    candidates: list[tuple[int, bool, Mapping[str, Any]]] = []
    for info in torrents:
        try:
            size = int(info.get("total_size") or info.get("size") or 0)
            progress = float(info.get("progress") or 0)
        except TypeError, ValueError:
            continue
        if not info.get("hash") or not info.get("save_path") or progress < 1:
            continue
        if str(info.get("state") or "") in UNUSABLE_STATES:
            continue
        extra = size - expected_size
        if 0 <= extra <= allowance:
            candidates.append((extra, str(info.get("name") or "") != torrent_name, info))
    candidates.sort(key=lambda item: (item[1], item[0]))
    return [info for _extra, _other_name, info in candidates[:MAX_CANDIDATES]]


def match_content_layout(expected: list[tuple[str, int]], multi_file: bool, client_files: Iterable[Mapping[str, Any]]) -> tuple[str, str] | None:
    """Place every expected file on a complete client file of the same size.

    Returns (prefix, content_layout): the folder below the client torrent's save
    path that holds the content, and the qBittorrent layout that maps the new
    torrent's files onto it.
    """
    if not expected:
        return None
    complete: dict[str, int] = {}
    for file in client_files:
        name = str(file.get("name") or "").replace("\\", "/").strip("/")
        try:
            if name and float(file.get("progress") or 0) >= 1:
                complete[name] = int(file.get("size", -1))
        except TypeError, ValueError:
            continue

    variants = [("Original", expected)]
    if multi_file:
        # NoSubfolder drops the torrent's root folder, so its files may sit in a folder of another name.
        stripped = [(path.split("/", 1)[1], size) for path, size in expected if "/" in path]
        if len(stripped) == len(expected):
            variants.append(("NoSubfolder", stripped))

    for layout, files in variants:
        anchor_path, anchor_size = files[0]
        prefixes = sorted(
            {
                "" if name == anchor_path else name[: -len(anchor_path) - 1]
                for name, size in complete.items()
                if size == anchor_size and (name == anchor_path or name.endswith(f"/{anchor_path}"))
            },
            key=len,
        )
        for prefix in prefixes:
            if all(complete.get(f"{prefix}/{path}" if prefix else path) == size for path, size in files):
                return prefix, layout
    return None


def join_client_path(save_path: str, prefix: str) -> str:
    """Append a posix relative folder to a client save path, keeping the client's separator."""
    if not prefix:
        return save_path
    separator = "\\" if "\\" in save_path and "/" not in save_path else "/"
    return save_path.rstrip("/\\") + separator + prefix.replace("/", separator)
