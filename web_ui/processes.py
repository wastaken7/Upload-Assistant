"""Upload subprocess spawning, I/O and structured stdout parsing."""

import contextlib
import importlib
import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, cast

import psutil

from src.webui_events import GUI_EVENT_KINDS, GUI_EVENT_NONCE_ENV, GUI_EVENT_STDOUT_PREFIX, GUI_EVENTS_ENV, MAX_EVENT_BYTES, event_prefix
from src.webui_progress import PROGRESS_STDOUT_PREFIX
from web_ui.context import console
from web_ui.flask_compat import _is_str_dict, _PopenGroupKwargs, _WebUIProcess

# ANSI color code regex pattern
ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


ProcessInfo = dict[str, Any]


class _ConPtyProcess:
    """Popen-compatible surface for a Windows ConPTY child."""

    def __init__(self, pty: Any) -> None:
        self._pty = pty
        self.pid = int(pty.pid)

    def poll(self) -> int | None:
        if self._pty.isalive():
            return None
        status = self._pty.exitstatus
        return int(status) if status is not None else 1

    def wait(self, timeout: float | None = None) -> int:
        timeout_value = timeout if timeout is not None else 0.0
        deadline = time.monotonic() + timeout if timeout is not None else None
        while self.poll() is None:
            if deadline is not None and time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(["ConPTY"], timeout_value)
            time.sleep(0.05)
        return self.poll() or 0

    def read(self, size: int = 1024) -> str:
        return str(self._pty.read(size))

    def write(self, text: str) -> None:
        self._pty.write(text)

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._pty.close()


def _spawn_webui_upload_process(command: list[str], base_dir: Path, env: dict[str, str]) -> tuple[_WebUIProcess, str]:
    """Start the upload controller, preferring a terminal on Windows for ANSI output."""
    if sys.platform == "win32":
        try:
            pty_process_class: Any = cast(Any, importlib.import_module("winpty")).PtyProcess

            pty = pty_process_class.spawn(command, cwd=str(base_dir), env=env, dimensions=(40, 120))
            return _ConPtyProcess(pty), "conpty"
        except ImportError:
            console.print("pywinpty is unavailable; falling back to pipe-based WebUI output.", markup=False)
        except Exception as err:
            console.print(f"ConPTY startup failed; falling back to pipe-based WebUI output: {err}", markup=False)

    popen_kwargs: _PopenGroupKwargs = {}
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    # codeql[py/command-line-injection]
    return (
        subprocess.Popen(  # lgtm[py/command-line-injection]  # noqa: S603
            command,
            shell=False,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=0,
            cwd=str(base_dir),
            env=env,
            universal_newlines=True,
            **popen_kwargs,
        ),
        "subprocess",
    )


def _write_webui_process_input(process: _WebUIProcess, user_input: str) -> None:
    if isinstance(process, _ConPtyProcess):
        process.write(f"{user_input}\r\n")
        return

    stdin = getattr(process, "stdin", None)
    if stdin is None:
        raise RuntimeError("Process stdin is unavailable")
    stdin.write(f"{user_input}\n")
    stdin.flush()


def _close_webui_process_io(process: _WebUIProcess) -> None:
    if isinstance(process, _ConPtyProcess):
        process.close()
        return

    for stream_name in ("stdin", "stdout", "stderr"):
        with contextlib.suppress(Exception):
            stream = getattr(process, stream_name, None)
            if stream is not None:
                stream.close()


def _terminate_process_tree(process: _WebUIProcess, timeout: float = 2.0) -> bool:
    """Terminate an upload controller and every child it has started."""
    if process.poll() is not None:
        return True
    # An upload controller is never PID 0/1; walking that tree would stop the whole system.
    if int(getattr(process, "pid", 0) or 0) <= 1:
        return False

    try:
        root = psutil.Process(process.pid)
    except psutil.NoSuchProcess, psutil.AccessDenied, OSError:
        return process.poll() is not None

    # Snapshot descendants before stopping the controller: once the controller
    # exits, its children may be re-parented and become impossible to identify.
    try:
        processes = root.children(recursive=True)
    except psutil.NoSuchProcess, psutil.AccessDenied, OSError:
        processes = []
    processes.append(root)

    for child in processes:
        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            child.terminate()

    _, alive = psutil.wait_procs(processes, timeout=timeout)
    for child in alive:
        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            child.kill()
    _, alive = psutil.wait_procs(alive, timeout=timeout)

    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=0)
    truly_alive = [p for p in alive if p.is_running() and p.status() != psutil.STATUS_ZOMBIE]
    return process.poll() is not None and not truly_alive


# Lines the child writes for the server rather than the terminal.
STRUCTURED_STDOUT_PREFIXES = (PROGRESS_STDOUT_PREFIX, GUI_EVENT_STDOUT_PREFIX)
# Secret part of the GUI event prefix, passed to every child. Text the child
# prints (e.g. release names from a tracker) cannot know it, so it cannot
# forge an event by printing the prefix itself.
_GUI_EVENT_NONCE = secrets.token_hex(16)


def _subprocess_prompt_type(buffer: str, previous_type: str | None = None) -> str | None:
    last_line = buffer.splitlines()[-1] if buffer else ""
    stripped = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", last_line).strip()
    if not stripped:
        return None
    if stripped.startswith(STRUCTURED_STDOUT_PREFIXES):
        return None
    if stripped == ">":
        return previous_type or "text"
    lowered = stripped.lower()
    if "running:" in lowered:
        return None
    if re.search(r"\(\s*y\s*/\s*n\s*\)\s*:?$", lowered):
        return "yes_no"
    if stripped.endswith(":") or stripped.endswith("?") or " enter " in f" {lowered} " or " select " in f" {lowered} " or lowered.startswith("select "):
        return "text"
    return None


def _webui_subprocess_env() -> dict[str, str]:
    """Return the environment required for an interactive colored WebUI child."""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    # Rich honors NO_COLOR even when force_terminal is enabled. The browser
    # consumes ANSI itself, so its child must not inherit that CLI preference.
    env.pop("NO_COLOR", None)
    env["UA_WEBUI_FORCE_COLOR"] = "1"
    env["UA_WEBUI_PROGRESS_STDOUT"] = "1"
    env["UA_WEBUI_PROMPT_SOUND_STDOUT"] = "1"
    env[GUI_EVENTS_ENV] = "1"
    # Lets the child skip terminal-only steps, e.g. opening a text editor;
    # descriptions are reviewed in the Web UI instead.
    env["UA_WEBUI_ACTIVE"] = "1"
    env[GUI_EVENT_NONCE_ENV] = _GUI_EVENT_NONCE
    env["UA_STATS_SOURCE"] = "webui"
    return env


def _subprocess_progress_event(chunk: str) -> dict[str, object] | None:
    payload = chunk.strip()
    if not payload.startswith(PROGRESS_STDOUT_PREFIX):
        return None
    try:
        event: object = json.loads(payload.removeprefix(PROGRESS_STDOUT_PREFIX))
    except json.JSONDecodeError:
        return None
    return event if _is_str_dict(event) else None


def _subprocess_gui_event(chunk: str) -> dict[str, object] | None:
    """Parse one GUI event line.

    Returns {} for a malformed, oversized or forged (wrong nonce) one, which is dropped.
    """
    payload = chunk.strip()
    if not payload.startswith(GUI_EVENT_STDOUT_PREFIX):
        return None
    prefix = event_prefix(_GUI_EVENT_NONCE)
    if not payload.startswith(prefix):
        return {}
    body = payload.removeprefix(prefix)
    if len(body) > MAX_EVENT_BYTES:
        return {}
    try:
        event: object = json.loads(body)
    except json.JSONDecodeError:
        return {}
    if not _is_str_dict(event) or event.get("kind") not in GUI_EVENT_KINDS:
        return {}
    return event


def _is_blank_output(chunk: str) -> bool:
    return not ANSI_ESCAPE.sub("", chunk).strip()


def _should_flush_subprocess_output(buffer: str, char: str, *, idle: bool = False) -> bool:
    if char == "\n" or (len(buffer) > 512 and not buffer.lstrip().startswith(STRUCTURED_STDOUT_PREFIXES)):
        return True
    # Wait for a pause in output before flushing unterminated prompts. Checking
    # each character would split ordinary lines at their first colon/question mark.
    if idle and not re.search(r"\x1b(?:\[[0-?]*[ -/]*)?$", buffer):
        return _subprocess_prompt_type(buffer) is not None
    return False


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text"""
    return ANSI_ESCAPE.sub("", text)
