import asyncio
from collections.abc import Awaitable, Callable


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
    if upload_order == "usenet":
        if bandwidth_control and has_usenet_upload:
            await wait_for_bandwidth()
        await upload_usenet()
        torrent_bandwidth_control = bandwidth_control and (not has_usenet_upload or bandwidth_control_after_usenet)
        await upload_torrents(torrent_bandwidth_control)
    elif upload_order == "tracker":
        await upload_torrents(bandwidth_control)
        if bandwidth_control and has_usenet_upload and has_torrent_trackers:
            await wait_for_bandwidth()
        await upload_usenet()
    else:
        await asyncio.gather(upload_usenet(), upload_torrents(bandwidth_control))
