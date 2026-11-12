# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Time-based upload controls: a fixed upload time and a minimum interval between uploads.

Both waits happen after the release is fully prepared and right before the
upload starts. After a wait, each torrent tracker repeats its duplicate check
(see ``recheck_dupes_after_wait`` in ``src/trackerhandle.py``).
"""

import asyncio
import re
import time
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timedelta
from typing import Any, cast

from src.console import console, logger
from src.meta import Meta
from src.webui_progress import complete_progress, has_progress_callback, publish_progress

_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_DURATION_RE = re.compile(r"(?:\d+[smhd])+")
_DURATION_PART_RE = re.compile(r"(\d+)([smhd])")
_TIME_ONLY_RE = re.compile(r"(\d{1,2}):(\d{2})(?::(\d{2}))?")
_PROGRESS_ID = "upload-schedule"


def parse_duration(value: object) -> int:
    """Return a duration in seconds from ``90``, ``90s``, ``45m``, ``2h``, ``1d`` or ``1h30m``."""
    if value is None or value is False or value == "":
        return 0
    if isinstance(value, bool):
        raise ValueError(f"invalid duration: {value!r}")
    if isinstance(value, (int, float)):
        if value < 0:
            raise ValueError(f"duration cannot be negative: {value!r}")
        return int(value)
    text = str(value).strip().lower().replace(" ", "")
    if text.isdigit():
        return int(text)
    if not _DURATION_RE.fullmatch(text):
        raise ValueError(f"invalid duration '{value}': use seconds or a value such as 90s, 45m, 2h or 1h30m")
    return sum(int(amount) * _UNIT_SECONDS[unit] for amount, unit in _DURATION_PART_RE.findall(text))


def _local_instants(wall_time: datetime) -> list[datetime]:
    """Return the local instants for a naive wall time, earliest first.

    A repeated DST hour has two; a time skipped by a DST change has none.
    """
    instants = {wall_time.replace(fold=fold).astimezone() for fold in (0, 1)}
    existing = [instant for instant in instants if instant.replace(tzinfo=None) == wall_time]
    return sorted(existing, key=lambda instant: instant.timestamp())


def resolve_upload_at(value: str, now: datetime | None = None) -> datetime:
    """Resolve ``HH:MM[:SS]`` or ``YYYY-MM-DD HH:MM[:SS]`` to a timezone-aware local datetime in the future.

    A time of day means its next occurrence: later today, the second occurrence
    of a repeated DST hour, or tomorrow. A full date in the past is an error,
    so a typo cannot start an upload immediately.
    """
    now_ts = (now or datetime.now().astimezone()).timestamp()
    text = str(value).strip()
    time_match = _TIME_ONLY_RE.fullmatch(text)
    if time_match:
        hour, minute, second = (int(part or 0) for part in time_match.groups())
        if hour > 23 or minute > 59 or second > 59:
            raise ValueError(f"invalid time '{value}'")
        today = datetime.fromtimestamp(now_ts).astimezone().replace(hour=hour, minute=minute, second=second, microsecond=0, tzinfo=None)
        # A third day covers a time that DST skips tomorrow after it passed today.
        for day in (today + timedelta(days=offset) for offset in range(3)):
            for instant in _local_instants(day):
                if instant.timestamp() > now_ts:
                    return instant
        raise ValueError(f"could not resolve upload time '{value}'")

    if ":" not in text:
        raise ValueError(f"invalid upload time '{value}': include a time, for example 23:30 or '2026-11-15 23:30'")
    try:
        target = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(f"invalid upload time '{value}': use HH:MM or 'YYYY-MM-DD HH:MM'") from None
    if target.tzinfo is None:
        instants = _local_instants(target)
        if not instants:
            raise ValueError(f"upload time '{value}' does not exist in the local timezone (skipped by a DST change)")
        target = instants[0]
    else:
        target = target.astimezone()
    if target.timestamp() <= now_ts:
        raise ValueError(f"upload time '{value}' is in the past")
    return target


def format_duration(seconds: float) -> str:
    seconds = max(0, round(seconds))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    parts = [f"{days}d"] if days else []
    if hours or days:
        parts.append(f"{hours}h")
    if not days:
        parts.append(f"{minutes:02d}m" if parts else f"{minutes}m")
        if not hours:
            parts.append(f"{secs:02d}s")
    return " ".join(parts)


def configured_upload_interval(meta: Meta, config: Mapping[str, Any]) -> int:
    """Return the interval from the command line (``0`` disables it), or else from ``DEFAULT.upload_interval``.

    An invalid configured value raises ``ValueError``; config validation reports it before the run starts.
    """
    if meta.upload_interval is not None:
        return int(meta.upload_interval)
    return parse_duration(config.get("DEFAULT", {}).get("upload_interval", 0))


class UploadPacer:
    """Remember when this run last uploaded, so queue items keep a minimum interval."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self.last_upload_at: float | None = None

    def record(self, meta: Meta) -> None:
        statuses = [cast(Mapping[str, Any], status) for status in meta.tracker_status.values() if isinstance(status, Mapping)]
        if meta.nzb_path or any(status.get("upload_success") is True for status in statuses):
            self.last_upload_at = self._clock()


async def wait_until(
    target: float,
    label: str,
    *,
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    chunk: float = 30.0,
) -> bool:
    """Sleep until the wall-clock ``target``, in short steps that survive system sleep and clock changes."""
    remaining = target - clock()
    if remaining <= 0:
        return False
    total = remaining
    target_text = datetime.fromtimestamp(target).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[yellow]{label}: waiting until {target_text} ({format_duration(remaining)}).[/yellow]")
    web_progress = has_progress_callback()
    while remaining > 0:
        detail = f"Upload at {target_text} ({format_duration(remaining)} left)"
        if web_progress:
            percent = max(0.0, min(100.0, (total - remaining) / total * 100))
            publish_progress(_PROGRESS_ID, label, current=percent, total=100, detail=detail, group="schedule")
        else:
            console.print(f"[yellow]{label}: {detail}[/yellow]     ", end="\r")
        await sleep(min(chunk, remaining))
        remaining = target - clock()
    if web_progress:
        complete_progress(_PROGRESS_ID, label, detail=f"Started at {datetime.now().astimezone().strftime('%H:%M:%S')}", group="schedule")
    else:
        console.print()
    logger.info(f"[green]{label}: wait finished.[/green]")
    return True


async def wait_before_upload(
    meta: Meta,
    config: Mapping[str, Any],
    pacer: UploadPacer | None,
    *,
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> bool:
    """Wait for ``--upload-at`` and ``--upload-interval``; return True when the upload was delayed."""
    targets: list[tuple[float, str]] = []
    if meta.upload_at:
        targets.append((datetime.fromisoformat(meta.upload_at).timestamp(), "Scheduled upload"))
    interval = configured_upload_interval(meta, config)
    if interval > 0 and pacer is not None and pacer.last_upload_at is not None:
        targets.append((pacer.last_upload_at + interval, "Upload interval"))
    if not targets:
        return False

    target, label = max(targets)
    if target <= clock():
        return False
    if meta.debug:
        target_text = datetime.fromtimestamp(target).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"[yellow]{label}: debug mode, not waiting until {target_text}.[/yellow]")
        return False
    return await wait_until(target, label, clock=clock, sleep=sleep)
