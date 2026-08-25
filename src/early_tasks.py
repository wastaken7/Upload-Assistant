"""Background artifact preparation shared by prep and upload stages."""

import asyncio
import os
import time
from collections.abc import Awaitable, Mapping
from pathlib import Path
from typing import Any, cast

from src.clients import Clients
from src.console import CliProgressGate, logger, suppress_cli_progress
from src.meta import Meta
from src.torrentcreate import TorrentCreator
from src.trackersetup import tracker_class_map
from src.webui_progress import has_progress_callback

_early_artifact_tasks: dict[str, tuple[asyncio.Task[None], asyncio.Task[None]]] = {}
_early_progress_gates: dict[str, CliProgressGate] = {}


async def _run_early_artifact_task(task: Awaitable[None], gate: CliProgressGate) -> None:
    """Run preparatory work without rendering CLI progress bars."""
    with suppress_cli_progress(gate):
        await task


def start_early_artifact_tasks(meta: Meta, client: Clients, config: Mapping[str, Any]) -> tuple[asyncio.Task[None], asyncio.Task[None]]:
    """Start, and retain outside ``Meta``, the local-artifact preparation tasks."""
    release_id = str(meta.uuid)
    tasks = _early_artifact_tasks.get(release_id)
    if tasks is None:
        gate = CliProgressGate()
        _early_progress_gates[release_id] = gate
        tasks = (
            asyncio.create_task(_run_early_artifact_task(create_base_torrents_early(meta, client), gate)),
            asyncio.create_task(_run_early_artifact_task(prepare_usenet_archive_early(meta, config), gate)),
        )
        _early_artifact_tasks[release_id] = tasks
    return tasks


def get_early_artifact_tasks(release_id: str) -> tuple[asyncio.Task[None], asyncio.Task[None]] | None:
    """Return the retained tasks for a release, if prep already started them."""
    return _early_artifact_tasks.get(str(release_id))


def release_early_artifact_progress(release_id: str) -> None:
    """Show any in-progress background artifact work after prompts finish."""
    if has_progress_callback() or os.environ.get("UA_WEBUI_ACTIVE") == "1":
        return
    gate = _early_progress_gates.get(str(release_id))
    if gate is not None:
        gate.release()


async def cancel_and_drain_early_artifact_tasks(release_id: str) -> None:
    """Cancel unfinished preparation tasks and wait for both before forgetting them."""
    tasks = _early_artifact_tasks.pop(str(release_id), None)
    _early_progress_gates.pop(str(release_id), None)
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
    task_started = time.perf_counter()
    if meta.nohash or meta.rehash or meta.force_recheck or is_usenet_only(meta):
        logger.debug("[cyan]Skipping early torrent creation due to hashing or tracker settings.[/cyan]")
        return

    torrent_path = Path(meta.base_dir) / "tmp" / meta.uuid / "BASE.torrent"
    subs_torrent_path = Path(meta.base_dir) / "tmp" / meta.uuid / "BASE_SUBS.torrent"
    if torrent_path.exists():
        logger.debug(f"[cyan]Skipping early torrent creation; BASE already exists at {torrent_path}[/cyan]")
        return

    try:
        reuse_torrent = meta.reuse_torrent_path
        if not reuse_torrent or not Path(reuse_torrent).exists():
            logger.debug("[cyan]Early torrent creation has no cached reusable torrent; searching client.[/cyan]")
            search_started = time.perf_counter()
            reuse_torrent = await client.find_existing_torrent(meta)
            logger.debug(f"[cyan]Early client torrent search completed in {time.perf_counter() - search_started:.2f}s[/cyan]")
        if reuse_torrent and Path(reuse_torrent).exists():
            meta.reuse_torrent_path = reuse_torrent
            logger.debug("[cyan]Creating torrent from the client copy while metadata and screenshots are processed.[/cyan]")
            base_creation_started = time.perf_counter()
            created_path = await TorrentCreator.create_base_from_existing_torrent(reuse_torrent, meta.base_dir, meta.uuid)
            logger.debug(f"[cyan]Early base torrent creation completed in {time.perf_counter() - base_creation_started:.2f}s: {created_path or 'no file created'}[/cyan]")
        else:
            logger.debug("[cyan]No reusable client torrent found; creating BASE torrent while metadata and screenshots are processed.[/cyan]")
            await TorrentCreator.create_torrent(meta, Path(cast(str, meta.path)), "BASE")
        if meta.subtitle_files and not subs_torrent_path.exists():
            await TorrentCreator.create_torrent(meta, Path(cast(str, meta.path)), "BASE_SUBS")
        logger.debug(f"[cyan]Early torrent task completed in {time.perf_counter() - task_started:.2f}s[/cyan]")
    except asyncio.CancelledError:
        raise
    except Exception as error:
        logger.warning(f"[yellow]Early torrent creation failed; upload stage will retry: {error}[/yellow]")


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

        logger.debug("[cyan]Preparing Usenet archive and PAR2 files while metadata and screenshots are processed.[/cyan]")
        prepared_path = await prepare_and_upload_usenet(meta, dict(config), prepare_only=True)
        if not prepared_path:
            logger.warning("[yellow]Early Usenet preparation did not complete; posting stage will retry.[/yellow]")
    except asyncio.CancelledError:
        raise
    except Exception as error:
        logger.warning(f"[yellow]Early Usenet preparation failed; posting stage will retry: {error}[/yellow]")
