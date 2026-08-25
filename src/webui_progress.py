from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable
from threading import Lock
from typing import TypedDict


class ProgressEvent(TypedDict, total=False):
    op: str
    id: str
    label: str
    current: float
    total: float
    detail: str
    status: str
    group: str
    unit: str
    updated_at: float


_callback: Callable[[ProgressEvent], None] | None = None
_callback_lock = Lock()
_stdout_lock = Lock()
PROGRESS_STDOUT_PREFIX = "UA_PROGRESS_JSON:"


def set_progress_callback(callback: Callable[[ProgressEvent], None] | None) -> None:
    with _callback_lock:
        global _callback
        _callback = callback


def clear_progress_callback(callback: Callable[[ProgressEvent], None] | None = None) -> None:
    """Clear the callback only if it still belongs to the finishing run."""
    with _callback_lock:
        global _callback
        if callback is None or _callback is callback:
            _callback = None


def has_progress_callback() -> bool:
    """Return whether the current process is publishing structured Web UI progress."""
    with _callback_lock:
        return _callback is not None or os.environ.get("UA_WEBUI_PROGRESS_STDOUT") == "1"


def _emit(event: ProgressEvent) -> None:
    with _callback_lock:
        callback = _callback
    if callback is None:
        if os.environ.get("UA_WEBUI_PROGRESS_STDOUT") == "1":
            with _stdout_lock:
                sys.stdout.write(f"\n{PROGRESS_STDOUT_PREFIX}{json.dumps(event, separators=(',', ':'))}\n")
                sys.stdout.flush()
        return
    callback(event)


def reset_progress() -> None:
    _emit({"op": "reset", "updated_at": time.time()})


def publish_progress(
    progress_id: str,
    label: str,
    *,
    current: float | int | None = None,
    total: float | int | None = None,
    detail: str = "",
    status: str = "running",
    group: str = "external",
    unit: str = "percent",
) -> None:
    event: ProgressEvent = {
        "op": "upsert",
        "id": str(progress_id),
        "label": str(label),
        "status": str(status),
        "group": str(group),
        "unit": str(unit),
        "updated_at": time.time(),
    }
    if current is not None:
        event["current"] = float(current)
    if total is not None:
        event["total"] = float(total)
    if detail:
        event["detail"] = str(detail)
    _emit(event)


def complete_progress(
    progress_id: str,
    label: str,
    *,
    current: float | int | None = None,
    total: float | int | None = None,
    detail: str = "",
    group: str = "external",
    unit: str = "percent",
) -> None:
    publish_progress(
        progress_id,
        label,
        current=current,
        total=total,
        detail=detail,
        status="completed",
        group=group,
        unit=unit,
    )
