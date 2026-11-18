# ruff: noqa: S101
import io
import json
import os
import queue
import subprocess
import sys
import threading
import time

import pytest

import web_ui.context as webui_context
import web_ui.paths as webui_paths
import web_ui.preview as webui_preview
import web_ui.processes as webui_processes
import web_ui.security as webui_security
import web_ui.server as server
import web_ui.session_state as webui_session_state
import web_ui.sessions as webui_sessions


def test_upload_child_publishes_preview_without_in_process_session() -> None:
    result = subprocess.run(
        [sys.executable, "-u", "-c", "import upload; upload._publish_webui_preview_target('Fictional Journey.mkv', 'fictional-release')"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=webui_processes._webui_subprocess_env(),
        timeout=30,
        check=True,
    )
    events = [webui_processes._subprocess_progress_event(line) for line in result.stdout.splitlines()]
    assert {"op": "preview_target", "path": "Fictional Journey.mkv", "meta_uuid": "fictional-release"} in events


class FeedStream:
    """Blocking stdout whose content the test releases step by step."""

    def __init__(self) -> None:
        self._chars: queue.Queue[str] = queue.Queue()

    def feed(self, text: str) -> None:
        for char in text:
            self._chars.put(char)

    def read(self, _size: int = 1) -> str:
        return self._chars.get()


def _wait_for(condition, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "condition not met in time"
        time.sleep(0.02)


def test_queue_preview_follows_child_targets(tmp_path, monkeypatch) -> None:
    targets = [tmp_path / "Fictional Journey.mkv", tmp_path / ("a" * 200) / ("b" * 200) / "Fictional Finale.mkv"]
    queue_path = tmp_path / "webui_queue_fictional.txt"
    queue_path.write_text("\n".join(str(target) for target in targets), encoding="utf-8")
    state_dir = tmp_path / "state"
    for index, target in enumerate(targets):
        meta_uuid = f"fictional-release-{index}"
        meta_dir = state_dir / "tmp" / meta_uuid
        meta_dir.mkdir(parents=True)
        (meta_dir / "meta.json").write_text(
            json.dumps({"uuid": meta_uuid, "path": str(target), "title": target.stem, "poster": f"https://example.invalid/poster-{index}.jpg"}), encoding="utf-8"
        )

    def preview_target(target, meta_uuid=None) -> str:
        event = {"op": "preview_target", "path": str(target)}
        if meta_uuid:
            event["meta_uuid"] = meta_uuid
        return webui_processes.PROGRESS_STDOUT_PREFIX + json.dumps(event) + "\n\n"

    class WaitingProcess:
        stdin = io.StringIO()
        stdout = FeedStream()
        stderr = io.StringIO()

        def poll(self):
            return None

    process = WaitingProcess()
    session_id = "queue-preview-test"
    monkeypatch.setattr(webui_context, "STATE_DIR", state_dir)
    monkeypatch.setattr(webui_security, "_is_authenticated", lambda: True)
    monkeypatch.setattr(webui_security, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(webui_paths, "_validate_execution_path", lambda *_args, **_kwargs: str(queue_path))
    monkeypatch.setattr(webui_paths, "_generated_queues", {os.path.normcase(os.path.realpath(queue_path)): "fictional-hash"})
    monkeypatch.setattr(webui_paths, "_assert_safe_resolved_path", lambda _: None)
    monkeypatch.setattr(webui_paths, "_validate_upload_assistant_args", lambda args: args)
    monkeypatch.setattr(webui_processes, "_spawn_webui_upload_process", lambda *_args: (process, "subprocess"))
    monkeypatch.setattr(webui_processes, "_terminate_process_tree", lambda _: True)
    response = server.app.test_client().post("/api/execute", json={"path": str(queue_path), "session_id": session_id}, buffered=False)
    try:
        next(response.response)
        state = webui_session_state.active_processes[session_id]
        process.stdout.feed("Continue? (y/N)\n")
        _wait_for(lambda: state["awaiting_input"] is True)
        for index, target in enumerate(targets):
            meta_uuid = f"fictional-release-{index}"
            # A new target without its UUID yet clears the previous item's preview.
            process.stdout.feed(preview_target(target, meta_uuid) + preview_target(target))
            _wait_for(lambda target=target: state["path"] == str(target) and "meta_uuid" not in state)
            assert webui_preview._find_execution_preview(session_id)["status"] == "waiting"

            # Re-publish the UUID as metadata becomes available for the same item.
            process.stdout.feed(preview_target(target, meta_uuid))
            _wait_for(lambda meta_uuid=meta_uuid: state.get("meta_uuid") == meta_uuid)
            preview = webui_preview._find_execution_preview(session_id)
            assert preview["status"] == "ready"
            assert preview["path"] == str(target)
            assert preview["title"] == target.stem
            assert preview["poster_url"].startswith("https://example.invalid/poster-")
            assert preview["awaiting_input"] is True

        with webui_sessions._session_condition(state):
            logged = "".join(payload for _seq, payload in webui_sessions._session_events(state))
        assert "preview_target" not in logged
    finally:
        response.close()
        webui_session_state.active_processes.pop(session_id, None)


def test_replaced_execution_cannot_change_preview(monkeypatch) -> None:
    state = webui_session_state._make_process_state("Fictional Finale.mkv", "")
    monkeypatch.setattr(webui_session_state, "active_processes", {"preview-session": state})
    webui_session_state.set_execution_preview_target("preview-session", "old-run-token", "Fictional Journey.mkv", "old-release")
    assert state["path"] == "Fictional Finale.mkv"
    assert "meta_uuid" not in state


@pytest.mark.parametrize(
    "output, expected_type",
    [("Status: gathering metadata\n", None), ("Upload? checking eligibility\n", None), ("Enter a title: ", "text"), ("> ", "text"), ("Continue? (y/N)", "yes_no")],
)
def test_prompt_state_changes_only_when_output_flushes(output, expected_type, tmp_path, monkeypatch) -> None:
    """Keep partial log lines inactive and publish real prompts on the idle path."""

    class WaitingProcess:
        stdin = io.StringIO()
        stdout = io.StringIO(output)
        stderr = io.StringIO()

        def poll(self):
            return None

    process = WaitingProcess()
    session_id = "flush-state-test"
    monkeypatch.setattr(webui_security, "_is_authenticated", lambda: True)
    monkeypatch.setattr(webui_security, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(webui_paths, "_validate_execution_path", lambda *_args, **_kwargs: str(tmp_path))
    monkeypatch.setattr(webui_paths, "_assert_safe_resolved_path", lambda _: None)
    monkeypatch.setattr(webui_paths, "_validate_upload_assistant_args", lambda args: args)
    monkeypatch.setattr(webui_processes, "_spawn_webui_upload_process", lambda *_args: (process, "subprocess"))
    monkeypatch.setattr(webui_processes, "_terminate_process_tree", lambda _process: True)
    original_flush = webui_processes._should_flush_subprocess_output
    states_before_flush = []
    flushed = threading.Event()

    def observe_flush(buffer, char, *, idle=False):
        # The session thread keeps polling after the flush; only earlier states matter.
        if not flushed.is_set():
            states_before_flush.append(webui_session_state.active_processes[session_id]["awaiting_input"])
        should_flush = original_flush(buffer, char, idle=idle)
        if should_flush:
            flushed.set()
        return should_flush

    monkeypatch.setattr(webui_processes, "_should_flush_subprocess_output", observe_flush)
    response = server.app.test_client().post("/api/execute", json={"path": str(tmp_path), "session_id": session_id}, buffered=False)
    try:
        assert response.status_code == 200
        deadline = time.monotonic() + 5
        for chunk in response.response:
            assert time.monotonic() < deadline, "Output never reached the browser"
            event = json.loads(chunk.decode().removeprefix("data: "))
            if event["type"] == "html":
                break
        else:
            pytest.fail("No HTML output received")
        assert states_before_flush and not any(states_before_flush)
        state = webui_session_state.active_processes[session_id]
        assert state["awaiting_input"] is (expected_type is not None)
        if expected_type is not None:
            assert state["input_type"] == expected_type
    finally:
        response.close()
        webui_session_state.active_processes.pop(session_id, None)


def test_subprocess_yes_no_prompt_is_classified_for_dedicated_buttons() -> None:
    assert webui_processes._subprocess_prompt_type(":: Continue? (y/N)\n") == "yes_no"
    assert webui_processes._subprocess_prompt_type("\x1b[1;31mContinue? (Y/n)\x1b[0m") == "yes_no"
    assert webui_processes._subprocess_prompt_type("Enter a new title:") == "text"
    assert webui_processes._subprocess_prompt_type(webui_processes.PROGRESS_STDOUT_PREFIX + '{"detail":"Please select a stream"}') is None
    assert webui_processes._subprocess_prompt_type("\x1b[32m> \x1b[0m", "yes_no") == "yes_no"
    assert webui_processes._subprocess_prompt_type("> ") == "text"


@pytest.mark.parametrize(
    "background_output, expected_type",
    [
        ("\n", "yes_no"),
        ("\x1b[0m\n", "yes_no"),
        ("\n" + webui_processes.PROGRESS_STDOUT_PREFIX + '{"op":"upsert","id":"scan","label":"Scanning","current":25,"total":100}\n', "yes_no"),
        ("\n" + webui_processes.PROGRESS_STDOUT_PREFIX + '{"op":"reset"}\n', "yes_no"),
        (webui_processes.PROGRESS_STDOUT_PREFIX + '{"op":"reset"}\n', "yes_no"),
        (webui_sessions.PROMPT_SOUND_STDOUT_MARKER + "\n", "yes_no"),
        ("Gathering metadata\n", None),
        ("Enter a title:\n", "text"),
    ],
)
def test_background_progress_preserves_yes_no_prompt(tmp_path, monkeypatch, background_output, expected_type) -> None:
    class WaitingProcess:
        stdin = io.StringIO()
        stdout = io.StringIO("Continue? (y/N)\n" + background_output + "> ")
        stderr = io.StringIO()

        def poll(self):
            return None

    process = WaitingProcess()
    session_id = "background-progress-prompt-test"
    monkeypatch.setattr(webui_security, "_is_authenticated", lambda: True)
    monkeypatch.setattr(webui_security, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(webui_security, "_verify_same_origin", lambda: True)
    monkeypatch.setattr(webui_paths, "_validate_execution_path", lambda *_args, **_kwargs: str(tmp_path))
    monkeypatch.setattr(webui_paths, "_assert_safe_resolved_path", lambda _: None)
    monkeypatch.setattr(webui_paths, "_validate_upload_assistant_args", lambda args: args)
    monkeypatch.setattr(webui_processes, "_spawn_webui_upload_process", lambda *_args: (process, "subprocess"))
    monkeypatch.setattr(webui_processes, "_terminate_process_tree", lambda _process: True)
    client = server.app.test_client()
    response = client.post("/api/execute", json={"path": str(tmp_path), "session_id": session_id}, buffered=False)
    try:
        assert response.status_code == 200
        deadline = time.monotonic() + 5
        first_output = True
        # The browser learns the prompt state from prompt_state events, which
        # precede the output that caused them.
        streamed_type = None
        for chunk in response.response:
            assert time.monotonic() < deadline, "Input marker never reached the browser"
            event = json.loads(chunk.decode().removeprefix("data: "))
            if event["type"] == "prompt_state":
                streamed_type = event["input_type"] if event["awaiting"] else None
                continue
            if event["type"] not in {"html", "progress"}:
                continue
            marker_seen = event["type"] == "html" and "&gt;" in event["data"]
            current_type = "yes_no" if first_output else (expected_type or "text") if marker_seen else expected_type
            assert streamed_type == current_type
            first_output = False
            if marker_seen:
                break
        else:
            pytest.fail("No input marker received")

        state = webui_session_state.active_processes[session_id]
        assert state["awaiting_input"] is (current_type is not None)
        assert state["input_type"] == current_type
        preview = webui_preview._find_execution_preview(session_id)
        assert preview["awaiting_input"] is (current_type is not None)
        assert preview["input_type"] == current_type

        answer = client.post("/api/input", json={"session_id": session_id, "input": "yes"})
        assert answer.status_code == 200
        assert process.stdin.getvalue() == "yes\n"
        assert state["awaiting_input"] is False
        assert state["input_type"] is None
    finally:
        response.close()
        webui_session_state.active_processes.pop(session_id, None)


@pytest.mark.parametrize("prompt", ["> ", "\x1b[32m> \x1b[0m", "Enter a title: ", "Continue? (y/N)"])
def test_unterminated_prompts_flush_after_output_becomes_idle(prompt) -> None:
    assert not webui_processes._should_flush_subprocess_output(prompt, prompt[-1])
    assert webui_processes._should_flush_subprocess_output(prompt, "", idle=True)


@pytest.mark.parametrize("buffer", ["", "Ordinary output", "Enter title:\x1b[", "Enter title:\x1b[31", webui_processes.PROGRESS_STDOUT_PREFIX + '{"detail":"Enter a title:"'])
def test_idle_flush_keeps_incomplete_ansi_and_progress_records(buffer) -> None:
    assert not webui_processes._should_flush_subprocess_output(buffer, "", idle=True)


def test_browser_receives_cli_ui_marker_before_answering(tmp_path, monkeypatch) -> None:
    command = [sys.executable, "-u", "-c", "import src.console; import cli_ui; answer = cli_ui.ask_yes_no('Continue?', default=False); print(f'ANSWER={answer}', flush=True)"]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=webui_processes._webui_subprocess_env())  # noqa: S603 - fixed Python prompt fixture
    session_id = "prompt-marker-test"
    monkeypatch.setattr(webui_security, "_is_authenticated", lambda: True)
    monkeypatch.setattr(webui_security, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(webui_paths, "_validate_execution_path", lambda *_args, **_kwargs: str(tmp_path))
    monkeypatch.setattr(webui_paths, "_assert_safe_resolved_path", lambda _: None)
    monkeypatch.setattr(webui_paths, "_validate_upload_assistant_args", lambda args: args)
    monkeypatch.setattr(webui_processes, "_spawn_webui_upload_process", lambda *_args: (process, "subprocess"))
    response = None
    try:
        response = server.app.test_client().post("/api/execute", json={"path": str(tmp_path), "session_id": session_id}, buffered=False)
        assert response.status_code == 200
        deadline = time.monotonic() + 10
        marker_seen = False
        for chunk in response.response:
            assert time.monotonic() < deadline, "Prompt marker was not sent before the answer"
            if b"&gt;" in chunk:
                marker_seen = True
                assert process.poll() is None
                assert webui_session_state.active_processes[session_id]["awaiting_input"] is True
                assert webui_session_state.active_processes[session_id]["input_type"] == "yes_no"
                break
        assert marker_seen
        webui_processes._write_webui_process_input(process, "no")
        assert process.wait(timeout=5) == 0
    finally:
        if response is not None:
            response.close()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        webui_processes._close_webui_process_io(process)
        webui_session_state.active_processes.pop(session_id, None)


def test_webui_child_environment_overrides_no_color(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")

    env = webui_processes._webui_subprocess_env()
    result = subprocess.run(
        [sys.executable, "-u", "-c", "from src.console import console; console.print('[red]color[/red]')"],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )

    assert "NO_COLOR" not in env
    assert "\x1b[" in result.stdout
    assert "31m" in result.stdout


def test_webui_child_reports_structured_progress() -> None:
    result = subprocess.run(
        [sys.executable, "-u", "-c", "from src.webui_progress import publish_progress; publish_progress('hash', 'Hashing', current=9, total=100)"],
        text=True,
        capture_output=True,
        env=webui_processes._webui_subprocess_env(),
        check=True,
    )

    event = webui_processes._subprocess_progress_event(result.stdout)
    assert event is not None
    assert event["id"] == "hash"
    assert event["current"] == 9.0


def test_nyuu_webui_progress_does_not_render_terminal_progress() -> None:
    script = """
import asyncio
import sys
import threading

from src.usenetcreate import run_nyuu_with_progress

child = "print('Uploading 100 article(s)'); print('Article posting progress: 10 read, 10 posted, 5 checked')"
asyncio.run(run_nyuu_with_progress([sys.executable, '-u', '-c', child]))
"""
    result = subprocess.run(  # noqa: S603 - command and script are test-controlled
        [sys.executable, "-u", "-c", script],
        text=True,
        capture_output=True,
        env=webui_processes._webui_subprocess_env(),
        check=True,
    )

    output_lines = [line for line in result.stdout.splitlines() if line]
    events = [webui_processes._subprocess_progress_event(line) for line in output_lines]

    assert all(event is not None for event in events)
    assert [event["current"] for event in events if event is not None] == [0.0, 7.5, 100.0]


def test_pesto_webui_progress_does_not_render_terminal_progress() -> None:
    script = """
import asyncio
import sys
import threading

from src.usenetcreate import run_pesto_with_progress

child = '''import json
print(json.dumps({"type": "segment_done", "progress_pct": 25, "total_segments": 100, "segment_done": 25}))'''
asyncio.run(run_pesto_with_progress([sys.executable, '-u', '-c', child]))
"""
    result = subprocess.run(  # noqa: S603 - command and script are test-controlled
        [sys.executable, "-u", "-c", script],
        text=True,
        capture_output=True,
        env=webui_processes._webui_subprocess_env(),
        check=True,
    )

    output_lines = [line for line in result.stdout.splitlines() if line]
    events = [webui_processes._subprocess_progress_event(line) for line in output_lines]

    assert all(event is not None for event in events)
    assert [event["current"] for event in events if event is not None] == [0.0, 25.0, 100.0]


def test_bdinfo_webui_progress_does_not_render_terminal_progress() -> None:
    script = """
import asyncio
import sys
import threading

from src.discparse import DiscParse

child = "import sys; sys.stderr.write('Stream scan: 25% (1 GiB / 4 GiB, files 1/4, read 100 MiB/s, ETA 3s)\\\\n')"
asyncio.run(DiscParse({})._run_bdinfo_with_progress([sys.executable, '-u', '-c', child], 'bdinfo-scan'))
"""
    result = subprocess.run(  # noqa: S603 - command and script are test-controlled
        [sys.executable, "-u", "-c", script],
        text=True,
        capture_output=True,
        env=webui_processes._webui_subprocess_env(),
        check=True,
    )

    output_lines = [line for line in result.stdout.splitlines() if line]
    events = [webui_processes._subprocess_progress_event(line) for line in output_lines]

    assert all(event is not None for event in events)
    assert [event["current"] for event in events if event is not None] == [0.0, 25.0, 100.0]


def test_long_progress_record_waits_for_newline() -> None:
    partial = f"{webui_processes.PROGRESS_STDOUT_PREFIX}{'x' * 600}"

    assert not webui_processes._should_flush_subprocess_output(partial, "x")
    assert webui_processes._should_flush_subprocess_output(f"{partial}\n", "\n")
