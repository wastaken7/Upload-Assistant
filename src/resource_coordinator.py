# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Cross-process slots for heavy work shared by concurrent Upload Assistant runs.

Each WebUI tab (and each CLI invocation) is a separate ``upload.py`` process, so
in-process asyncio primitives cannot keep two runs from hashing torrents, posting
to Usenet or waiting on qBittorrent bandwidth at the same time.

A slot is an OS file lock plus a ticket queue. Waiting processes write a ticket
named after their start time, and only the oldest live run may try the lock, so
the run that started first goes first. The OS releases the lock when a process
dies, which keeps a killed tab from leaving a slot held.

Within one process a slot is shared: concurrent coroutines of the same run hold
it together, so behaviour inside a single upload is unchanged.

Deadlock rule: leaf slots (everything except ``qbit-bandwidth``) must only wrap
the heavy subprocess itself. They never acquire another slot while held and are
never held across interactive prompts. ``qbit-bandwidth`` is the only outer slot.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import os
import threading
import time
from collections.abc import AsyncGenerator, Awaitable, Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, ParamSpec, TypeVar

import psutil

from src.app_paths import TMP_DIR
from src.console import logger
from src.webui_progress import complete_progress, publish_progress

RESOURCES = frozenset({"torrent-hash", "usenet-prep", "usenet-post", "screenshots", "bdinfo", "qbit-bandwidth"})
POLL_SECONDS = 1.0

P = ParamSpec("P")
R = TypeVar("R")

# Tests point this at a temporary directory.
LOCK_DIR: Path = TMP_DIR / "locks"


@dataclass
class _Hold:
    lock_file: BinaryIO
    count: int = 0


_state_lock = threading.Lock()
# Separate from _state_lock, which is held while _remove_ticket calls _own_key.
_process_key_lock = threading.Lock()
_holds: dict[str, _Hold] = {}
_waiters: dict[str, int] = {}
_process_key: str | None = None


def _create_time_key(pid: int) -> str | None:
    try:
        return f"{round(psutil.Process(pid).create_time() * 1_000_000):020d}"
    except psutil.NoSuchProcess:
        return None


def _own_key() -> str:
    global _process_key
    # Worker threads may race here; a fallback key must be computed only once.
    with _process_key_lock:
        if _process_key is None:
            pid = os.getpid()
            try:
                created = _create_time_key(pid)
            except psutil.AccessDenied:
                # Some sandboxes (e.g. Android/Termux) deny reading even our own start time.
                created = None
            # A zero key would make other processes treat this ticket as stale.
            created = created or f"{round(time.time() * 1_000_000):020d}"
            _process_key = f"{created}-{pid:010d}"
        return _process_key


def _queue_dir(name: str) -> Path:
    return LOCK_DIR / f"{name}.queue"


def _ticket_is_live(ticket: Path) -> bool:
    try:
        created, pid_text = ticket.stem.split("-", 1)
        pid = int(pid_text)
        int(created)
    except ValueError:
        return False
    try:
        current = _create_time_key(pid)
        # Tolerate float jitter in psutil's start time; PID reuse differs by far more.
        return current is not None and abs(int(current) - int(created)) <= 10_000
    except psutil.AccessDenied:
        # Another user's live process; never treat it as stale.
        return True


def _first_live_ticket(name: str) -> str | None:
    queue_dir = _queue_dir(name)
    try:
        tickets = sorted(queue_dir.glob("*.ticket"))
    except OSError:
        return None
    for ticket in tickets:
        if ticket.stem == _own_key() or _ticket_is_live(ticket):
            return ticket.stem
        with contextlib.suppress(OSError):
            ticket.unlink()
    return None


def _ensure_ticket(name: str) -> None:
    ticket = _queue_dir(name) / f"{_own_key()}.ticket"
    if not ticket.exists():
        ticket.parent.mkdir(parents=True, exist_ok=True)
        ticket.touch()


def _remove_ticket(name: str) -> None:
    with contextlib.suppress(OSError):
        (_queue_dir(name) / f"{_own_key()}.ticket").unlink()


def _try_lock(lock_path: Path) -> BinaryIO | None:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = lock_path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock_file.close()
        return None
    return lock_file


def _unlock(lock_file: BinaryIO) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    finally:
        lock_file.close()


def _join_existing_hold(name: str) -> bool:
    with _state_lock:
        hold = _holds.get(name)
        if hold is None:
            return False
        hold.count += 1
        return True


def _try_acquire(name: str) -> bool:
    if _join_existing_hold(name):
        return True
    _ensure_ticket(name)
    if _first_live_ticket(name) != _own_key():
        return False
    lock_file = _try_lock(LOCK_DIR / f"{name}.lock")
    if lock_file is None:
        # Another coroutine of this run may have just taken the lock; share it now.
        return _join_existing_hold(name)
    with _state_lock:
        _holds[name] = _Hold(lock_file, 1)
        if not _waiters.get(name):
            _remove_ticket(name)
    return True


def _release(name: str) -> None:
    with _state_lock:
        hold = _holds.get(name)
        if hold is None:
            return
        hold.count -= 1
        if hold.count > 0:
            return
        del _holds[name]
        _unlock(hold.lock_file)
        if not _waiters.get(name):
            _remove_ticket(name)


async def _acquire_once(name: str) -> bool:
    """Try the slot in a worker thread without leaking it if this coroutine is cancelled."""
    future = asyncio.ensure_future(asyncio.to_thread(_try_acquire, name))
    try:
        return await asyncio.shield(future)
    except asyncio.CancelledError:
        # The thread keeps running; if it still wins the slot, give it back.
        def _undo(done: asyncio.Future[bool]) -> None:
            if not done.cancelled() and done.exception() is None and done.result():
                _release(name)

        future.add_done_callback(_undo)
        raise


@contextlib.asynccontextmanager
async def resource_slot(name: str, label: str) -> AsyncGenerator[None]:
    """Hold ``name`` across processes; the oldest waiting run acquires it first."""
    if name not in RESOURCES:
        raise ValueError(f"Unknown resource slot: {name}")

    if not await _acquire_once(name):
        with _state_lock:
            _waiters[name] = _waiters.get(name, 0) + 1
        progress_id = f"wait-{name}"
        logger.info(f"[yellow]Waiting for {label}: another upload is using it...[/yellow]")
        publish_progress(progress_id, f"Waiting: {label}", detail="Another upload tab is using this resource", status="waiting", group="coordination")
        try:
            while True:
                await asyncio.sleep(POLL_SECONDS)
                if await _acquire_once(name):
                    break
        finally:
            with _state_lock:
                _waiters[name] -= 1
                # Holding the lock needs no ticket; other local waiters re-create it.
                if not _waiters[name]:
                    _remove_ticket(name)
            complete_progress(progress_id, f"Waiting: {label}", group="coordination")

    try:
        yield
    finally:
        _release(name)


def holds_slot(name: str, label: str) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Coroutine[Any, Any, R]]]:
    """Run the decorated coroutine function inside ``resource_slot``."""

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Coroutine[Any, Any, R]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            async with resource_slot(name, label):
                return await func(*args, **kwargs)

        return wrapper

    return decorator
