"""Background artifact preparation shared by prep and upload stages."""

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from src.clients import Clients
from src.console import logger
from src.meta import Meta
from src.torrentcreate import TorrentCreator
from src.trackersetup import tracker_class_map

_early_artifact_tasks: dict[str, tuple[asyncio.Task[None], asyncio.Task[None]]] = {}


def start_early_artifact_tasks(meta: Meta, client: Clients, config: Mapping[str, Any]) -> tuple[asyncio.Task[None], asyncio.Task[None]]:
    """Start, and retain outside ``Meta``, the local-artifact preparation tasks."""
    release_id = str(meta.uuid)
    tasks = _early_artifact_tasks.get(release_id)
    if tasks is None:
        tasks = (
            asyncio.create_task(create_base_torrents_early(meta, client)),
            asyncio.create_task(prepare_usenet_archive_early(meta, config)),
        )
        _early_artifact_tasks[release_id] = tasks
    return tasks


def get_early_artifact_tasks(release_id: str) -> tuple[asyncio.Task[None], asyncio.Task[None]] | None:
    """Return the retained tasks for a release, if prep already started them."""
    return _early_artifact_tasks.get(str(release_id))


async def cancel_and_drain_early_artifact_tasks(release_id: str) -> None:
    """Cancel unfinished preparation tasks and wait for both before forgetting them."""
    tasks = _early_artifact_tasks.pop(str(release_id), None)
    if tasks is None:
        return
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def restart_early_artifact_tasks(meta: Meta, client: Clients, config: Mapping[str, Any]) -> tuple[asyncio.Task[None], asyncio.Task[None]]:
    """Replace stale tasks after metadata edits with tasks based on current metadata."""
    await cancel_and_drain_early_artifact_tasks(str(meta.uuid))
    return start_early_artifact_tasks(meta, client, config)


def is_usenet_only(meta: Meta) -> bool:
    raw_trackers = meta.trackers
    trackers = raw_trackers.split(",") if isinstance(raw_trackers, str) else raw_trackers
    normalized = [str(tracker).strip().upper() for tracker in trackers if str(tracker).strip()]
    return bool(normalized) and all(tracker in ("USENET", "MANUAL") or getattr(tracker_class_map.get(tracker), "is_usenet", False) for tracker in normalized)


async def create_base_torrents_early(meta: Meta, client: Clients) -> None:
    """Reuse or hash BASE torrents while metadata and screenshots are processed."""
    if meta.nohash or meta.rehash or meta.force_recheck or is_usenet_only(meta):
        return

    torrent_path = Path(meta.base_dir) / "tmp" / meta.uuid / "BASE.torrent"
    subs_torrent_path = Path(meta.base_dir) / "tmp" / meta.uuid / "BASE_SUBS.torrent"
    if torrent_path.exists():
        return

    try:
        reuse_torrent = meta.reuse_torrent_path
        if not reuse_torrent or not Path(reuse_torrent).exists():
            reuse_torrent = await client.find_existing_torrent(meta)
        if reuse_torrent and Path(reuse_torrent).exists():
            meta.reuse_torrent_path = reuse_torrent
            logger.info("[cyan]Creating BASE torrent from the client copy while metadata and screenshots are processed.[/cyan]")
            await TorrentCreator.create_base_from_existing_torrent(reuse_torrent, meta.base_dir, meta.uuid)
        else:
            logger.info("[cyan]No reusable client torrent found; creating BASE torrent while metadata and screenshots are processed.[/cyan]")
            await TorrentCreator.create_torrent(meta, Path(cast(str, meta.path)), "BASE")
        if meta.subtitle_files and not subs_torrent_path.exists():
            await TorrentCreator.create_torrent(meta, Path(cast(str, meta.path)), "BASE_SUBS")
    except asyncio.CancelledError:
        raise
    except Exception as error:
        logger.warning(f"[yellow]Early BASE torrent creation failed; upload stage will retry: {error}[/yellow]")


def needs_usenet_archive(meta: Meta) -> bool:
    raw_trackers = meta.trackers
    trackers = raw_trackers.split(",") if isinstance(raw_trackers, str) else raw_trackers
    return bool(meta.usenet) or any(
        str(tracker).strip().upper() == "USENET" or getattr(tracker_class_map.get(str(tracker).strip().upper()), "is_usenet", False)
        for tracker in trackers
        if str(tracker).strip()
    )


async def prepare_usenet_archive_early(meta: Meta, config: Mapping[str, Any]) -> None:
    """Create archive/PAR2 files before duplicate confirmation, never post them."""
    usenet_cfg = config.get("USENET", {})
    if not needs_usenet_archive(meta) or not isinstance(usenet_cfg, Mapping) or usenet_cfg.get("skip_archive", False):
        return
    try:
        from src.usenetcreate import prepare_and_upload_usenet

        logger.info("[cyan]Preparing Usenet archive and PAR2 files while metadata and screenshots are processed.[/cyan]")
        prepared_path = await prepare_and_upload_usenet(meta, dict(config), prepare_only=True)
        if not prepared_path:
            logger.warning("[yellow]Early Usenet preparation did not complete; posting stage will retry.[/yellow]")
    except asyncio.CancelledError:
        raise
    except Exception as error:
        logger.warning(f"[yellow]Early Usenet preparation failed; posting stage will retry: {error}[/yellow]")
