# ruff: noqa: S101
"""Races between queue advances, scheduling, kills and late subprocess output."""

import hashlib
import io
import json
import os
import queue
import threading
import time
import types
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


def test_launch_stops_the_controller_when_the_pump_cannot_start(isolated_sessions, monkeypatch):
    state = _registered_state("tab", "/media/Fictional Item")
    state["launch"] = (["upload"], Path("/state"), {})
    process = ExitedProcess()
    terminated: list[object] = []

    class FailingThread:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def start(self) -> None:
            raise RuntimeError("can't start new thread")

    monkeypatch.setattr(webui_processes, "_spawn_webui_upload_process", lambda *_args: (process, "subprocess"))
    monkeypatch.setattr(webui_processes, "_terminate_process_tree", lambda proc: terminated.append(proc) or True)
    monkeypatch.setattr(webui_sessions, "threading", types.SimpleNamespace(Thread=FailingThread))

    with pytest.raises(RuntimeError):
        webui_sessions._launch_session("tab", state)
    assert terminated == [process]


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
    # A real generated queue: inside STATE_DIR/tmp and registered by its digest,
    # so the cleanup would delete it if it wrongly released the queue.
    (tmp_path / "tmp").mkdir()
    queue_file = tmp_path / "tmp" / "webui_queue_fictional.txt"
    queue_file.write_text(f'"{item}"\n', encoding="utf-8")
    key = os.path.normcase(os.path.realpath(queue_file))
    monkeypatch.setitem(webui_paths._generated_queues, key, hashlib.sha256(queue_file.read_bytes()).hexdigest())
    monkeypatch.setattr(webui_context, "STATE_DIR", tmp_path)
    monkeypatch.setattr(webui_paths, "_validate_execution_path", lambda *_args, **_kwargs: str(queue_file))
    monkeypatch.setattr(webui_paths, "_assert_safe_resolved_path", lambda _: None)
    monkeypatch.setattr(webui_sessions, "_webui_session_settings", lambda: (True, 0.0))
    owner = _registered_state("owner", str(queue_file))
    owner["execution_path"] = str(queue_file)
    owner["content_paths"] = webui_session_state._execution_content_paths(str(queue_file))

    response = server.app.test_client().post("/api/execute", json={"path": str(queue_file), "session_id": "intruder"}, buffered=False)
    events = [json.loads(chunk.decode().removeprefix("data: ")) for chunk in response.response]

    assert (events[0]["type"], events[0]["code"]) == ("error", "duplicate")
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


def test_preview_reports_nothing_when_the_target_keeps_moving(isolated_sessions, monkeypatch):
    state = _registered_state("tab", "/media/Fictional Item 0")
    reads: list[str] = []

    def read(execution_path: str, _known_uuid: str):
        reads.append(execution_path)
        webui_session_state.set_execution_preview_target("tab", str(state["run_token"]), f"/media/Fictional Item {len(reads)}", None)
        return Path("meta.json"), {"name": execution_path}, ""

    monkeypatch.setattr(webui_preview, "_read_preview_meta_for_target", read)

    assert webui_preview._resolve_execution_preview_meta("tab") == ("", None, None)


def test_alias_metadata_of_another_release_is_not_used(tmp_path, monkeypatch):
    monkeypatch.setattr(webui_context, "STATE_DIR", tmp_path)
    alias_dir = tmp_path / "tmp" / "Fictional Item"
    alias_dir.mkdir(parents=True)
    (alias_dir / "meta.json").write_text(json.dumps({"uuid": "older-uuid"}), encoding="utf-8")

    # The published UUID's own metadata is not written yet.
    assert webui_preview._read_preview_meta_for_target("/media/Fictional Item", "published-uuid") == (None, None, "")

    # The alias is still used when it belongs to the published release.
    _meta_file, meta, uuid_to_cache = webui_preview._read_preview_meta_for_target("/media/Fictional Item", "older-uuid")
    assert meta is not None and meta["uuid"] == "older-uuid"
    assert uuid_to_cache == "older-uuid"


def test_metadata_written_by_another_item_with_the_same_basename_is_not_used(tmp_path, monkeypatch):
    monkeypatch.setattr(webui_context, "STATE_DIR", tmp_path)
    release_dir = tmp_path / "tmp" / "Fictional Item"
    release_dir.mkdir(parents=True)
    first, second = tmp_path / "first" / "Fictional Item", tmp_path / "second" / "Fictional Item"
    (release_dir / "meta.json").write_text(json.dumps({"uuid": "Fictional Item", "path": str(first)}), encoding="utf-8")

    assert webui_preview._read_preview_meta_for_target(str(second), "Fictional Item") == (None, None, "")
    assert webui_preview._read_preview_meta_for_target(str(second), "") == (None, None, "")
    _meta_file, meta, _uuid = webui_preview._read_preview_meta_for_target(str(first), "Fictional Item")
    assert meta is not None and meta["path"] == str(first)


def test_preview_status_comes_from_the_validated_target(isolated_sessions, monkeypatch):
    state = _registered_state("tab", "/media/Fictional Item A")
    state.update(awaiting_input=True, input_type="confirm", progress={"step": {"id": "step", "status": "running"}})
    monkeypatch.setattr(webui_preview, "_read_preview_meta_for_target", lambda _path, _uuid: (Path("meta.json"), {"uuid": "uuid-a"}, "uuid-a"))

    assert webui_preview._resolve_execution_preview_target("tab")[3] == {}
    _path, _meta_file, _meta, status = webui_preview._resolve_execution_preview_target("tab", with_status=True)
    # The live state moves on; the snapshot must not follow it.
    state.update(awaiting_input=False, input_type=None)
    state["progress"]["step"]["status"] = "done"

    assert status == {"awaiting_input": True, "input_type": "confirm", "progress": [{"id": "step", "status": "running"}]}


def _pump_with_timeout(state: dict[str, object], process: "ExitedProcess", timeout: float = 5.0) -> None:
    """Run the pump in a worker so a regression fails the test instead of hanging it."""
    worker = threading.Thread(target=webui_sessions._pump_session, args=("tab", state, process, "subprocess"), daemon=True)
    worker.start()
    try:
        worker.join(timeout)
        assert not worker.is_alive(), "pump did not return"
    finally:
        process.stdout.end()
        worker.join(1)


def test_pump_reads_output_written_after_the_process_exited(isolated_sessions):
    state = _registered_state("tab", "/media/Fictional Item")
    process = ExitedProcess()

    def write_late() -> None:
        time.sleep(0.3)
        process.stdout.feed("final summary line\n")
        process.stdout.end()

    threading.Thread(target=write_late, daemon=True).start()
    _pump_with_timeout(state, process)

    assert "final summary line" in _logged_html(state)
    assert state["finished"] is True
    assert state["exit_code"] == process.returncode


def test_pump_stops_waiting_when_a_descendant_holds_the_pipe_open(isolated_sessions, monkeypatch):
    monkeypatch.setattr(webui_sessions, "READER_DRAIN_GRACE_SECONDS", 0.2)
    state = _registered_state("tab", "/media/Fictional Item")
    process = ExitedProcess()
    process.stdout.feed("before exit\n")

    _pump_with_timeout(state, process)

    assert "before exit" in _logged_html(state)
    assert state["finished"] is True
    assert state["exit_code"] == process.returncode


class _SteppingClock:
    """The real time module, except that monotonic() advances one second per call once output is accepted."""

    def __init__(self, ready: threading.Event) -> None:
        self._now = 0.0
        self._ready = ready

    def monotonic(self) -> float:
        self._ready.wait(5)
        self._now += 1.0
        return self._now

    def __getattr__(self, name: str) -> object:
        return getattr(time, name)


class _ObservedThreading:
    """The real threading module, whose Lock reports the pump's output-gate hand-offs."""

    def __init__(self, accepted_chars: int) -> None:
        self.before_cutoff_accepted = threading.Event()
        self.cutoff = threading.Event()
        self._remaining = accepted_chars
        outer = self

        class GateLock:
            def __init__(self) -> None:
                self._lock = threading.Lock()

            def __enter__(self) -> None:
                self._lock.acquire()

            def __exit__(self, *_exc: object) -> None:
                if "read_" in threading.current_thread().name:
                    outer._remaining -= 1
                    if outer._remaining == 0:
                        outer.before_cutoff_accepted.set()
                else:
                    # Only the pump thread takes the gate to close it.
                    outer.cutoff.set()
                self._lock.release()

        self.Lock = GateLock

    def __getattr__(self, name: str) -> object:
        return getattr(threading, name)


def test_pump_closes_reader_output_at_the_drain_deadline(isolated_sessions, monkeypatch):
    before, after = "accepted before cutoff\n", "written after cutoff\n"
    observed = _ObservedThreading(len(before))
    # The deadline passes only once every character of the first marker was
    # accepted; the second marker is written only after the pump closed the gate.
    monkeypatch.setattr(webui_sessions, "threading", observed)
    monkeypatch.setattr(webui_sessions, "time", _SteppingClock(observed.before_cutoff_accepted))
    monkeypatch.setattr(webui_sessions, "READER_DRAIN_GRACE_SECONDS", 0.5)
    state = _registered_state("tab", "/media/Fictional Item")
    process = ExitedProcess()
    process.stdout.feed(before)

    def write_after_cutoff() -> None:
        if observed.cutoff.wait(5):
            process.stdout.feed(after)

    threading.Thread(target=write_after_cutoff, daemon=True).start()
    # The pipe never reaches EOF while the pump runs.
    _pump_with_timeout(state, process)

    logged = _logged_html(state)
    assert "accepted before cutoff" in logged
    assert "written after cutoff" not in logged
    assert "output_queue" not in state
    assert state["finished"] is True
    assert state["exit_code"] == process.returncode


def test_pump_does_not_report_a_prompt_timeout_after_the_process_exited(isolated_sessions, monkeypatch):
    monkeypatch.setattr(webui_sessions, "READER_DRAIN_GRACE_SECONDS", 0.2)
    state = _registered_state("tab", "/media/Fictional Item")
    state.update(prompt_timeout=0.01, awaiting_input=True, awaiting_since=0.0, detached_at=0.0, last_input_at=0.0)
    process = ExitedProcess()

    _pump_with_timeout(state, process)

    assert "went unanswered" not in _logged_html(state)
    assert state["finished"] is True
    assert state["exit_code"] == process.returncode


def test_queue_release_keeps_a_queue_a_replacement_registered(isolated_sessions, tmp_path, monkeypatch):
    monkeypatch.setattr(webui_context, "STATE_DIR", tmp_path)
    (tmp_path / "tmp").mkdir()
    queue_file = tmp_path / "tmp" / "webui_queue_fictional.txt"
    queue_file.write_text('"/media/Fictional Item"\n', encoding="utf-8")
    key = os.path.normcase(os.path.realpath(queue_file))
    monkeypatch.setitem(webui_paths._generated_queues, key, hashlib.sha256(queue_file.read_bytes()).hexdigest())
    retiring = _registered_state("tab", str(queue_file))
    retiring["execution_path"] = str(queue_file)
    # The same tab already runs the queue again when the old pump cleans up.
    replacement = _registered_state("tab", str(queue_file))
    replacement["execution_path"] = str(queue_file)

    webui_sessions._release_session_queue_file(str(queue_file), retiring)
    assert key in webui_paths._generated_queues
    assert queue_file.is_file()

    webui_session_state._discard_session_state("tab", replacement)
    webui_sessions._release_session_queue_file(str(queue_file), retiring)
    assert key not in webui_paths._generated_queues
    assert not queue_file.exists()


def test_queue_release_keeps_logs_another_file_with_the_same_content_uses(isolated_sessions, tmp_path, monkeypatch):
    monkeypatch.setattr(webui_context, "STATE_DIR", tmp_path)
    tmp_dir = tmp_path / "tmp"
    tmp_dir.mkdir()
    content = '"/media/Fictional Item"\n'
    queue_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    running_file, unused_file = tmp_dir / "webui_queue_running.txt", tmp_dir / "webui_queue_unused.txt"
    for path in (running_file, unused_file):
        path.write_text(content, encoding="utf-8")
        monkeypatch.setitem(webui_paths._generated_queues, os.path.normcase(os.path.realpath(path)), queue_hash)
    queue_log = tmp_dir / f"{webui_paths.generated_queue_name(queue_hash)}_queue.log"
    queue_log.write_text("[]", encoding="utf-8")
    running = _registered_state("running", str(running_file))
    running["execution_path"] = str(running_file)

    # A second tab's refused request releases the unused file only.
    webui_sessions._release_session_queue_file(str(unused_file), None)

    assert not unused_file.exists()
    assert running_file.is_file()
    assert queue_log.is_file()
