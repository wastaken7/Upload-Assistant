"""Registry of upload sessions and their per-process state."""

import contextlib
import os
import secrets
import shlex
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from web_ui import paths as paths_mod
from web_ui.flask_compat import _is_str_dict
from web_ui.processes import ProcessInfo

# Lock protecting the active execution registry.
active_processes_lock = threading.Lock()
# Each WebUI tab holds one SSE stream; browsers allow ~6 connections per host.
MAX_CONCURRENT_SESSIONS = 4
# Uploads waiting for a free slot, and finished uploads kept for review.
MAX_SCHEDULED_SESSIONS = 16
MAX_RETAINED_FINISHED_SESSIONS = 4


# Store active processes
active_processes: dict[str, ProcessInfo] = {}


def _debug_process_snapshot(session_id: str | None = None) -> dict[str, object]:
    try:
        snapshot: dict[str, object] = {
            "active_sessions": list(active_processes.keys()),
        }
        if session_id and session_id in active_processes:
            info = active_processes.get(session_id, {})
            snapshot["session"] = {
                "mode": info.get("mode"),
                "has_worker": isinstance(info.get("worker"), threading.Thread),
                "has_stdout_thread": isinstance(info.get("stdout_thread"), threading.Thread),
                "has_stderr_thread": isinstance(info.get("stderr_thread"), threading.Thread),
            }
        return snapshot
    except Exception:
        return {"error": "failed to build snapshot"}


def _set_process_awaiting_input(session_id: str, waiting: bool, input_type: str = "text") -> None:
    with active_processes_lock:
        process_info = active_processes.get(session_id)
        if process_info is not None:
            process_info["awaiting_input"] = waiting
            process_info["input_type"] = input_type if waiting else None


def _set_process_awaiting_input_if_current(session_id: str, process_state: Mapping[str, object], waiting: bool, input_type: str = "text") -> None:
    with active_processes_lock:
        current_state = active_processes.get(session_id)
        if current_state is None or current_state is not process_state:
            return
        run_token = process_state.get("run_token")
        if run_token and current_state.get("run_token") == run_token:
            current_state["awaiting_input"] = waiting
            current_state["input_type"] = input_type if waiting else None


def _apply_progress_event(process_info: ProcessInfo, event: Mapping[str, object]) -> None:
    operation = str(event.get("op", "upsert")).strip().lower()
    if operation == "reset":
        process_info["progress"] = {}
        return

    progress_id = str(event.get("id", "")).strip()
    if not progress_id:
        return

    progress_map_obj = process_info.get("progress")
    if not isinstance(progress_map_obj, dict):
        progress_map_obj = {}
        process_info["progress"] = progress_map_obj
    progress_map = cast(dict[str, dict[str, object]], progress_map_obj)

    current_item = dict(progress_map.get(progress_id, {}))
    for key in ("id", "label", "detail", "status", "group", "unit", "updated_at"):
        if key in event:
            current_item[key] = event[key]
    for key in ("current", "total"):
        value = event.get(key)
        if isinstance(value, (int, float)):
            current_item[key] = float(value)
    progress_map[progress_id] = current_item


def _set_process_progress_if_current(session_id: str, process_state: Mapping[str, object], event: Mapping[str, object]) -> None:
    with active_processes_lock:
        current_state = active_processes.get(session_id)
        if current_state is None or current_state is not process_state:
            return
        run_token = process_state.get("run_token")
        if not (run_token and current_state.get("run_token") == run_token):
            return
        _apply_progress_event(current_state, event)


def _progress_items_locked(process_info: Mapping[str, object]) -> list[dict[str, object]]:
    """Copy a process's progress records; the caller holds active_processes_lock."""
    progress_map_obj = process_info.get("progress")
    if not _is_str_dict(progress_map_obj):
        return []
    items = [dict(value) for value in progress_map_obj.values() if _is_str_dict(value)]
    items.sort(key=lambda item: (0 if str(item.get("status", "")) == "running" else 1, str(item.get("id", ""))))
    return items


def _execution_item_paths(validated_path: str) -> list[str]:
    """Return the normalized content paths one execution will upload, in queue order."""
    paths = [validated_path]
    if paths_mod._is_generated_queue(validated_path):
        lines = Path(validated_path).read_text(encoding="utf-8").splitlines()
        paths = [shlex.split(line)[0] for line in lines if line.strip()]
    return [os.path.normcase(os.path.realpath(path)) for path in paths]


def _execution_content_paths(validated_path: str) -> frozenset[str]:
    return frozenset(_execution_item_paths(validated_path))


def _content_paths_overlap(first: frozenset[str], second: frozenset[str]) -> bool:
    for a in first:
        for b in second:
            with contextlib.suppress(ValueError):
                if os.path.commonpath([a, b]) in (a, b):
                    return True
    return False


def _execution_conflict_locked(session_id: str, content_paths: frozenset[str]) -> tuple[str, str] | None:
    """Return (code, message) when an execution cannot start now; caller holds active_processes_lock.

    "duplicate": a running or scheduled upload already claims this content.
    "capacity": every upload slot is busy, so the upload can only be scheduled.
    """
    # Finished sessions stay listed for review but no longer hold capacity or content.
    others = {key: info for key, info in active_processes.items() if key != session_id and _session_is_running(info)}
    for info in others.values():
        running_paths = info.get("content_paths")
        if isinstance(running_paths, frozenset) and _content_paths_overlap(content_paths, cast(frozenset[str], running_paths)):
            return "duplicate", "This content is already being uploaded in another tab"
    if sum(1 for info in others.values() if not info.get("scheduled")) >= MAX_CONCURRENT_SESSIONS:
        return "capacity", f"Maximum of {MAX_CONCURRENT_SESSIONS} concurrent uploads reached; wait for one to finish"
    return None


def _make_process_state(path: str, args: str) -> dict[str, object]:
    return {
        "run_token": secrets.token_hex(8),
        "mode": "starting",
        "path": path,
        "args": args,
        "started_at": time.time(),
        "awaiting_input": False,
        "input_type": None,
        "progress": {},
    }


def set_execution_preview_target(session_id: str, expected_run_token: str, path: str, meta_uuid: str | None = None) -> None:
    """Update the active preview target for a Web UI execution."""
    cleaned_session_id = str(session_id or "").strip()
    cleaned_run_token = str(expected_run_token or "").strip()
    cleaned_path = str(path or "").strip()
    if not cleaned_session_id or not cleaned_run_token or not cleaned_path:
        return

    with active_processes_lock:
        process_info = active_processes.get(cleaned_session_id)
        if process_info is None:
            return
        if str(process_info.get("run_token") or "").strip() != cleaned_run_token:
            return
        process_info["path"] = cleaned_path
        if meta_uuid:
            process_info["meta_uuid"] = str(meta_uuid).strip()
        else:
            process_info.pop("meta_uuid", None)


def _session_state_is_current(session_id: str, process_state: Mapping[str, object]) -> bool:
    with active_processes_lock:
        return _session_state_is_current_locked(session_id, process_state)


def _session_state_is_current_locked(session_id: str, process_state: Mapping[str, object]) -> bool:
    """Like _session_state_is_current; the caller holds active_processes_lock."""
    current_state = active_processes.get(session_id)
    if current_state is None or current_state is not process_state:
        return False
    run_token = process_state.get("run_token")
    return bool(run_token and current_state.get("run_token") == run_token)


def _execution_path_held_elsewhere_locked(key: str, own_state: Mapping[str, object] | None) -> bool:
    """Return whether a running or scheduled session other than own_state uses this normalized path.

    The caller holds active_processes_lock.
    """
    for info in active_processes.values():
        other_path = str(info.get("execution_path") or "")
        if info is own_state or not other_path or not _session_is_running(info):
            continue
        if os.path.normcase(os.path.realpath(other_path)) == key:
            return True
    return False


def _discard_session_state(session_id: str, process_state: Mapping[str, object]) -> None:
    with active_processes_lock:
        _discard_session_state_locked(session_id, process_state)


def _discard_session_state_locked(session_id: str, process_state: Mapping[str, object]) -> None:
    """Like _discard_session_state; the caller holds active_processes_lock."""
    if _session_state_is_current_locked(session_id, process_state):
        active_processes.pop(session_id, None)


def _session_is_running(process_state: Mapping[str, object]) -> bool:
    return "events_cond" not in process_state or not process_state.get("finished")
