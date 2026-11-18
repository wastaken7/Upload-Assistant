# ruff: noqa: S101
"""Races between queue advances, scheduling, kills and late subprocess output."""

import io
import json
import os
import queue
import threading
import time
from pathlib import Path

import pytest

import web_ui.context as webui_context
import web_ui.paths as webui_paths
import web_ui.preview as webui_preview
import web_ui.processes as webui_processes
import web_ui.security as webui_security
import web_ui.server as server
import web_ui.session_state as webui_session_state
import web_ui.sessions as webui_sessions


class FeedStream:
    def __init__(self) -> None:
        self._chars: queue.Queue[str] = queue.Queue()

    def feed(self, text: str) -> None:
        for char in text:
            self._chars.put(char)

    def end(self) -> None:
        self._chars.put("")

    def read(self, _size: int = 1) -> str:
        return self._chars.get()


class ExitedProcess:
    """A process that has already exited while its stdout is still being written."""

    pid = 1

    def __init__(self) -> None:
        self.stdin = io.StringIO()
        self.stdout = FeedStream()
        self.stderr = io.StringIO()
        self.returncode = 0

    def poll(self) -> int:
        return self.returncode

    def wait(self, _timeout: float | None = None) -> int:
        return self.returncode


@pytest.fixture
def isolated_sessions(monkeypatch):
    monkeypatch.setattr(webui_session_state, "active_processes", {})
    monkeypatch.setattr(webui_security, "_is_authenticated", lambda: True)
    monkeypatch.setattr(webui_security, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(webui_security, "_verify_same_origin", lambda: True)
    monkeypatch.setattr(webui_security, "_get_bearer_from_header", lambda: None)
    monkeypatch.setattr(webui_processes, "_close_webui_process_io", lambda _: None)
    return webui_session_state.active_processes


def _registered_state(session_id: str, path: str) -> dict[str, object]:
    state = webui_session_state._make_process_state(path, "")
    webui_sessions._init_session_events(state, label="Fictional Item", keep_running=True, prompt_timeout=0.0)
    webui_session_state.active_processes[session_id] = state
    return state


def _logged_html(state: dict[str, object]) -> str:
    with webui_sessions._session_condition(state):
        return "".join(payload for _seq, payload in webui_sessions._session_events(state))


def test_scheduler_skips_an_entry_whose_launch_is_not_stored_yet(isolated_sessions, monkeypatch):
    state = _registered_state("waiting", "/media/Fictional Item")
    state["scheduled"] = True
    state["scheduled_at"] = time.time()
    launched: list[str] = []
    monkeypatch.setattr(webui_sessions, "_launch_session", lambda session_id, _state: launched.append(session_id))

    webui_sessions._start_scheduled_sessions()
    assert launched == []
    assert state["scheduled"] is True

    state["launch"] = (["upload"], Path("/state"), {})
    webui_sessions._start_scheduled_sessions()
    assert launched == ["waiting"]


def test_kill_keeps_a_replacement_session_registered_under_the_same_id(isolated_sessions, monkeypatch):
    killed = _registered_state("tab", "/media/Fictional Item")
    killed["process"] = ExitedProcess()
    replacement = _registered_state("other", "/media/Another Item")

    def terminate_while_replaced(_process: object) -> bool:
        # Another execute request for the same tab replaces the state mid-kill.
        isolated_sessions["tab"] = replacement
        return True

    monkeypatch.setattr(webui_processes, "_terminate_process_tree", terminate_while_replaced)
    response = server.app.test_client().post("/api/kill", json={"session_id": "tab"})

    assert response.get_json()["success"] is True
    assert isolated_sessions["tab"] is replacement


def test_refused_execute_keeps_the_queue_of_the_session_it_conflicts_with(isolated_sessions, tmp_path, monkeypatch):
    item = tmp_path / "Fictional Item"
    item.mkdir()
    queue_file = tmp_path / "webui_queue_fictional.txt"
    queue_file.write_text(f'"{item}"\n', encoding="utf-8")
    key = os.path.normcase(os.path.realpath(queue_file))
    monkeypatch.setitem(webui_paths._generated_queues, key, "0123456789abcdef")
    monkeypatch.setattr(webui_context, "STATE_DIR", tmp_path)
    monkeypatch.setattr(webui_paths, "_validate_execution_path", lambda *_args, **_kwargs: str(queue_file))
    monkeypatch.setattr(webui_paths, "_assert_safe_resolved_path", lambda _: None)
    monkeypatch.setattr(webui_sessions, "_webui_session_settings", lambda: (True, 0.0))
    owner = _registered_state("owner", str(queue_file))
    owner["execution_path"] = str(queue_file)
    owner["content_paths"] = webui_session_state._execution_content_paths(str(queue_file))

    response = server.app.test_client().post("/api/execute", json={"path": str(queue_file), "session_id": "intruder"}, buffered=False)
    events = [json.loads(chunk.decode().removeprefix("data: ")) for chunk in response.response]

    assert events[0]["type"] == "error"
    assert queue_file.is_file()
    assert key in webui_paths._generated_queues
    assert "intruder" not in isolated_sessions


def test_preview_metadata_is_not_cached_for_a_target_that_moved_during_the_read(isolated_sessions, monkeypatch):
    state = _registered_state("tab", "/media/Fictional Item A")
    reads: list[str] = []

    def read(execution_path: str, _known_uuid: str):
        reads.append(execution_path)
        if len(reads) == 1:
            # The queue advances to item B while item A's files are read.
            webui_session_state.set_execution_preview_target("tab", str(state["run_token"]), "/media/Fictional Item B", "uuid-b")
            return Path("a/meta.json"), {"uuid": "uuid-a", "name": "A"}, "uuid-a"
        return Path("b/meta.json"), {"uuid": "uuid-b", "name": "B"}, "uuid-b"

    monkeypatch.setattr(webui_preview, "_read_preview_meta_for_target", read)
    execution_path, _meta_file, meta = webui_preview._resolve_execution_preview_meta("tab")

    assert reads == ["/media/Fictional Item A", "/media/Fictional Item B"]
    assert execution_path == "/media/Fictional Item B"
    assert meta is not None and meta["name"] == "B"
    assert state["meta_uuid"] == "uuid-b"


def test_pump_reads_output_written_after_the_process_exited(isolated_sessions):
    state = _registered_state("tab", "/media/Fictional Item")
    process = ExitedProcess()

    def write_late() -> None:
        time.sleep(0.3)
        process.stdout.feed("final summary line\n")
        process.stdout.end()

    threading.Thread(target=write_late, daemon=True).start()
    webui_sessions._pump_session("tab", state, process, "subprocess")

    assert "final summary line" in _logged_html(state)
    assert state["finished"] is True


def test_pump_stops_waiting_when_a_descendant_holds_the_pipe_open(isolated_sessions, monkeypatch):
    monkeypatch.setattr(webui_sessions, "READER_DRAIN_GRACE_SECONDS", 0.2)
    state = _registered_state("tab", "/media/Fictional Item")
    process = ExitedProcess()
    process.stdout.feed("before exit\n")

    started = time.monotonic()
    webui_sessions._pump_session("tab", state, process, "subprocess")

    assert time.monotonic() - started < 5
    assert "before exit" in _logged_html(state)
    assert state["finished"] is True
    process.stdout.end()
