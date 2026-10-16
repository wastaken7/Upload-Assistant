import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

from src.resource_coordinator import resource_slot


def _bandwidth_slot(enabled: bool) -> contextlib.AbstractAsyncContextManager[Any]:
    """Serialize bandwidth-controlled uploads across concurrent runs, one item at a time."""
    if not enabled:
        return contextlib.nullcontext()
    return resource_slot("qbit-bandwidth", "qBittorrent bandwidth slot")


async def run_upload_order(
    upload_order: str,
    upload_usenet: Callable[[], Awaitable[None]],
    upload_torrents: Callable[[bool], Awaitable[None]],
    wait_for_bandwidth: Callable[[], Awaitable[None]],
    *,
    bandwidth_control: bool,
    bandwidth_control_after_usenet: bool,
    has_usenet_upload: bool,
    has_torrent_trackers: bool,
) -> None:
    """Run upload flows while preserving bandwidth-control boundaries."""
    hold_slot = bandwidth_control and (has_usenet_upload or has_torrent_trackers)
    if upload_order == "usenet":
        async with _bandwidth_slot(hold_slot):
            if bandwidth_control and has_usenet_upload:
                await wait_for_bandwidth()
            await upload_usenet()
            torrent_bandwidth_control = bandwidth_control and (not has_usenet_upload or bandwidth_control_after_usenet)
            await upload_torrents(torrent_bandwidth_control)
    elif upload_order == "tracker":
        async with _bandwidth_slot(hold_slot):
            await upload_torrents(bandwidth_control)
            if bandwidth_control and has_usenet_upload and has_torrent_trackers:
                await wait_for_bandwidth()
            await upload_usenet()
    else:

        async def bandwidth_controlled_torrents() -> None:
            # Concurrent Usenet posting does not wait on qBittorrent bandwidth.
            async with _bandwidth_slot(bandwidth_control and has_torrent_trackers):
                await upload_torrents(bandwidth_control)

        await asyncio.gather(upload_usenet(), bandwidth_controlled_torrents())
