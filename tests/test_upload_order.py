# ruff: noqa: S101

import asyncio

from src.uploadorder import run_upload_order


def test_usenet_order_waits_once_then_uploads_trackers_without_bandwidth_checks():
    events: list[str] = []

    async def upload_usenet() -> None:
        events.append("usenet")

    async def upload_torrents(bandwidth_control: bool) -> None:
        events.append(f"torrents:{bandwidth_control}")

    async def wait_for_bandwidth() -> None:
        events.append("bandwidth")

    asyncio.run(
        run_upload_order(
            "usenet",
            upload_usenet,
            upload_torrents,
            wait_for_bandwidth,
            bandwidth_control=True,
            bandwidth_control_after_usenet=False,
            has_usenet_upload=True,
            has_torrent_trackers=True,
        )
    )

    assert events == ["bandwidth", "usenet", "torrents:False"]


def test_tracker_order_keeps_tracker_bandwidth_control_before_usenet_wait():
    events: list[str] = []

    async def upload_usenet() -> None:
        events.append("usenet")

    async def upload_torrents(bandwidth_control: bool) -> None:
        events.append(f"torrents:{bandwidth_control}")

    async def wait_for_bandwidth() -> None:
        events.append("bandwidth")

    asyncio.run(
        run_upload_order(
            "tracker",
            upload_usenet,
            upload_torrents,
            wait_for_bandwidth,
            bandwidth_control=True,
            bandwidth_control_after_usenet=False,
            has_usenet_upload=True,
            has_torrent_trackers=True,
        )
    )

    assert events == ["torrents:True", "bandwidth", "usenet"]


def test_usenet_order_without_usenet_upload_preserves_tracker_bandwidth_setting():
    events: list[str] = []

    async def upload_usenet() -> None:
        events.append("usenet")

    async def upload_torrents(bandwidth_control: bool) -> None:
        events.append(f"torrents:{bandwidth_control}")

    async def wait_for_bandwidth() -> None:
        events.append("bandwidth")

    asyncio.run(
        run_upload_order(
            "usenet",
            upload_usenet,
            upload_torrents,
            wait_for_bandwidth,
            bandwidth_control=True,
            bandwidth_control_after_usenet=False,
            has_usenet_upload=False,
            has_torrent_trackers=True,
        )
    )

    assert events == ["usenet", "torrents:True"]


def test_usenet_order_does_not_check_bandwidth_when_control_is_disabled():
    events: list[str] = []

    async def upload_usenet() -> None:
        events.append("usenet")

    async def upload_torrents(bandwidth_control: bool) -> None:
        events.append(f"torrents:{bandwidth_control}")

    async def wait_for_bandwidth() -> None:
        events.append("bandwidth")

    asyncio.run(
        run_upload_order(
            "usenet",
            upload_usenet,
            upload_torrents,
            wait_for_bandwidth,
            bandwidth_control=False,
            bandwidth_control_after_usenet=False,
            has_usenet_upload=True,
            has_torrent_trackers=True,
        )
    )

    assert events == ["usenet", "torrents:False"]


def test_tracker_order_does_not_check_bandwidth_when_control_is_disabled():
    events: list[str] = []

    async def upload_usenet() -> None:
        events.append("usenet")

    async def upload_torrents(bandwidth_control: bool) -> None:
        events.append(f"torrents:{bandwidth_control}")

    async def wait_for_bandwidth() -> None:
        events.append("bandwidth")

    asyncio.run(
        run_upload_order(
            "tracker",
            upload_usenet,
            upload_torrents,
            wait_for_bandwidth,
            bandwidth_control=False,
            bandwidth_control_after_usenet=False,
            has_usenet_upload=True,
            has_torrent_trackers=True,
        )
    )

    assert events == ["torrents:False", "usenet"]


def test_concurrent_order_forwards_disabled_bandwidth_control():
    events: list[str] = []

    async def upload_usenet() -> None:
        events.append("usenet")

    async def upload_torrents(bandwidth_control: bool) -> None:
        events.append(f"torrents:{bandwidth_control}")

    async def wait_for_bandwidth() -> None:
        events.append("bandwidth")

    asyncio.run(
        run_upload_order(
            "concurrent",
            upload_usenet,
            upload_torrents,
            wait_for_bandwidth,
            bandwidth_control=False,
            bandwidth_control_after_usenet=False,
            has_usenet_upload=True,
            has_torrent_trackers=True,
        )
    )

    assert sorted(events) == ["torrents:False", "usenet"]


def test_usenet_order_can_keep_bandwidth_control_for_tracker_uploads():
    events: list[str] = []

    async def upload_usenet() -> None:
        events.append("usenet")

    async def upload_torrents(bandwidth_control: bool) -> None:
        events.append(f"torrents:{bandwidth_control}")

    async def wait_for_bandwidth() -> None:
        events.append("bandwidth")

    asyncio.run(
        run_upload_order(
            "usenet",
            upload_usenet,
            upload_torrents,
            wait_for_bandwidth,
            bandwidth_control=True,
            bandwidth_control_after_usenet=True,
            has_usenet_upload=True,
            has_torrent_trackers=True,
        )
    )

    assert events == ["bandwidth", "usenet", "torrents:True"]


def test_after_usenet_setting_cannot_bypass_disabled_master_switch():
    events: list[str] = []

    async def upload_usenet() -> None:
        events.append("usenet")

    async def upload_torrents(bandwidth_control: bool) -> None:
        events.append(f"torrents:{bandwidth_control}")

    async def wait_for_bandwidth() -> None:
        events.append("bandwidth")

    asyncio.run(
        run_upload_order(
            "usenet",
            upload_usenet,
            upload_torrents,
            wait_for_bandwidth,
            bandwidth_control=False,
            bandwidth_control_after_usenet=True,
            has_usenet_upload=True,
            has_torrent_trackers=True,
        )
    )

    assert events == ["usenet", "torrents:False"]
