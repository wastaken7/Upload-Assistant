# ruff: noqa: S101
import io
import json
import os
import queue
import threading
import time
from collections.abc import Callable, Iterator

import pytest

import web_ui.server as server


class FeedStream:
    """Blocking stdout whose content the test releases step by step."""

    def __init__(self) -> None:
        self._chars: queue.Queue[str] = queue.Queue()

    def feed(self, text: str) -> None:
        for char in text:
            self._chars.put(char)

    def end(self) -> None:
        self._chars.put("")

    def read(self, _size: int = 1) -> str:
        return self._chars.get()


class FakeProcess:
    pid = 1

    def __init__(self) -> None:
        self.stdin = io.StringIO()
        self.stdout = FeedStream()
        self.stderr = io.StringIO()
        self.returncode: int | None = None

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, _timeout: float | None = None) -> int | None:
        return self.returncode

    def exit(self, code: int) -> None:
        if self.returncode is None:
            self.returncode = code
            self.stdout.end()


def _wait_for(condition: Callable[[], bool], timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "condition not met in time"
        time.sleep(0.02)


def _events(response: object) -> Iterator[dict[str, object]]:
    for chunk in response.response:  # type: ignore[attr-defined]
        yield json.loads(chunk.decode().removeprefix("data: "))


def _read_until(events: Iterator[dict[str, object]], predicate: Callable[[dict[str, object]], bool], timeout: float = 10.0) -> list[dict[str, object]]:
    seen = []
    deadline = time.monotonic() + timeout
    for event in events:
        assert time.monotonic() < deadline, f"event not received; saw {seen}"
        seen.append(event)
        if predicate(event):
            return seen
    raise AssertionError(f"stream ended first; saw {seen}")


def _logged_html(session_id: str) -> str:
    state = server.active_processes[session_id]
    with server._session_condition(state):
        return "".join(payload for _seq, payload in server._session_events(state))


@pytest.fixture
def start_session(tmp_path, monkeypatch):
    """Start an execution backed by a FakeProcess with the given session settings."""
    monkeypatch.setattr(server, "active_processes", {})
    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_verify_same_origin", lambda: True)
    monkeypatch.setattr(server, "_get_bearer_from_header", lambda: None)
    monkeypatch.setattr(server, "_validate_execution_path", lambda *_args, **_kwargs: str(tmp_path / "Fictional Journey 2024"))
    monkeypatch.setattr(server, "_assert_safe_resolved_path", lambda _: None)
    monkeypatch.setattr(server, "_close_webui_process_io", lambda _: None)
    terminated: list[FakeProcess] = []

    def terminate(process: FakeProcess) -> bool:
        terminated.append(process)
        process.exit(-15)
        return True

    monkeypatch.setattr(server, "_terminate_process_tree", terminate)
    processes: list[FakeProcess] = []

    def start(session_id: str, *, keep_running: bool = True, prompt_timeout: float = 0.0):
        process = FakeProcess()
        processes.append(process)
        monkeypatch.setattr(server, "_webui_session_settings", lambda: (keep_running, prompt_timeout))
        monkeypatch.setattr(server, "_spawn_webui_upload_process", lambda *_args: (process, "subprocess"))
        response = server.app.test_client().post(
            "/api/execute",
            json={"path": "Fictional Journey 2024", "session_id": session_id, "label": "Fictional Journey 2024"},
            buffered=False,
        )
        assert response.status_code == 200
        return process, response, terminated

    yield start
    for process in processes:
        process.exit(0)
    # Session threads must finish before this test's patches are undone; a late
    # one would otherwise run against the next test's state.
    for thread in threading.enumerate():
        if thread.name.startswith("webui-session-"):
            thread.join(timeout=10)


def test_closed_tab_keeps_upload_running_and_reattach_replays_missed_output(start_session) -> None:
    process, response, terminated = start_session("keep-running")
    events = _events(response)
    _read_until(events, lambda event: event["type"] == "replay_done")
    process.stdout.feed("Fictional first line\n")
    first = _read_until(events, lambda event: event["type"] == "html" and "Fictional first line" in str(event["data"]))[-1]
    response.close()

    # The browser is gone, but the upload keeps producing output.
    process.stdout.feed("Fictional second line\n")
    _wait_for(lambda: "Fictional second line" in _logged_html("keep-running"))
    assert process.poll() is None
    assert terminated == []

    client = server.app.test_client()
    sessions = client.get("/api/sessions").get_json()["sessions"]
    assert [(item["session_id"], item["label"], item["running"]) for item in sessions] == [("keep-running", "Fictional Journey 2024", True)]

    resumed = client.get(f"/api/session_stream?session_id=keep-running&after={first['seq']}", buffered=False)
    resumed_events = _events(resumed)
    backlog = _read_until(resumed_events, lambda event: event["type"] == "replay_done")
    replayed = "".join(str(event.get("data", "")) for event in backlog)
    assert "Fictional second line" in replayed
    assert "Fictional first line" not in replayed

    process.exit(0)
    tail = _read_until(resumed_events, lambda event: event["type"] == "exit")
    assert tail[-1]["code"] == 0
    assert list(resumed_events) == [{"type": "finished", "exit_code": 0}]
    resumed.close()

    _wait_for(lambda: server.active_processes["keep-running"].get("finished") is True)
    finished = client.get("/api/sessions").get_json()["sessions"]
    assert [(item["running"], item["exit_code"]) for item in finished] == [(False, 0)]

    # A finished session no longer claims its content or capacity.
    with server.active_processes_lock:
        assert server._execution_conflict_locked("another-tab", frozenset(server.active_processes["keep-running"]["content_paths"])) is None

    assert client.post("/api/session_dismiss", json={"session_id": "keep-running"}).get_json() == {"success": True}
    assert "keep-running" not in server.active_processes


def test_closed_tab_kills_upload_when_keep_running_is_disabled(start_session) -> None:
    process, response, terminated = start_session("legacy", keep_running=False)
    events = _events(response)
    _read_until(events, lambda event: event["type"] == "replay_done")
    response.close()

    assert process in terminated
    assert "legacy" not in server.active_processes


def test_unanswered_prompt_is_killed_only_while_no_browser_is_attached(start_session) -> None:
    process, response, terminated = start_session("prompt-timeout", prompt_timeout=0.3)
    events = _events(response)
    process.stdout.feed("Continue? (y/N)")
    prompt = _read_until(events, lambda event: event["type"] == "prompt_state" and event["awaiting"] is True)[-1]
    assert prompt["input_type"] == "yes_no"

    # The open stream keeps the browser attached past the timeout; the prompt must survive.
    time.sleep(0.9)
    assert terminated == []

    response.close()
    _wait_for(lambda: process in terminated)
    assert "a prompt went unanswered" in _logged_html("prompt-timeout")


def test_running_sessions_cannot_be_dismissed(start_session) -> None:
    process, response, _terminated = start_session("still-running")
    _read_until(_events(response), lambda event: event["type"] == "replay_done")
    response.close()

    answer = server.app.test_client().post("/api/session_dismiss", json={"session_id": "still-running"})
    assert answer.status_code == 409
    assert "still-running" in server.active_processes
    process.exit(0)


def test_unknown_session_stream_is_not_found(monkeypatch) -> None:
    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    response = server.app.test_client().get("/api/session_stream?session_id=missing&after=0")
    assert response.status_code == 404


def test_only_recent_finished_sessions_are_kept(monkeypatch) -> None:
    def finished_state(finished_at: float) -> dict[str, object]:
        state = server._make_process_state("Fictional.mkv", "")
        server._init_session_events(state, label="Fictional", keep_running=True, prompt_timeout=0)
        server._finish_session(state, 0)
        state["finished_at"] = finished_at
        return state

    now = time.time()
    keep = server.MAX_RETAINED_FINISHED_SESSIONS
    sessions = {f"done-{index}": finished_state(now - index) for index in range(keep + 1)}
    sessions["expired"] = finished_state(now - server.FINISHED_SESSION_TTL_SECONDS - 1)
    sessions["running"] = {"content_paths": frozenset()}
    monkeypatch.setattr(server, "active_processes", sessions)

    with server.active_processes_lock:
        server._prune_finished_sessions_locked()

    # Expired and oldest finished sessions go; running ones are never pruned.
    assert sorted(server.active_processes) == sorted([*(f"done-{index}" for index in range(keep)), "running"])


def test_session_log_is_capped_and_reattach_reports_trimmed_output(monkeypatch) -> None:
    monkeypatch.setattr(server, "SESSION_EVENT_LOG_MAX_BYTES", 400)
    state = server._make_process_state("Fictional.mkv", "")
    server._init_session_events(state, label="Fictional", keep_running=True, prompt_timeout=0)
    for index in range(20):
        server._publish_session_event(state, {"type": "html", "data": f"Fictional line {index}"})
    server._finish_session(state, 0)

    assert state["events_bytes"] <= 400
    replay = [json.loads(chunk.removeprefix("data: ")) for chunk in server._stream_session_events("capped", state, 0)]
    assert replay[0] == {"type": "truncated"}
    assert replay[-3]["data"] == "Fictional line 19"
    assert replay[-2] == {"type": "replay_done"}
    assert replay[-1] == {"type": "finished", "exit_code": 0}


@pytest.mark.parametrize(
    ("meta_data", "expected"),
    [
        ({"category": "MOVIE", "title": "Fictional Journey", "year": 2024}, "Fictional Journey (2024)"),
        ({"category": "MOVIE", "title": "Fictional Journey", "year": 0}, "Fictional Journey"),
        ({"category": "TV", "title": "Fictional Voyage", "season": "S01", "episode": "E02", "tv_pack": 0}, "Fictional Voyage S01E02"),
        ({"category": "TV", "title": "Fictional Voyage", "season": "S01", "episode": "E02", "tv_pack": 1}, "Fictional Voyage S01"),
        ({"category": "MUSIC", "title": "Fictional Album", "artist": "Fictional Band"}, f"Fictional Band{server.SESSION_LABEL_SEPARATOR}Fictional Album"),
        ({"category": "BOOK", "title": "Fictional Novel", "author": "Fictional Writer"}, f"Fictional Writer{server.SESSION_LABEL_SEPARATOR}Fictional Novel"),
        ({"category": "GAME", "title": "Fictional Quest"}, "Fictional Quest"),
        ({"category": "MOVIE", "year": 2024}, ""),
    ],
)
def test_session_display_label(meta_data, expected) -> None:
    assert server._session_display_label(meta_data) == expected


def test_queue_tab_label_follows_the_current_item(start_session, tmp_path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    targets = [tmp_path / "Fictional.Journey.2024.mkv", tmp_path / "Fictional.Voyage.2023.mkv"]
    monkeypatch.setattr(server, "STATE_DIR", state_dir)
    monkeypatch.setattr(server, "_execution_item_paths", lambda _path: [os.path.normcase(os.path.realpath(target)) for target in targets])
    process, response, _terminated = start_session("labels")
    events = _events(response)

    def target_event(target, meta_uuid=None) -> str:
        event = {"op": "preview_target", "path": str(target)}
        if meta_uuid:
            event["meta_uuid"] = meta_uuid
        return server.PROGRESS_STDOUT_PREFIX + json.dumps(event) + "\n\n"

    def write_meta(meta_uuid: str, **meta: object) -> None:
        meta_dir = state_dir / "tmp" / meta_uuid
        meta_dir.mkdir(parents=True, exist_ok=True)
        (meta_dir / "meta.json").write_text(json.dumps({"uuid": meta_uuid, **meta}), encoding="utf-8")

    def next_label() -> dict[str, object]:
        return _read_until(events, lambda event: event["type"] == "label")[-1]

    # Before metadata exists the queue position and file name are shown.
    process.stdout.feed(target_event(targets[0]))
    assert next_label()["label"] == "[1/2] Fictional.Journey.2024.mkv"

    write_meta("journey", category="MOVIE", title="Fictional Journey", year=2024, name="Fictional.Journey.2024.1080p.WEB-DL")
    process.stdout.feed(target_event(targets[0], "journey"))
    label = next_label()
    assert (label["label"], label["detail"]) == ("[1/2] Fictional Journey (2024)", "Fictional.Journey.2024.1080p.WEB-DL")

    write_meta("voyage", category="TV", title="Fictional Voyage", season="S01", episode="E02", name="Fictional.Voyage.S01E02")
    process.stdout.feed(target_event(targets[1], "voyage"))
    assert next_label()["label"] == "[2/2] Fictional Voyage S01E02"

    sessions = server.app.test_client().get("/api/sessions").get_json()["sessions"]
    assert (sessions[0]["label"], sessions[0]["label_detail"]) == ("[2/2] Fictional Voyage S01E02", "Fictional.Voyage.S01E02")
    response.close()
    process.exit(0)


def _occupy_all_slots(tmp_path) -> dict[str, dict[str, object]]:
    return {f"busy-{index}": {"content_paths": frozenset({str(tmp_path / f"Fictional Busy {index}")})} for index in range(server.MAX_CONCURRENT_SESSIONS)}


def _post_execute(session_id: str, *, schedule: bool) -> list[dict[str, object]]:
    response = server.app.test_client().post(
        "/api/execute",
        json={"path": "Fictional Journey 2024", "session_id": session_id, "label": "Fictional Journey 2024", "schedule": schedule},
        buffered=False,
    )
    return list(_events(response))


def test_full_slots_schedule_the_upload_and_a_free_slot_starts_it(start_session, tmp_path, monkeypatch) -> None:
    start_session("warm-up")[0].exit(0)  # installs the session fixture patches
    busy = _occupy_all_slots(tmp_path)
    monkeypatch.setattr(server, "active_processes", dict(busy))
    process = FakeProcess()
    spawned: list[FakeProcess] = []

    def spawn(*_args):
        spawned.append(process)
        return process, "subprocess"

    monkeypatch.setattr(server, "_spawn_webui_upload_process", spawn)
    monkeypatch.setattr(server, "_webui_session_settings", lambda: (True, 0.0))

    assert _post_execute("scheduled", schedule=True) == [{"type": "scheduled"}]
    state = server.active_processes["scheduled"]
    assert state["scheduled"] is True
    assert spawned == []

    client = server.app.test_client()
    listed = client.get("/api/sessions").get_json()
    assert listed["scheduling"] is True
    assert [(item["session_id"], item["scheduled"], item["running"]) for item in listed["sessions"]] == [("scheduled", True, True)]

    # Scheduled content is claimed: a second upload of it is a duplicate.
    with server.active_processes_lock:
        assert server._execution_conflict_locked("other", state["content_paths"])[0] == "duplicate"

    with server.active_processes_lock:
        server.active_processes.pop("busy-0")
    server._start_scheduled_sessions()
    assert spawned == [process]
    assert state["scheduled"] is False
    assert '"started"' in _logged_html("scheduled")
    process.exit(0)


def test_upload_is_refused_instead_of_scheduled_when_not_requested_or_keep_running_is_off(start_session, tmp_path, monkeypatch) -> None:
    start_session("warm-up")[0].exit(0)
    monkeypatch.setattr(server, "active_processes", _occupy_all_slots(tmp_path))

    assert _post_execute("plain", schedule=False)[0]["code"] == "capacity"
    monkeypatch.setattr(server, "_webui_session_settings", lambda: (False, 0.0))
    assert _post_execute("legacy", schedule=True)[0]["code"] == "capacity"
    assert "plain" not in server.active_processes
    assert "legacy" not in server.active_processes


def test_killing_a_scheduled_upload_cancels_it(start_session, tmp_path, monkeypatch) -> None:
    start_session("warm-up")[0].exit(0)
    monkeypatch.setattr(server, "active_processes", _occupy_all_slots(tmp_path))
    monkeypatch.setattr(server, "_webui_session_settings", lambda: (True, 0.0))
    assert _post_execute("cancel-me", schedule=True) == [{"type": "scheduled"}]

    response = server.app.test_client().post("/api/kill", json={"session_id": "cancel-me"})
    assert response.get_json() == {"success": True, "message": "Execution startup cancelled"}
    assert "cancel-me" not in server.active_processes


def test_scheduling_queue_has_its_own_limit(start_session, tmp_path, monkeypatch) -> None:
    start_session("warm-up")[0].exit(0)
    sessions = _occupy_all_slots(tmp_path)
    for index in range(server.MAX_SCHEDULED_SESSIONS):
        sessions[f"waiting-{index}"] = {"content_paths": frozenset({str(tmp_path / f"Fictional Wait {index}")}), "scheduled": True}
    monkeypatch.setattr(server, "active_processes", sessions)
    monkeypatch.setattr(server, "_webui_session_settings", lambda: (True, 0.0))

    error = _post_execute("one-too-many", schedule=True)[0]
    assert (error["code"], error["data"]) == ("capacity", f"Maximum of {server.MAX_SCHEDULED_SESSIONS} scheduled uploads reached; wait for one to start")


def test_replacing_a_scheduled_session_releases_it(start_session, tmp_path, monkeypatch) -> None:
    start_session("warm-up")[0].exit(0)
    monkeypatch.setattr(server, "active_processes", _occupy_all_slots(tmp_path))
    monkeypatch.setattr(server, "_webui_session_settings", lambda: (True, 0.0))
    assert _post_execute("reused-id", schedule=True) == [{"type": "scheduled"}]
    replaced = server.active_processes["reused-id"]
    released: list[str] = []
    monkeypatch.setattr(server, "_remove_session_queue_file", released.append)
    monkeypatch.setattr(server, "_execution_item_paths", lambda _path: [str(tmp_path / "Fictional Other 2024")])
    monkeypatch.setattr(server, "_validate_execution_path", lambda *_args, **_kwargs: str(tmp_path / "Fictional Other 2024"))
    replaced["execution_path"] = str(tmp_path / "webui_queue_old.txt")

    assert _post_execute("reused-id", schedule=True) == [{"type": "scheduled"}]
    assert server.active_processes["reused-id"] is not replaced
    assert replaced["finished"] is True
    assert released == [str(tmp_path / "webui_queue_old.txt")]


def test_dismiss_requires_a_session_id(monkeypatch) -> None:
    monkeypatch.setattr(server, "_get_bearer_from_header", lambda: None)
    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_verify_same_origin", lambda: True)
    response = server.app.test_client().post("/api/session_dismiss", json={})
    assert response.status_code == 400


def test_session_settings_are_reparsed_only_when_a_config_changes(monkeypatch) -> None:
    calls: list[object] = []
    real_load = server._load_config_from_file

    def counting_load(path):
        calls.append(path)
        return real_load(path)

    monkeypatch.setattr(server, "_session_settings_cache", None)
    monkeypatch.setattr(server, "_load_config_from_file", counting_load)
    first = server._webui_session_settings()
    assert server._webui_session_settings() == first
    assert len(calls) == 2  # user and example config, parsed once
