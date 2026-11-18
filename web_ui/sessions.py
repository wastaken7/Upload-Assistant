"""Upload session state, scheduling and event streaming."""

import contextlib
import json
import os
import queue
import re
import threading
import time
import traceback
from collections import deque
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import cast

from src.prompt_sound import PROMPT_SOUND_STDOUT_MARKER
from web_ui import config_store as config_store_mod
from web_ui import context as context_mod
from web_ui import paths as paths_mod
from web_ui import preview as preview_mod
from web_ui import processes as processes_mod
from web_ui import session_state as session_state_mod
from web_ui.context import ansi_to_html, console
from web_ui.flask_compat import _WebUIProcess
from web_ui.paths import _generated_queues_lock, _remove_generated_queue_file, _remove_generated_queue_logs
from web_ui.preview import _music_preview_from_meta, _resolve_gui_item_artwork, _stringify_preview_value
from web_ui.processes import STRUCTURED_STDOUT_PREFIXES, _ConPtyProcess, _is_blank_output, _subprocess_gui_event, _subprocess_progress_event, _subprocess_prompt_type
from web_ui.request_utils import _as_dict
from web_ui.session_state import (
    MAX_CONCURRENT_SESSIONS,
    MAX_RETAINED_FINISHED_SESSIONS,
    _discard_session_state,
    _execution_path_held_elsewhere_locked,
    _session_is_running,
    _session_state_is_current,
    _session_state_is_current_locked,
    _set_process_awaiting_input_if_current,
    _set_process_progress_if_current,
    active_processes_lock,
    set_execution_preview_target,
)

# Background execution sessions ----------------------------------------------
#
# An upload runs in a pump thread that records its output in a bounded event
# log. Browser connections only tail that log, so closing a tab no longer kills
# the upload (unless webui_keep_uploads_on_disconnect is False) and a later
# visit can replay and follow it.

SESSION_EVENT_LOG_MAX_BYTES = 4 * 1024 * 1024
SESSION_KEEPALIVE_SECONDS = 1.0
# How long the pump keeps reading after the upload exits while a pipe stays open.
READER_DRAIN_GRACE_SECONDS = 2.0
FINISHED_SESSION_TTL_SECONDS = 24 * 60 * 60
SESSION_LABEL_MAX_LENGTH = 200


_session_settings_cache: tuple[tuple[str, int, str, int], tuple[bool, float]] | None = None


def _config_mtime_ns(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def _webui_session_settings() -> tuple[bool, float]:
    """Return (keep uploads running on disconnect, unattended prompt timeout in seconds)."""
    global _session_settings_cache
    user_path = context_mod.STATE_DIR / "data" / "config.py"
    example_path = context_mod.CODE_DIR / "data" / "example_config.py"
    # Polled often (session list, every execute); reparse only when a file changes.
    key = (str(user_path), _config_mtime_ns(user_path), str(example_path), _config_mtime_ns(example_path))
    if _session_settings_cache is not None and _session_settings_cache[0] == key:
        return _session_settings_cache[1]
    user_config = config_store_mod._load_config_from_file(user_path) or {}
    example_config = config_store_mod._load_config_from_file(example_path) or {}
    user_defaults = _as_dict(user_config.get("DEFAULT")) or {}
    example_defaults = _as_dict(example_config.get("DEFAULT")) or {}

    keep_value = user_defaults.get("webui_keep_uploads_on_disconnect", example_defaults.get("webui_keep_uploads_on_disconnect", True))
    keep_running = keep_value if isinstance(keep_value, bool) else str(keep_value).strip().lower() in {"1", "true", "yes", "on"}

    timeout_value = user_defaults.get("webui_unattended_prompt_timeout", example_defaults.get("webui_unattended_prompt_timeout", 60))
    try:
        timeout_minutes = max(0.0, float(timeout_value))
    except TypeError, ValueError:
        timeout_minutes = 60.0
    result = (keep_running, timeout_minutes * 60)
    _session_settings_cache = (key, result)
    return result


def _init_session_events(process_state: dict[str, object], *, label: str, keep_running: bool, prompt_timeout: float) -> None:
    now = time.time()
    process_state.update(
        {
            "label": label,
            "keep_running": keep_running,
            "prompt_timeout": prompt_timeout,
            "events": deque(),
            "events_bytes": 0,
            "events_trimmed": False,
            "next_seq": 1,
            "events_cond": threading.Condition(),
            "finished": False,
            "exit_code": None,
            "finished_at": None,
            "clients": 0,
            "detached_at": now,
            "awaiting_since": now,
            "last_input_at": now,
        }
    )


def _session_condition(process_state: Mapping[str, object]) -> threading.Condition:
    return cast(threading.Condition, process_state["events_cond"])


def _session_events(process_state: Mapping[str, object]) -> deque[tuple[int, str]]:
    return cast(deque[tuple[int, str]], process_state["events"])


def _publish_session_event(process_state: dict[str, object], event: Mapping[str, object]) -> None:
    """Append one event to the session log, trimming the oldest output past the size cap."""
    condition = _session_condition(process_state)
    with condition:
        seq = cast(int, process_state["next_seq"])
        process_state["next_seq"] = seq + 1
        payload = json.dumps({**event, "seq": seq})
        events = _session_events(process_state)
        events.append((seq, payload))
        size = cast(int, process_state["events_bytes"]) + len(payload)
        while size > SESSION_EVENT_LOG_MAX_BYTES and len(events) > 1:
            _seq, dropped = events.popleft()
            size -= len(dropped)
            process_state["events_trimmed"] = True
        process_state["events_bytes"] = size
        condition.notify_all()


def _finish_session(process_state: dict[str, object], exit_code: int | None) -> None:
    condition = _session_condition(process_state)
    with condition:
        process_state["finished"] = True
        process_state["exit_code"] = exit_code
        process_state["finished_at"] = time.time()
        process_state["awaiting_input"] = False
        condition.notify_all()


def _prune_finished_sessions_locked() -> None:
    """Drop expired finished sessions and keep only the newest few; caller holds active_processes_lock."""
    now = time.time()
    finished = sorted(
        ((key, info) for key, info in session_state_mod.active_processes.items() if not _session_is_running(info)),
        key=lambda item: float(cast(float, item[1].get("finished_at") or 0)),
    )
    kept = [(key, info) for key, info in finished if now - float(cast(float, info.get("finished_at") or 0)) <= FINISHED_SESSION_TTL_SECONDS]
    for key, _info in finished[: len(finished) - len(kept)] + kept[: max(0, len(kept) - MAX_RETAINED_FINISHED_SESSIONS)]:
        session_state_mod.active_processes.pop(key, None)


def _launch_session(session_id: str, process_state: dict[str, object]) -> None:
    """Start a registered session's upload controller and the pump that records its output."""
    command, base_dir, env = cast(tuple[list[str], Path, dict[str, str]], process_state["launch"])
    # codeql[py/command-line-injection]
    process, process_mode = processes_mod._spawn_webui_upload_process(command, base_dir, env)
    # Publish the handle and check the session under one lock, so Kill either
    # sees the handle or has already cancelled the startup.
    with active_processes_lock:
        process_state.update({"mode": process_mode, "process": process})
        still_current = _session_state_is_current_locked(session_id, process_state)
    if not still_current:
        processes_mod._terminate_process_tree(process)
        processes_mod._close_webui_process_io(process)
        raise RuntimeError("Execution session was replaced before subprocess startup completed")
    try:
        threading.Thread(
            target=_pump_session,
            args=(session_id, process_state, process, process_mode),
            name=f"webui-session-{session_id}",
            daemon=True,
        ).start()
    except BaseException:
        # Without a pump nobody owns the controller; stop it before the caller
        # releases the reservation and its queue.
        with contextlib.suppress(Exception):
            processes_mod._terminate_process_tree(process)
        processes_mod._close_webui_process_io(process)
        raise


def _start_scheduled_sessions() -> None:
    """Launch scheduled uploads, oldest first, while upload slots are free."""
    while True:
        with active_processes_lock:
            busy = sum(1 for info in session_state_mod.active_processes.values() if _session_is_running(info) and not info.get("scheduled"))
            waiting = sorted(
                # A scheduled entry is registered before its launch command is
                # stored; execute_command calls this again once it is set.
                ((key, info) for key, info in session_state_mod.active_processes.items() if info.get("scheduled") and "launch" in info and _session_is_running(info)),
                key=lambda item: float(cast(float, item[1].get("scheduled_at") or 0)),
            )
            if busy >= MAX_CONCURRENT_SESSIONS or not waiting:
                return
            session_id, process_state = waiting[0]
            process_state["scheduled"] = False
        console.print(f"Starting scheduled upload session {session_id}", markup=False)
        _publish_session_event(process_state, {"type": "started"})
        try:
            _launch_session(session_id, process_state)
        except Exception as e:
            console.print(f"Could not start scheduled session {session_id}: {e}", markup=False)
            _publish_session_event(process_state, {"type": "error", "data": "Execution error"})
            _release_session_queue_file(str(process_state.get("execution_path") or ""), process_state)
            _finish_session(process_state, None)


SESSION_LABEL_REFRESH_SECONDS = 5.0
SESSION_LABEL_SEPARATOR = " \u2013 "  # en dash between artist/author and work


def _session_display_label(meta_data: Mapping[str, object]) -> str:
    """Build a short, recognisable tab label from an upload's metadata ("" until it is known)."""

    def text(*keys: str) -> str:
        for key in keys:
            value = _stringify_preview_value(meta_data.get(key))
            if value:
                return value
        return ""

    category = text("category").upper()
    title = text("title")
    if category == "MUSIC":
        music = _music_preview_from_meta(meta_data)
        artist = _stringify_preview_value(music.get("artist")) or text("artist")
        album = _stringify_preview_value(music.get("album")) or title
        return SESSION_LABEL_SEPARATOR.join(part for part in (artist, album) if part)
    if category == "BOOK":
        author = text("author", "book_author")
        book_title = text("book_title") or title
        return SESSION_LABEL_SEPARATOR.join(part for part in (author, book_title) if part)
    if not title:
        return ""
    if category == "TV":
        tv_pack = text("tv_pack").lower() not in ("", "0", "false", "none", "null")
        episode = "" if tv_pack else text("episode")
        return f"{title} {text('season')}{episode}".strip()
    year = text("year")
    if category == "MOVIE" and year.isdigit() and int(year) > 0:
        return f"{title} ({year})"
    return title


def _refresh_session_label(session_id: str, process_state: dict[str, object]) -> None:
    """Publish a better tab label once the current item's metadata is known."""
    process_state["label_checked_at"] = time.time()
    current_path = _stringify_preview_value(process_state.get("path"))
    _path, _meta_file, meta_data = preview_mod._resolve_execution_preview_meta(session_id)
    label = _session_display_label(meta_data) if meta_data is not None else ""
    detail = _stringify_preview_value(meta_data.get("name")) if meta_data is not None else ""

    item_paths = cast(list[str], process_state.get("item_paths") or [])
    if len(item_paths) > 1:
        normalized = os.path.normcase(os.path.realpath(current_path)) if current_path else ""
        if normalized in item_paths:
            label = f"[{item_paths.index(normalized) + 1}/{len(item_paths)}] {label or Path(current_path).name}"
    if not label or (label, detail) == (process_state.get("label"), process_state.get("label_detail")):
        return
    process_state["label"] = label
    process_state["label_detail"] = detail
    _publish_session_event(process_state, {"type": "label", "label": label, "detail": detail})


def _session_summary(session_id: str, process_state: Mapping[str, object]) -> dict[str, object]:
    condition = _session_condition(process_state)
    with condition:
        return {
            "session_id": session_id,
            "label": str(process_state.get("label") or Path(str(process_state.get("path") or "")).name),
            "label_detail": str(process_state.get("label_detail") or ""),
            "scheduled": bool(process_state.get("scheduled")),
            "running": not process_state.get("finished"),
            "exit_code": process_state.get("exit_code"),
            "awaiting_input": bool(process_state.get("awaiting_input")),
            "started_at": process_state.get("started_at"),
            "finished_at": process_state.get("finished_at"),
            "last_seq": cast(int, process_state["next_seq"]) - 1,
        }


def _sse(event: Mapping[str, object]) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _stream_session_events(session_id: str, process_state: dict[str, object], after: int) -> Iterator[str]:
    """Replay logged events after ``after`` and follow the session until it finishes."""
    condition = _session_condition(process_state)
    with condition:
        process_state["clients"] = cast(int, process_state["clients"]) + 1
    try:
        with condition:
            backlog = [(seq, payload) for seq, payload in _session_events(process_state) if seq > after]
            trimmed = bool(process_state.get("events_trimmed")) and (not backlog or backlog[0][0] > after + 1)
        if trimmed:
            yield _sse({"type": "truncated"})
        last_seq = after
        for seq, payload in backlog:
            yield f"data: {payload}\n\n"
            last_seq = seq
        yield _sse({"type": "replay_done"})

        while True:
            with condition:
                condition.wait_for(
                    lambda seen=last_seq: cast(int, process_state["next_seq"]) - 1 > seen or bool(process_state.get("finished")),
                    timeout=SESSION_KEEPALIVE_SECONDS,
                )
                pending = [(seq, payload) for seq, payload in _session_events(process_state) if seq > last_seq]
                finished = bool(process_state.get("finished"))
            for seq, payload in pending:
                yield f"data: {payload}\n\n"
                last_seq = seq
            if not pending:
                if finished:
                    # Tells the browser the session is over, not that the connection dropped.
                    yield _sse({"type": "finished", "exit_code": process_state.get("exit_code")})
                    break
                yield _sse({"type": "keepalive"})
    finally:
        with condition:
            clients = cast(int, process_state["clients"]) - 1
            process_state["clients"] = clients
            if clients == 0:
                process_state["detached_at"] = time.time()
            orphaned = clients == 0 and not process_state.get("finished")
        if orphaned and not process_state.get("keep_running", True):
            # Legacy behaviour: the upload lives only as long as a browser follows it.
            process = cast(_WebUIProcess | None, process_state.get("process"))
            if process is not None and process.poll() is None:
                with contextlib.suppress(Exception):
                    processes_mod._terminate_process_tree(process)
            _discard_session_state(session_id, process_state)


def _unanswered_prompt_expired(process_state: Mapping[str, object]) -> bool:
    timeout = float(cast(float, process_state.get("prompt_timeout") or 0))
    if timeout <= 0 or not process_state.get("awaiting_input"):
        return False
    with _session_condition(process_state):
        if cast(int, process_state["clients"]) > 0:
            return False
        since = max(
            float(cast(float, process_state["awaiting_since"])),
            float(cast(float, process_state["detached_at"])),
            float(cast(float, process_state["last_input_at"])),
        )
    return time.time() - since >= timeout


def _subprocess_html_fragment(chunk: str) -> str:
    try:
        if ansi_to_html:
            return ansi_to_html(chunk)
    except Exception as e:
        console.print(f"HTML conversion error: {e}", markup=False)
    import html as _html

    return f"<pre>{_html.escape(chunk)}</pre>"


def _remove_session_queue_file(validated_path: str) -> None:
    try:
        key = os.path.normcase(os.path.realpath(validated_path))
        with _generated_queues_lock:
            generated = paths_mod._generated_queues.pop(key, None)
        _cleanup_released_queue(key, generated, validated_path)
    except Exception as cleanup_err:
        console.print(f"Failed to cleanup queue file: {cleanup_err}", markup=False)


def _release_session_queue_file(validated_path: str, own_state: Mapping[str, object] | None) -> None:
    """Release a queue unless a session other than own_state still uses it.

    The holder check and the release share the registration lock, so a request
    that registers the same queue either keeps it alive or sees it expired.
    """
    if not validated_path:
        return
    try:
        key = os.path.normcase(os.path.realpath(validated_path))
        with active_processes_lock:
            if _execution_path_held_elsewhere_locked(key, own_state):
                return
            with _generated_queues_lock:
                generated = paths_mod._generated_queues.pop(key, None)
                # Saving the same selection twice gives two files one log name
                # (it comes from the content hash): keep the logs while another
                # session runs a queue with that hash.
                logs_in_use = generated is not None and _queue_hash_held_elsewhere_locked(generated, own_state)
        _cleanup_released_queue(key, generated, validated_path, remove_logs=not logs_in_use)
    except Exception as cleanup_err:
        console.print(f"Failed to cleanup queue file: {cleanup_err}", markup=False)


def _queue_hash_held_elsewhere_locked(queue_hash: str, own_state: Mapping[str, object] | None) -> bool:
    """Caller holds active_processes_lock and _generated_queues_lock."""
    for info in session_state_mod.active_processes.values():
        other_path = str(info.get("execution_path") or "")
        if info is own_state or not other_path or not _session_is_running(info):
            continue
        if paths_mod._generated_queues.get(os.path.normcase(os.path.realpath(other_path))) == queue_hash:
            return True
    return False


def _cleanup_released_queue(key: str, generated: str | None, validated_path: str, *, remove_logs: bool = True) -> None:
    if generated is None:
        return
    lines = Path(key).read_text(encoding="utf-8").splitlines() if Path(key).is_file() else []
    _remove_generated_queue_file(key)
    if remove_logs:
        _remove_generated_queue_logs(generated, lines)
    console.print(f"Cleaned up queue file: {Path(validated_path).name}", markup=False)


def _pump_session(session_id: str, process_state: dict[str, object], process: _WebUIProcess, process_mode: str) -> None:
    """Read one upload's output into its session log until the process exits."""
    exit_code: int | None = None
    try:
        output_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        # At the drain cutoff the readers stop handing output to the pump. They
        # keep reading, so a descendant writing to the pipe never blocks on it.
        output_gate = threading.Lock()
        output_closed = False

        def accept_output(item: tuple[str, str]) -> None:
            with output_gate:
                if not output_closed:
                    output_queue.put(item)

        if isinstance(process, _ConPtyProcess):
            # A pseudo terminal combines stdout and stderr into one ANSI stream.
            def read_stdout():
                try:
                    while True:
                        # Keep the same incremental prompt detection semantics as
                        # the pipe reader. ConPTY can return a whole prompt plus
                        # its trailing input marker in one read.
                        for char in process.read(1024):
                            accept_output(("stdout", char))
                except EOFError:
                    pass
                except Exception as err:
                    console.print(f"ConPTY read error: {err}", markup=False)

            stdout_thread = threading.Thread(target=read_stdout, daemon=True)
            stderr_thread = None
        else:
            # Thread to read stdout - stream raw output with ANSI codes
            def read_stdout():
                try:
                    stdout = getattr(process, "stdout", None)
                    if stdout is None:
                        return
                    while True:
                        chunk = stdout.read(1)
                        if not chunk:
                            break
                        accept_output(("stdout", chunk))
                except Exception as err:
                    console.print(f"stdout read error: {err}", markup=False)

            # Thread to read stderr - stream raw output
            def read_stderr():
                try:
                    stderr = getattr(process, "stderr", None)
                    if stderr is None:
                        return
                    while True:
                        chunk = stderr.read(1)
                        if not chunk:
                            break
                        accept_output(("stderr", chunk))
                except Exception as err:
                    console.print(f"stderr read error: {err}", markup=False)

            stdout_thread = threading.Thread(target=read_stdout, daemon=True)
            stderr_thread = threading.Thread(target=read_stderr, daemon=True)

        stdout_thread.start()
        if stderr_thread is not None:
            stderr_thread.start()

        # Record threads and output queue for debugging/cleanup
        with contextlib.suppress(Exception):
            if _session_state_is_current(session_id, process_state):
                process_state["stdout_thread"] = stdout_thread
                process_state["stderr_thread"] = stderr_thread
                process_state["output_queue"] = output_queue

        console.print(
            f"Started {process_mode} reader threads for session {session_id}: stdout={stdout_thread.name}, stderr={getattr(stderr_thread, 'name', 'merged')}",
            markup=False,
        )

        def _read_output(q: queue.Queue[tuple[str, str]]) -> tuple[bool, tuple[str, str] | None]:
            try:
                return True, q.get(timeout=0.1)
            except queue.Empty:
                return False, None

        buffers: dict[str, str] = {"stdout": "", "stderr": ""}
        last_prompt_state: tuple[bool, object] = (False, None)
        held_blank: tuple[str, str] | None = None
        prompt_timed_out = False
        orphaned = False

        exited_at: float | None = None
        while True:
            # Process exit does not mean its pipes are drained: keep reading
            # until both readers reach EOF. A descendant that inherited the
            # pipe can hold it open (silent or still writing), so after a
            # grace period only the output already queued at the cutoff is
            # processed.
            exited = process.poll() is not None
            if exited:
                readers_done = not stdout_thread.is_alive() and (stderr_thread is None or not stderr_thread.is_alive())
                if readers_done and output_queue.empty():
                    break
                if exited_at is None:
                    exited_at = time.monotonic()
                elif not output_closed and time.monotonic() - exited_at >= READER_DRAIN_GRACE_SECONDS:
                    with output_gate:
                        output_closed = True
                # Closed: nothing new arrives, so the queue empties in finite time.
                if output_closed and output_queue.empty():
                    break
            if not exited and not prompt_timed_out and _unanswered_prompt_expired(process_state):
                prompt_timed_out = True
                minutes = float(cast(float, process_state["prompt_timeout"])) / 60
                message = f"Upload killed: a prompt went unanswered for {minutes:g} minutes with no browser connected"
                console.print(f"{message} (session {session_id})", markup=False)
                _publish_session_event(process_state, {"type": "error", "data": message})
                with contextlib.suppress(Exception):
                    processes_mod._terminate_process_tree(process)

            has_output, output = _read_output(output_queue)
            previous_prompt_type = str(process_state.get("input_type") or "text") if process_state.get("awaiting_input") else None
            if has_output and output is not None:
                output_type, char = output
                if output_type not in buffers:
                    buffers[output_type] = ""
                buffers[output_type] += char
                prompt_type = _subprocess_prompt_type(buffers[output_type], previous_prompt_type)

                if not processes_mod._should_flush_subprocess_output(buffers[output_type], char):
                    continue
            else:
                # cli_ui writes its input marker without a newline.
                # Flush it when output has been idle for the queue timeout.
                pending_type = next((kind for kind, buffer in buffers.items() if processes_mod._should_flush_subprocess_output(buffer, "", idle=True)), None)
                if pending_type is None:
                    # A dismissed or replaced session has nobody left to report to.
                    if not _session_state_is_current(session_id, process_state):
                        orphaned = True
                        break
                    if time.time() - float(cast(float, process_state.get("label_checked_at") or 0)) >= SESSION_LABEL_REFRESH_SECONDS:
                        _refresh_session_label(session_id, process_state)
                    continue
                output_type = pending_type
                prompt_type = _subprocess_prompt_type(buffers[output_type], previous_prompt_type)

            chunk = buffers[output_type]
            buffers[output_type] = ""
            stripped_chunk = chunk.strip()
            structured = stripped_chunk == PROMPT_SOUND_STDOUT_MARKER or stripped_chunk.startswith(STRUCTURED_STDOUT_PREFIXES)
            if held_blank is not None:
                # Structured lines start with a newline so they never join a
                # terminal line; drop the blank line that newline produced.
                if not structured:
                    _publish_session_event(process_state, {"type": "html", "data": _subprocess_html_fragment(held_blank[1]), "origin": held_blank[0]})
                held_blank = None
            if not structured and not prompt_type and chunk.endswith("\n") and _is_blank_output(chunk):
                held_blank = (output_type, chunk)
                continue

            if stripped_chunk == PROMPT_SOUND_STDOUT_MARKER:
                _publish_session_event(process_state, {"type": "prompt_sound"})
                continue

            gui_event = _subprocess_gui_event(chunk)
            if gui_event is not None:
                if gui_event:
                    _publish_session_event(process_state, {"type": "gui", "data": _resolve_gui_item_artwork(session_id, process_state, gui_event)})
                continue

            progress_event = _subprocess_progress_event(chunk)
            if progress_event is not None:
                if progress_event.get("op") == "preview_target":
                    target_path = progress_event.get("path")
                    meta_uuid = progress_event.get("meta_uuid")
                    if isinstance(target_path, str) and (meta_uuid is None or isinstance(meta_uuid, str)):
                        set_execution_preview_target(session_id, str(process_state["run_token"]), target_path, meta_uuid)
                        _refresh_session_label(session_id, process_state)
                    continue
                _set_process_progress_if_current(session_id, process_state, progress_event)
                _publish_session_event(process_state, {"type": "progress", "data": progress_event})
                continue

            # Structured progress and its blank/ANSI separator lines
            # do not answer or replace an outstanding terminal prompt.
            if prompt_type:
                _set_process_awaiting_input_if_current(session_id, process_state, True, prompt_type)
            elif re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", chunk).strip():
                _set_process_awaiting_input_if_current(session_id, process_state, False)
            # Lets background tabs flag a pending prompt without polling.
            prompt_state = (bool(process_state.get("awaiting_input")), process_state.get("input_type"))
            if prompt_state != last_prompt_state:
                if prompt_state[0] and not last_prompt_state[0]:
                    with _session_condition(process_state):
                        process_state["awaiting_since"] = time.time()
                last_prompt_state = prompt_state
                _publish_session_event(process_state, {"type": "prompt_state", "awaiting": prompt_state[0], "input_type": prompt_state[1]})

            _publish_session_event(process_state, {"type": "html", "data": _subprocess_html_fragment(chunk), "origin": output_type})

        # Flush remaining buffers as HTML
        if held_blank is not None:
            _publish_session_event(process_state, {"type": "html", "data": _subprocess_html_fragment(held_blank[1]), "origin": held_blank[0]})
        for output_type, remaining in list(buffers.items()):
            if remaining:
                _publish_session_event(process_state, {"type": "html", "data": _subprocess_html_fragment(remaining), "origin": output_type})

        if not orphaned:
            exit_code = process.wait()
    except Exception as e:
        console.print(f"Execution error for session {session_id}: {e}", markup=False)
        console.print(traceback.format_exc(), markup=False)
        _publish_session_event(process_state, {"type": "error", "data": "Execution error"})
    finally:
        with contextlib.suppress(Exception):
            if process.poll() is None:
                processes_mod._terminate_process_tree(process)
        processes_mod._close_webui_process_io(process)
        # A finished session must not keep unrendered output alive.
        process_state.pop("output_queue", None)
        # A replacement session in the same tab can already run this queue again.
        _release_session_queue_file(str(process_state.get("execution_path") or ""), process_state)
        if exit_code is not None:
            _publish_session_event(process_state, {"type": "exit", "code": exit_code})
        _finish_session(process_state, exit_code)
        _start_scheduled_sessions()
