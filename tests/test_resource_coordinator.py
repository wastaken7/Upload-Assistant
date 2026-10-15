# ruff: noqa: S101, S603

import asyncio
import contextlib
import subprocess
import sys
import threading
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest

import src.resource_coordinator as rc
from src.uploadorder import run_upload_order

REPO_ROOT = Path(__file__).resolve().parent.parent

CHILD_SCRIPT = """
import asyncio, sys, time
from pathlib import Path
import src.resource_coordinator as rc
rc.LOCK_DIR = Path(sys.argv[1])
rc.POLL_SECONDS = 0.05
log, name, release = Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4])

def write(event):
    with log.open("a", encoding="utf-8") as handle:
        handle.write(f"{event} {name}\\n")

async def main():
    async with rc.resource_slot("torrent-hash", "test"):
        write("start")
        while not release.exists():
            await asyncio.sleep(0.02)
        write("end")

asyncio.run(main())
"""


@pytest.fixture
def lock_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "locks"
    monkeypatch.setattr(rc, "LOCK_DIR", directory)
    monkeypatch.setattr(rc, "POLL_SECONDS", 0.05)
    return directory


def _spawn(lock_dir: Path, log: Path, name: str, release: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen([sys.executable, "-c", CHILD_SCRIPT, str(lock_dir), str(log), name, str(release)], cwd=REPO_ROOT)


def _wait_for(condition: Callable[[], bool], timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.02)


def _events(log: Path) -> list[str]:
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _tickets(lock_dir: Path) -> list[Path]:
    return list((lock_dir / "torrent-hash.queue").glob("*.ticket"))


def test_processes_never_overlap_and_oldest_waiter_goes_first(tmp_path: Path, lock_dir: Path) -> None:
    log = tmp_path / "events.log"
    releases = {name: tmp_path / f"release-{name}" for name in ("holder", "older", "newer")}
    holder = _spawn(lock_dir, log, "holder", releases["holder"])
    processes = [holder]
    try:
        _wait_for(lambda: "start holder" in _events(log))
        older = _spawn(lock_dir, log, "older", releases["older"])
        processes.append(older)
        _wait_for(lambda: len(_tickets(lock_dir)) == 1)
        newer = _spawn(lock_dir, log, "newer", releases["newer"])
        processes.append(newer)
        _wait_for(lambda: len(_tickets(lock_dir)) == 2)

        for name in ("holder", "older", "newer"):
            _wait_for(lambda name=name: f"start {name}" in _events(log))
            # A process only keeps a ticket while it waits, never while it holds.
            remaining = {"holder": 2, "older": 1, "newer": 0}[name]
            _wait_for(lambda remaining=remaining: len(_tickets(lock_dir)) == remaining)
            releases[name].touch()
            _wait_for(lambda name=name: f"end {name}" in _events(log))
        for process in processes:
            assert process.wait(timeout=30) == 0
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()

    assert _events(log) == ["start holder", "end holder", "start older", "end older", "start newer", "end newer"]
    assert _tickets(lock_dir) == []


def test_killed_holder_releases_slot(tmp_path: Path, lock_dir: Path) -> None:
    log = tmp_path / "events.log"
    holder = _spawn(lock_dir, log, "holder", tmp_path / "never-released")
    try:
        _wait_for(lambda: "start holder" in _events(log))
        holder.kill()
        holder.wait(timeout=30)

        async def acquire() -> None:
            async with rc.resource_slot("torrent-hash", "test"):
                pass

        asyncio.run(asyncio.wait_for(acquire(), timeout=10))
    finally:
        if holder.poll() is None:
            holder.kill()


def test_stale_ticket_from_dead_process_is_removed(lock_dir: Path) -> None:
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait(timeout=30)
    queue_dir = lock_dir / "torrent-hash.queue"
    queue_dir.mkdir(parents=True)
    stale = queue_dir / f"{0:020d}-{dead.pid:010d}.ticket"
    stale.touch()

    async def acquire() -> None:
        async with rc.resource_slot("torrent-hash", "test"):
            assert not stale.exists()

    asyncio.run(asyncio.wait_for(acquire(), timeout=10))


@pytest.mark.usefixtures("lock_dir")
def test_same_process_holders_share_the_slot() -> None:
    inside = 0
    max_inside = 0

    async def hold() -> None:
        nonlocal inside, max_inside
        async with rc.resource_slot("screenshots", "test"):
            inside += 1
            max_inside = max(max_inside, inside)
            await asyncio.sleep(0.1)
            inside -= 1

    async def main() -> None:
        await asyncio.wait_for(asyncio.gather(hold(), hold(), hold()), timeout=10)

    asyncio.run(main())
    assert max_inside == 3
    assert rc._holds == {}


@pytest.mark.usefixtures("lock_dir")
def test_losing_the_lock_race_to_a_sibling_coroutine_joins_its_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    sibling_lock = object()

    def sibling_wins(_path: Path) -> None:
        # Another coroutine of this run took the OS lock between our checks.
        rc._holds["torrent-hash"] = rc._Hold(sibling_lock, 1)  # type: ignore[arg-type]

    monkeypatch.setattr(rc, "_try_lock", sibling_wins)
    try:
        assert rc._try_acquire("torrent-hash") is True
        assert rc._holds["torrent-hash"].count == 2
    finally:
        rc._holds.clear()


def test_own_ticket_key_never_falls_back_to_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rc, "_process_key", None)
    monkeypatch.setattr(rc, "_create_time_key", lambda _pid: None)
    created, _pid = rc._own_key().split("-")
    assert int(created) > 0


def test_slot_won_after_cancellation_is_given_back(lock_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gate = threading.Event()
    real_try_acquire = rc._try_acquire

    acquired_after_cancel: list[bool] = []

    def slow_try_acquire(name: str) -> bool:
        gate.wait(timeout=10)
        won = real_try_acquire(name)
        acquired_after_cancel.append(won)
        return won

    monkeypatch.setattr(rc, "_try_acquire", slow_try_acquire)

    async def main() -> None:
        async def acquire() -> None:
            async with rc.resource_slot("bdinfo", "test"):
                pass

        task = asyncio.ensure_future(acquire())
        await asyncio.sleep(0.05)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        # The worker thread now wins the slot after its caller was cancelled.
        gate.set()
        for _ in range(200):
            await asyncio.sleep(0.01)
            if acquired_after_cancel and "bdinfo" not in rc._holds:
                break

    asyncio.run(main())
    assert "bdinfo" not in rc._holds
    # The OS lock was released too: another acquirer gets it immediately.
    lock_file = rc._try_lock(lock_dir / "bdinfo.lock")
    assert lock_file is not None
    rc._unlock(lock_file)


def test_unknown_resource_is_rejected() -> None:
    async def acquire() -> None:
        async with rc.resource_slot("unknown", "test"):
            pass

    with pytest.raises(ValueError, match="Unknown resource slot"):
        asyncio.run(acquire())


@pytest.mark.parametrize("bandwidth_control", [True, False])
@pytest.mark.parametrize("order", ["usenet", "tracker", "concurrent"])
def test_upload_order_holds_bandwidth_slot_only_when_enabled(monkeypatch: pytest.MonkeyPatch, order: str, bandwidth_control: bool) -> None:
    events: list[str] = []

    @contextlib.asynccontextmanager
    async def fake_slot(name: str, _label: str) -> AsyncIterator[None]:
        events.append(f"acquire:{name}")
        yield
        events.append(f"release:{name}")

    async def upload_usenet() -> None:
        events.append("usenet")

    async def upload_torrents(enabled: bool) -> None:
        events.append(f"torrents:{enabled}")

    async def wait_for_bandwidth() -> None:
        events.append("bandwidth")

    monkeypatch.setattr("src.uploadorder.resource_slot", fake_slot)
    asyncio.run(
        run_upload_order(
            order,
            upload_usenet,
            upload_torrents,
            wait_for_bandwidth,
            bandwidth_control=bandwidth_control,
            bandwidth_control_after_usenet=True,
            has_usenet_upload=True,
            has_torrent_trackers=True,
        )
    )

    if bandwidth_control:
        assert events.count("acquire:qbit-bandwidth") == 1
        assert events.index("acquire:qbit-bandwidth") < events.index("torrents:True") < events.index("release:qbit-bandwidth")
    else:
        assert "acquire:qbit-bandwidth" not in events
