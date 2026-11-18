"""Upload session routes: queue, execute, input, kill and session streaming."""

import contextlib
import hashlib
import json
import os
import re
import secrets
import shlex
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import cast

from src.webui_paths import MAX_UPLOAD_PATHS, QUEUE_ENV, QUEUE_HASH_ENV, ROOTS_ENV, InspectedDirectories
from web_ui import context as context_mod
from web_ui import paths as paths_mod
from web_ui import processes as processes_mod
from web_ui import security as security_mod
from web_ui import session_state as session_state_mod
from web_ui import sessions as sessions_mod
from web_ui.argument_presets import MAX_ARGUMENT_PRESETS, _argument_presets_lock, _load_argument_presets, _save_argument_presets
from web_ui.context import console
from web_ui.extensions import _rate_limit_key_func, limiter
from web_ui.flask_compat import Blueprint, Response, _is_obj_list, _is_str_dict, _ResponseLike, jsonify, request
from web_ui.paths import _generated_queues_lock, _prune_stale_queue_logs, _remove_generated_queue_file
from web_ui.processes import _write_webui_process_input
from web_ui.request_utils import _as_dict, _json_load_dict, _request_json_dict
from web_ui.security import _token_is_valid
from web_ui.session_state import (
    MAX_CONCURRENT_SESSIONS,
    MAX_SCHEDULED_SESSIONS,
    _debug_process_snapshot,
    _discard_session_state,
    _discard_session_state_locked,
    _execution_conflict_locked,
    _make_process_state,
    _session_is_running,
    _set_process_awaiting_input,
    active_processes_lock,
)
from web_ui.sessions import (
    SESSION_LABEL_MAX_LENGTH,
    _finish_session,
    _init_session_events,
    _launch_session,
    _prune_finished_sessions_locked,
    _publish_session_event,
    _session_condition,
    _session_summary,
    _sse,
    _start_scheduled_sessions,
    _stream_session_events,
)

bp = Blueprint("sessions", __name__)


@bp.route("/api/argument_presets", methods=["GET", "POST", "DELETE"])
@limiter.limit("7200 per hour", key_func=_rate_limit_key_func, override_defaults=True)
def argument_presets():
    """Read and persist shared Web UI argument presets in ``data``."""
    if not security_mod._is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
    if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

    with _argument_presets_lock:
        presets = _load_argument_presets()
        if request.method == "GET":
            return jsonify({"success": True, "presets": presets})

        data = _request_json_dict()
        name_value = data.get("name")
        name = name_value.strip() if isinstance(name_value, str) else ""
        if not name:
            return jsonify({"success": False, "error": "Preset name is required"}), 400

        if request.method == "DELETE":
            next_presets = [preset for preset in presets if preset["name"].casefold() != name.casefold()]
        else:
            arguments_value = data.get("arguments")
            arguments = arguments_value.strip() if isinstance(arguments_value, str) else ""
            if not arguments:
                return jsonify({"success": False, "error": "Preset arguments are required"}), 400
            replacement = {"name": name, "arguments": arguments}
            existing_index = next(
                (index for index, preset in enumerate(presets) if preset["name"].casefold() == name.casefold()),
                None,
            )
            if existing_index is None:
                next_presets = [*presets, replacement][-MAX_ARGUMENT_PRESETS:]
            else:
                next_presets = presets.copy()
                next_presets[existing_index] = replacement

        try:
            _save_argument_presets(next_presets)
        except OSError:
            return jsonify({"success": False, "error": "Failed to persist argument presets"}), 500
        return jsonify({"success": True, "presets": next_presets})


def _save_queue_created_file(response: _ResponseLike) -> bool:
    """Only issued queue files count against the quota, not path validation."""
    data = response.get_json(silent=True)
    return _is_str_dict(data) and data.get("queued") is True


@bp.route("/api/save_queue", methods=["POST"])
@limiter.limit("100 per hour", key_func=_rate_limit_key_func, deduct_when=_save_queue_created_file)
def save_queue():
    """Save selected items to a temporary queue text file on the server"""
    # CSRF check
    if not security_mod._verify_csrf_header():
        return jsonify({"error": "CSRF token missing or invalid", "success": False}), 403

    # Auth check
    bearer = security_mod._get_bearer_from_header()
    if bearer:
        if not _token_is_valid(bearer):
            return jsonify({"success": False, "error": "Forbidden (invalid token)"}), 403
    else:
        if not security_mod._is_authenticated():
            return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
        if not security_mod._verify_same_origin():
            return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

    try:
        data = _as_dict(request.get_json(silent=True)) or {}
        items = data.get("items")
        if not _is_obj_list(items):
            return jsonify({"error": "Items must be a list", "success": False}), 400

        if not items:
            return jsonify({"error": "No items provided", "success": False}), 400
        if len(items) > MAX_UPLOAD_PATHS:
            return jsonify({"error": f"Maximum {MAX_UPLOAD_PATHS} paths per upload", "success": False}), 400

        base_dir = context_mod.STATE_DIR
        tmp_dir = base_dir / "tmp"
        filename = f"webui_queue_{int(time.time() * 1000)}_{secrets.token_hex(4)}.txt"
        file_path = tmp_dir / filename

        validated_items: list[tuple[str, list[str]]] = []
        inspected_directories: InspectedDirectories = set()
        # Item number by normalized content path, and by each of its parent folders.
        claimed_paths: dict[str, int] = {}
        claimed_parents: dict[str, int] = {}
        for number, item in enumerate(items, 1):
            if not _is_str_dict(item):
                return jsonify({"error": f"Invalid queue item {number}", "success": False, "item": number}), 400
            path = item.get("path")
            args = item.get("args", "")

            try:
                if not isinstance(path, str) or not path.strip() or not isinstance(args, str):
                    raise ValueError("Path and arguments must be strings; path cannot be empty")
                validated_path = paths_mod._validate_execution_path(path.strip(), inspected_directories=inspected_directories)
                if paths_mod._is_generated_queue(validated_path):
                    raise ValueError("Nested queues are not allowed")
                validated_args = paths_mod._validate_upload_assistant_args(shlex.split(args) if args else [], inspected_directories=inspected_directories)
            except (ValueError, TypeError) as err:
                return jsonify({"error": f"Invalid queue item {number}: {err}", "success": False, "item": number}), 400
            content_key = os.path.normcase(validated_path)
            parent_keys = [str(parent) for parent in Path(content_key).parents]
            # The same content twice, or a folder plus something inside it, would upload twice.
            overlapping = next((claimed_paths[key] for key in (content_key, *parent_keys) if key in claimed_paths), claimed_parents.get(content_key))
            if overlapping is not None:
                return jsonify({"error": f"Invalid queue item {number}: repeats or overlaps item {overlapping}", "success": False, "item": number}), 400
            claimed_paths[content_key] = number
            for parent_key in parent_keys:
                claimed_parents.setdefault(parent_key, number)
            validated_items.append((validated_path, validated_args))

        if not validated_items:
            return jsonify({"error": "No valid items provided", "success": False}), 400

        if len(validated_items) == 1 and data.get("return_single_path") is True:
            return jsonify({"success": True, "path": validated_items[0][0], "queued": False})

        content = "".join(shlex.join([path, *args]) + "\n" for path, args in validated_items)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        with file_path.open("x", encoding="utf-8", newline="\n") as f:
            f.write(content)
        key = os.path.normcase(os.path.realpath(file_path))
        evicted_key = None
        with active_processes_lock, _generated_queues_lock:
            # Bound abandoned queue registrations. Old files never become trusted
            # merely because their names have the webui_queue_ prefix.
            if len(paths_mod._generated_queues) >= MAX_UPLOAD_PATHS:
                # "path" follows the current queue item; the queue file itself is the execution path.
                active_queue_keys = {
                    os.path.normcase(os.path.realpath(str(process.get("execution_path") or process.get("path", "")))) for process in session_state_mod.active_processes.values()
                }
                evicted_key = next((entry for entry in paths_mod._generated_queues if entry not in active_queue_keys), None)
                if evicted_key is None:
                    file_path.unlink(missing_ok=True)
                    return jsonify({"success": False, "error": "All queue slots are active; try again after an upload finishes"}), 429
                paths_mod._generated_queues.pop(evicted_key)
            paths_mod._generated_queues[key] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if evicted_key is not None:
            try:
                _remove_generated_queue_file(evicted_key)
            except OSError as error:
                console.print(f"Could not remove expired WebUI queue: {error}", markup=False)
        _prune_stale_queue_logs()

        return jsonify({"success": True, "path": str(file_path), "queued": True})

    except Exception as e:
        console.print(f"Error saving queue: {e}", markup=False)
        console.print(traceback.format_exc(), markup=False)
        return jsonify({"error": "Error saving queue file", "success": False}), 500


def _release_reservation(session_id: str, process_state: dict[str, object] | None) -> None:
    """Drop a reservation that will not launch and let a scheduled upload use its slot."""
    if process_state is not None:
        with contextlib.suppress(Exception):
            _discard_session_state(session_id, process_state)
    with contextlib.suppress(Exception):
        _start_scheduled_sessions()


@bp.route("/api/execute", methods=["POST", "OPTIONS"])
@limiter.limit("100 per hour", key_func=_rate_limit_key_func)
def execute_command():
    """Execute upload.py with interactive terminal support"""

    if request.method == "OPTIONS":
        return "", 204

    # Require CSRF token for execute POST requests
    if request.method == "POST" and not security_mod._verify_csrf_header():
        return jsonify({"error": "CSRF token missing or invalid", "success": False}), 403

    # If caller used a bearer token, ensure it is valid
    bearer = security_mod._get_bearer_from_header()
    if bearer and not _token_is_valid(bearer):
        return jsonify({"error": "Forbidden (invalid token)", "success": False}), 403

    try:
        # Prefer a silent JSON parse to avoid Werkzeug raising on malformed
        # payloads. If parsing fails, try form data or a few tolerant
        # fallbacks to extract common fields (path, args, session_id).
        data = None
        try:
            data = _as_dict(request.get_json(silent=True)) or {}
        except Exception:
            data = None

        if not data:
            # Try standard form-encoded body first
            try:
                if request.form:
                    data = dict(request.form.items())
            except Exception:
                data = None

        if not data:
            # As a last resort attempt to parse raw body text that may be
            # produced by shells which strip quoting or backslashes. We
            # attempt a few conservative transforms rather than executing
            # arbitrary code: 1) normalize single quotes to double quotes,
            # 2) quote unquoted object keys, then try json.loads. If that
            # fails, fall back to simple regex extraction of `path` and
            # `session_id` values.
            try:
                raw = (request.get_data(as_text=True) or "").strip()
                if raw:
                    # Quick normalization: single -> double quotes
                    candidate = raw.replace("'", '"')
                    # Quote unquoted keys like: {path:...} -> {"path":...}
                    candidate = re.sub(r"([\{\s,])([A-Za-z0-9_]+)\s*:", r'\1"\2":', candidate)
                    try:
                        data = _json_load_dict(candidate)
                    except Exception:
                        # Regex extraction fallback for minimal fields
                        d: dict[str, str] = {}
                        m_path = re.search(r'path\s*[:=]\s*["\']?([^"\'\},]+)', raw)
                        m_sess = re.search(r'session_id\s*[:=]\s*["\']?([^"\'\},]+)', raw)
                        m_args = re.search(r'args\s*[:=]\s*["\']?([^"\'\}]+)', raw)
                        if m_path:
                            d["path"] = m_path.group(1)
                        if m_sess:
                            d["session_id"] = m_sess.group(1)
                        if m_args:
                            # Trim any trailing quote/comma characters and preserve spacing
                            raw_args = m_args.group(1).strip()
                            # Defensive: some shells or quoting can produce a
                            # concatenated fragment like `--debug,session_id:...`.
                            # Strip any trailing `,session_id` fragment or any
                            # comma followed by a session_id key so args remain
                            # clean.
                            raw_args = re.split(r',\s*(?:"?session_id|session_id)\b', raw_args)[0]
                            raw_args = raw_args.rstrip(",").strip().strip('"').strip("'")
                            d["args"] = raw_args
                        if d:
                            data = d
            except Exception:
                data = None

        if not data:
            return jsonify({"error": "No JSON data received", "success": False}), 400

        path = str(data.get("path", ""))
        args = str(data.get("args", ""))
        session_id = str(data.get("session_id", "default"))
        label = str(data.get("label", "")).strip()[:SESSION_LABEL_MAX_LENGTH]
        schedule_requested = data.get("schedule") is True
        console.print(f"Execute request - Path: {path}, Args: {args}, Session: {session_id}", markup=False)

        if not path:
            return jsonify({"error": "Missing path", "success": False}), 400

        def generate():
            handed_off = False
            validated_path: str = ""
            process_state: dict[str, object] | None = None
            try:
                # Build command to run upload.py directly
                validated_path = paths_mod._validate_execution_path(path)

                # Additional explicit assertion for static analysis: ensure the
                # resolved path is within allowed browse roots and contains no
                # invalid characters before using it in commands/subprocesses.
                try:
                    paths_mod._assert_safe_resolved_path(validated_path)
                except ValueError:
                    yield f"data: {json.dumps({'type': 'error', 'data': 'Invalid execution path'})}\n\n"
                    return

                base_dir = context_mod.STATE_DIR
                upload_script = str(context_mod.CODE_DIR / "upload.py")
                command = [sys.executable, "-u", upload_script, validated_path]

                # Add arguments if provided
                if args:
                    parsed_args = shlex.split(args)
                    try:
                        validated_args = paths_mod._validate_upload_assistant_args(parsed_args)
                    except ValueError as err:
                        console.print(f"Invalid execution arguments: {err}", markup=False)
                        yield f"data: {json.dumps({'type': 'error', 'data': 'Invalid execution arguments'})}\n\n"
                        return
                    command.extend(validated_args)

                item_paths = session_state_mod._execution_item_paths(validated_path)
                content_paths = frozenset(item_paths)
                keep_running, prompt_timeout = sessions_mod._webui_session_settings()
                process_state = _make_process_state(validated_path, args)
                process_state["content_paths"] = content_paths
                process_state["item_paths"] = item_paths
                process_state["execution_path"] = validated_path
                _init_session_events(
                    process_state,
                    label=label or Path(validated_path).name,
                    keep_running=keep_running,
                    prompt_timeout=prompt_timeout,
                )

                # Invalid requests must not terminate an existing session. The
                # conflict check and registration share one lock so concurrent
                # tabs cannot both pass the limit or claim the same content.
                with active_processes_lock:
                    conflict = _execution_conflict_locked(session_id, content_paths)
                    scheduled = False
                    if conflict is not None and conflict[0] == "capacity" and schedule_requested and keep_running:
                        waiting = sum(
                            1 for key, info in session_state_mod.active_processes.items() if key != session_id and info.get("scheduled") and _session_is_running(info)
                        )
                        if waiting < MAX_SCHEDULED_SESSIONS:
                            conflict, scheduled = None, True
                        else:
                            conflict = ("capacity", f"Maximum of {MAX_SCHEDULED_SESSIONS} scheduled uploads reached; wait for one to start")
                    existing = None
                    if conflict is None:
                        existing = session_state_mod.active_processes.pop(session_id, None)
                        _prune_finished_sessions_locked()
                        process_state["scheduled"] = scheduled
                        process_state["scheduled_at"] = time.time()
                        session_state_mod.active_processes[session_id] = process_state
                if conflict is not None:
                    yield _sse({"type": "error", "code": conflict[0], "data": conflict[1]})
                    return
                if existing:
                    proc = existing.get("process")
                    if proc and proc.poll() is None:
                        with contextlib.suppress(Exception):
                            processes_mod._terminate_process_tree(proc)
                    elif existing.get("scheduled"):
                        # A replaced scheduled upload never started: release its
                        # queue file (unless reused here) and end its listeners.
                        existing_path = str(existing.get("execution_path") or "")
                        if existing_path and os.path.normcase(os.path.realpath(existing_path)) != os.path.normcase(os.path.realpath(validated_path)):
                            sessions_mod._release_session_queue_file(existing_path, existing)
                        if "events_cond" in existing:
                            _finish_session(existing, None)

                command_str = subprocess.list2cmdline(command)
                console.print(f"Running: {command_str}", markup=False)

                _publish_session_event(process_state, {"type": "system", "data": f"Executing: {command_str}"})

                # Run the upload controller in an isolated subprocess so Kill can
                # terminate its external workers as one process tree. Subprocess
                # stdin supports the WebUI prompt flow.
                env = processes_mod._webui_subprocess_env()
                env[ROOTS_ENV] = json.dumps(paths_mod._get_browse_roots())
                env.pop(QUEUE_ENV, None)
                env.pop(QUEUE_HASH_ENV, None)
                if Path(validated_path).suffix.lower() == ".txt":
                    with _generated_queues_lock:
                        queue_hash = paths_mod._generated_queues.get(os.path.normcase(os.path.realpath(validated_path)))
                    if queue_hash is None:
                        _release_reservation(session_id, process_state)
                        yield _sse({"type": "error", "data": "WebUI queue expired; select the paths again"})
                        return
                    env[QUEUE_ENV] = validated_path
                    env[QUEUE_HASH_ENV] = queue_hash

                # Sanity-check the working directory used for the subprocess.
                # `base_dir` is computed from the application `__file__`, but
                # perform lightweight validation to satisfy static analysis
                # tools and ensure we do not pass uncontrolled input here.
                if "\x00" in str(base_dir) or not str(base_dir):
                    raise ValueError("Invalid execution directory")
                if not Path(str(base_dir)).is_absolute():
                    base_dir = str(Path(str(base_dir)).resolve())

                # Validate the constructed argv structure and the values that carry
                # security meaning. Shell punctuation is valid data when passed as
                # an argv value to a subprocess that does not invoke a shell.
                try:
                    if not isinstance(command, list) or not all(isinstance(arg, str) for arg in command):
                        raise ValueError("Invalid command structure")
                    if len(command) < 4 or command[0] != sys.executable or command[1] != "-u" or command[3] != validated_path:
                        raise ValueError("Invalid command structure")

                    paths_mod._assert_safe_resolved_path(validated_path)

                    expected_script = os.path.realpath(str(context_mod.CODE_DIR / "upload.py"))
                    script_real = os.path.realpath(command[2])
                    if script_real != expected_script:
                        raise ValueError("Invalid script path")
                except Exception as err:
                    console.print(f"Refusing to run unsafe command: {err}", markup=False)
                    _release_reservation(session_id, process_state)
                    yield _sse({"type": "error", "data": "Unsafe execution request"})
                    return

                process_state["launch"] = (command, Path(base_dir), env)
                if scheduled:
                    # The scheduler launches it, even with no browser open; the
                    # tab watches /api/sessions instead of holding a stream open.
                    handed_off = True
                    console.print(f"Scheduled upload session {session_id}", markup=False)
                    # Wake the scheduler first: the client may close the response
                    # at the yield, and this generator would never resume.
                    _start_scheduled_sessions()
                    yield _sse({"type": "scheduled"})
                    return

                _launch_session(session_id, process_state)
                # From here the pump thread owns the process and its cleanup; this
                # response only follows the session log and may disconnect freely.
                handed_off = True
                yield from _stream_session_events(session_id, process_state, 0)

            except Exception as e:
                console.print(f"Execution error for session {session_id}: {e}", markup=False)
                console.print(traceback.format_exc(), markup=False)
                if not handed_off:
                    # Release the reservation before yielding: the client may
                    # close the response there.
                    _release_reservation(session_id, process_state)
                    yield _sse({"type": "error", "data": "Execution error"})
            finally:
                # A refused request must not release a queue that another
                # session (for example the one it conflicted with) still uses.
                if not handed_off and validated_path:
                    sessions_mod._release_session_queue_file(validated_path, process_state)

        return Response(generate(), mimetype="text/event-stream")

    except Exception as e:
        console.print(f"Request error: {e}", markup=False)
        console.print(traceback.format_exc(), markup=False)
        return jsonify({"error": "Request error", "success": False}), 500


@bp.route("/api/input", methods=["POST"])
@limiter.limit("200 per hour", key_func=_rate_limit_key_func)
def send_input():
    """Send user input to running process"""
    try:
        data = _request_json_dict()
        session_id = str(data.get("session_id", "default"))
        user_input = str(data.get("input", ""))

        # Received input for session (logged at debug level previously) - keep minimal output

        # Authorization: allow either a valid bearer token (programmatic clients)
        # or an authenticated web session. Bearer tokens are validated by
        # `_token_is_valid` (valid token grants access).
        bearer = security_mod._get_bearer_from_header()
        if bearer:
            if not _token_is_valid(bearer):
                return jsonify({"error": "Forbidden (invalid token)", "success": False}), 403
        else:
            # Require a web session plus CSRF and same-origin checks for non-token callers
            if not security_mod._is_authenticated():
                return jsonify({"error": "Authentication required (web session)", "success": False}), 401
            if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
                return jsonify({"error": "CSRF/Origin validation failed", "success": False}), 403

        if session_id not in session_state_mod.active_processes:
            return jsonify({"error": "No active process", "success": False}), 404

        try:
            process_info = session_state_mod.active_processes[session_id]
            process = process_info.get("process")
            if process is None:
                return jsonify({"error": "No process found", "success": False}), 500

            if process.poll() is None:  # Process still running
                _set_process_awaiting_input(session_id, False)
                if "events_cond" in process_info:
                    with _session_condition(process_info):
                        process_info["last_input_at"] = time.time()
                _write_webui_process_input(process, user_input)
                console.print(f"Sent input for session {session_id}", markup=False)
            else:
                console.print(f"Process already terminated for session {session_id}", markup=False)
                return jsonify({"error": "Process not running", "success": False}), 400

        except Exception as e:
            console.print(f"Error handling input for session {session_id}: {e}", markup=False)
            console.print(traceback.format_exc(), markup=False)
            return jsonify({"error": "Failed to handle input", "success": False}), 500

        return jsonify({"success": True})

    except Exception as e:
        console.print(f"Input error: {e}", markup=False)
        console.print(traceback.format_exc(), markup=False)
        return jsonify({"error": "Input error", "success": False}), 500


@bp.route("/api/kill", methods=["POST"])
@limiter.limit("50 per hour", key_func=_rate_limit_key_func)
def kill_process():
    """Kill a running process"""
    try:
        data = _request_json_dict()
        session_id = str(data.get("session_id", ""))

        console.print(f"Kill request for session {session_id}", markup=False)

        # Authorization: allow either a valid bearer token or an authenticated web session
        bearer = security_mod._get_bearer_from_header()
        if bearer:
            if not _token_is_valid(bearer):
                return jsonify({"error": "Forbidden (invalid token)", "success": False}), 403
        else:
            if not security_mod._is_authenticated():
                return jsonify({"error": "Authentication required (web session)", "success": False}), 401
            if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
                return jsonify({"error": "CSRF/Origin validation failed", "success": False}), 403

        # One lookup, and the no-handle decision under the same lock that
        # _launch_session holds while it publishes the handle.
        with active_processes_lock:
            process_info = session_state_mod.active_processes.get(session_id)
            process = process_info.get("process") if process_info is not None else None
            if process_info is not None and process is None:
                # Kill can race with startup after the session has been registered
                # but before Popen returns. Removing this state makes the launcher
                # terminate the controller immediately if it does start. A scheduled
                # upload is cancelled the same way and its queue file is released.
                _discard_session_state_locked(session_id, process_info)
        if process_info is None:
            return jsonify({"error": "No active process", "success": False}), 404
        if process is None:
            if process_info.get("scheduled"):
                sessions_mod._release_session_queue_file(str(process_info.get("execution_path") or ""), process_info)
            return jsonify({"success": True, "message": "Execution startup cancelled"})

        terminated = False
        try:
            terminated = processes_mod._terminate_process_tree(process)

            processes_mod._close_webui_process_io(process)

        finally:
            # Keep the session available for another Kill attempt if the
            # process tree could not be terminated.
            # Attempt to join reader threads if present
            # Use the state this request killed: the session id can already
            # belong to a replacement upload.
            with contextlib.suppress(Exception):
                stdout_t = process_info.get("stdout_thread")
                stderr_t = process_info.get("stderr_thread")
                if isinstance(stdout_t, threading.Thread):
                    console.print(f"Joining stdout thread for session {session_id}", markup=False)
                    stdout_t.join(timeout=1)
                if isinstance(stderr_t, threading.Thread):
                    console.print(f"Joining stderr thread for session {session_id}", markup=False)
                    stderr_t.join(timeout=1)

            if terminated:
                with contextlib.suppress(Exception):
                    _discard_session_state(session_id, process_info)

        if not terminated:
            return jsonify({"error": "Failed to terminate process tree", "success": False}), 500

        console.print(f"Process killed for session {session_id}", markup=False)
        console.print(f"Post-kill snapshot: {_debug_process_snapshot(session_id)}", markup=False)
        return jsonify({"success": True, "message": "Process terminated"})

    except Exception as e:
        console.print(f"Kill error: {e}", markup=False)
        console.print(traceback.format_exc(), markup=False)
        return jsonify({"error": "Kill error", "success": False}), 500


@bp.route("/api/sessions")
@limiter.limit("3600 per hour", key_func=_rate_limit_key_func, override_defaults=True)
def list_sessions():
    """List running and recently finished uploads so a reopened page can restore its tabs."""
    with active_processes_lock:
        _prune_finished_sessions_locked()
        sessions = [(key, info) for key, info in session_state_mod.active_processes.items() if "events_cond" in info]
    summaries = sorted((_session_summary(key, info) for key, info in sessions), key=lambda item: float(cast(float, item.get("started_at") or 0)))
    keep_running, _prompt_timeout = sessions_mod._webui_session_settings()
    response = jsonify(
        {
            "success": True,
            "sessions": summaries,
            "max_running": MAX_CONCURRENT_SESSIONS,
            # Scheduled uploads start later without a browser, which only fits keep-running mode.
            "scheduling": keep_running,
        }
    )
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@bp.route("/api/session_stream")
@limiter.limit("3600 per hour", key_func=_rate_limit_key_func, override_defaults=True)
def session_stream():
    """Re-attach to an upload: replay its logged events after ``after`` and follow it live."""
    session_id = str(request.args.get("session_id", "")).strip()
    try:
        after = max(0, int(str(request.args.get("after", "0"))))
    except ValueError:
        return jsonify({"success": False, "error": "Invalid after"}), 400
    with active_processes_lock:
        process_state = session_state_mod.active_processes.get(session_id)
    if process_state is None or "events_cond" not in process_state:
        return jsonify({"success": False, "error": "Session not found"}), 404
    return Response(_stream_session_events(session_id, process_state, after), mimetype="text/event-stream", headers={"Cache-Control": "no-store"})


@bp.route("/api/session_dismiss", methods=["POST"])
@limiter.limit("600 per hour", key_func=_rate_limit_key_func)
def dismiss_session():
    """Forget a finished upload; running uploads must be killed instead."""
    bearer = security_mod._get_bearer_from_header()
    if bearer:
        if not _token_is_valid(bearer):
            return jsonify({"error": "Forbidden (invalid token)", "success": False}), 403
    elif not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"error": "CSRF/Origin validation failed", "success": False}), 403

    session_id = str(_request_json_dict().get("session_id", "")).strip()
    if not session_id:
        return jsonify({"error": "Missing session_id", "success": False}), 400
    with active_processes_lock:
        process_state = session_state_mod.active_processes.get(session_id)
        if process_state is None:
            return jsonify({"success": True})
        if _session_is_running(process_state):
            return jsonify({"error": "Session is still running", "success": False}), 409
        session_state_mod.active_processes.pop(session_id, None)
    return jsonify({"success": True})
