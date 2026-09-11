"""Select or create policy-compliant base torrents before tracker uploads."""

from __future__ import annotations

import asyncio
import os
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from src.console import logger
from src.meta import Meta
from src.torrent_manifest import TorrentLayout, TorrentManifest
from src.torrent_policy import MIB, PIECE_SIZE_MAX, PIECE_SIZE_MIN, TorrentPolicy
from src.torrentcreate import TorrentCreator

_locks: dict[str, asyncio.Lock] = {}
_locks_guard = threading.Lock()


def _variant_lock(meta: Meta, layout: TorrentLayout, policy: TorrentPolicy) -> asyncio.Lock:
    key = f"{Path(meta.base_dir).resolve()}:{meta.uuid}:{layout}:{policy!r}"
    with _locks_guard:
        return _locks.setdefault(key, asyncio.Lock())


def _content_size(path: str | os.PathLike[str]) -> int:
    source = Path(path)
    if source.is_file():
        return source.stat().st_size
    return sum(item.stat().st_size for item in source.rglob("*") if item.is_file())


async def provision_tracker_torrents(
    meta: Meta,
    config: Mapping[str, Any],
    trackers: Sequence[str],
    tracker_class_map: Mapping[str, Any],
) -> set[str]:
    """Prepare manifest selections and return trackers blocked by constraints."""
    manifest = TorrentManifest(meta.base_dir, meta.uuid)
    blocked: dict[str, str] = {}
    tracker_configs = config.get("TRACKERS", {})
    tracker_configs = tracker_configs if isinstance(tracker_configs, Mapping) else {}

    for raw_tracker in trackers:
        tracker = str(raw_tracker).strip().upper()
        try:
            factory = tracker_class_map.get(tracker)
            if factory is None or getattr(factory, "is_usenet", False):
                continue
            tracker_settings = tracker_configs.get(tracker, {})
            allow_subs = isinstance(tracker_settings, Mapping) and bool(tracker_settings.get("allow_ext_subtitles", False))
            layout: TorrentLayout = "base_subs" if allow_subs and manifest.default_path("base_subs") is not None else "base"
            policy = cast(TorrentPolicy | None, getattr(factory, "torrent_policy", None))
            if manifest.select(tracker, layout, policy) is not None:
                continue
            if meta.nohash:
                blocked[tracker] = "Skipped: no policy-compliant torrent is available and hashing is disabled"
                continue
            if policy is None:
                continue

            async with _variant_lock(meta, layout, policy):
                if manifest.select(tracker, layout, policy) is not None:
                    continue
                if meta.path is None:
                    blocked[tracker] = "Skipped: source path is unavailable for torrent creation"
                    continue
                content_size = await asyncio.to_thread(_content_size, meta.path)
                hash_meta = meta.copy()
                hash_meta.trackers = [tracker]
                default_piece_size = TorrentCreator.calculate_piece_size(
                    content_size,
                    PIECE_SIZE_MIN,
                    PIECE_SIZE_MAX,
                    hash_meta,
                    piece_size=meta.max_piece_size,
                )
                chosen = policy.choose_piece_size(content_size, default_piece_size)
                output = "BASE_SUBS" if layout == "base_subs" else "BASE"
                logger.info(f"{tracker}: [yellow]Creating a policy-compliant {chosen / MIB:g} MiB base torrent.[/yellow]")
                try:
                    cooldown = int(cast(Mapping[str, Any], config.get("DEFAULT", {})).get("rehash_cooldown", 0) or 0)
                except TypeError, ValueError:
                    cooldown = 0
                if cooldown > 0:
                    await asyncio.sleep(cooldown)
                await TorrentCreator.create_torrent(hash_meta, Path(meta.path), output, piece_size=max(1, chosen // MIB))
                if manifest.select(tracker, layout, policy) is None:
                    blocked[tracker] = "Skipped: generated torrent does not satisfy the tracker policy"
        except asyncio.CancelledError:
            raise
        except Exception as error:
            blocked[tracker] = f"Skipped: torrent provisioning failed: {error}"

    for tracker, reason in blocked.items():
        status = meta.tracker_status.setdefault(tracker, {})
        status["upload"] = False
        status["status_message"] = reason
        logger.info(f"[yellow]{tracker}: {status['status_message']}[/yellow]")
    return set(blocked)
