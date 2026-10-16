# ruff: noqa: S101

import asyncio
from typing import Any

import pytest

from src import qbitwait, webui_progress
from src.qbitwait import Wait


class FakeClient:
    def __init__(self, speeds: list[int]) -> None:
        self.speeds = speeds

    def transfer_info(self) -> dict[str, int]:
        return {"up_info_speed": self.speeds.pop(0)}


def make_waiter(speeds: list[int]) -> Wait:
    waiter = Wait.__new__(Wait)
    waiter.proxy_url = ""
    waiter.qbt_client = FakeClient(speeds)
    return waiter


def test_bandwidth_wait_publishes_webui_meter(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict[str, Any]] = []
    printed: list[str] = []

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(qbitwait.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(qbitwait.console, "print", lambda message, **_kwargs: printed.append(str(message)))
    webui_progress.set_progress_callback(lambda event: events.append(dict(event)))
    try:
        waiter = make_waiter([200 * 1024, 50 * 1024, 50 * 1024])
        assert asyncio.run(waiter.wait_for_bandwidth(100, 10)) is True
    finally:
        webui_progress.clear_progress_callback()

    meter_events = [event for event in events if event.get("id") == "qbit-bandwidth"]
    assert [event["status"] for event in meter_events] == ["running", "running", "completed"]
    assert all(event["unit"] == "kbps" and event["total"] == 100 for event in meter_events)
    assert meter_events[0]["current"] == 200
    # Only the final summary reaches the console; intermediate samples go to the meter.
    assert len(printed) == 1
