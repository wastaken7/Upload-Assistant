# ruff: noqa: S101
import io
import json
import os
import subprocess
import sys
import time

import pytest

import web_ui.server as server


def test_upload_child_publishes_preview_without_in_process_session() -> None:
    result = subprocess.run(
        [sys.executable, "-u", "-c", "import upload; upload._publish_webui_preview_target('Fictional Journey.mkv', 'fictional-release')"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=server._webui_subprocess_env(),
        timeout=30,
        check=True,
    )
    events = [server._subprocess_progress_event(line) for line in result.stdout.splitlines()]
    assert {"op": "preview_target", "path": "Fictional Journey.mkv", "meta_uuid": "fictional-release"} in events


def test_queue_preview_follows_child_targets(tmp_path, monkeypatch) -> None:
    targets = [tmp_path / "Fictional Journey.mkv", tmp_path / ("a" * 200) / ("b" * 200) / "Fictional Finale.mkv"]
    queue_path = tmp_path / "webui_queue_fictional.txt"
    queue_path.write_text("\n".join(str(target) for target in targets), encoding="utf-8")
    state_dir = tmp_path / "state"
    output = "Continue? (y/N)\n"
    for index, target in enumerate(targets):
        meta_uuid = f"fictional-release-{index}"
        meta_dir = state_dir / "tmp" / meta_uuid
        meta_dir.mkdir(parents=True)
        (meta_dir / "meta.json").write_text(
            json.dumps({"uuid": meta_uuid, "path": str(target), "title": target.stem, "poster": f"https://example.invalid/poster-{index}.jpg"}), encoding="utf-8"
        )
        output += server.PROGRESS_STDOUT_PREFIX + json.dumps({"op": "preview_target", "path": str(target), "meta_uuid": meta_uuid}) + "\n\n"
        output += server.PROGRESS_STDOUT_PREFIX + json.dumps({"op": "preview_target", "path": str(target)}) + "\n\n"
        # Re-publish the UUID as metadata becomes available for the same item.
        output += server.PROGRESS_STDOUT_PREFIX + json.dumps({"op": "preview_target", "path": str(target), "meta_uuid": meta_uuid}) + "\n\n"

    class WaitingProcess:
        stdin = io.StringIO()
        stdout = io.StringIO(output)
        stderr = io.StringIO()

        def poll(self):
            return None

    session_id = "queue-preview-test"
    monkeypatch.setattr(server, "STATE_DIR", state_dir)
    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_validate_execution_path", lambda *_args, **_kwargs: str(queue_path))
    monkeypatch.setattr(server, "_generated_queues", {os.path.normcase(os.path.realpath(queue_path)): "fictional-hash"})
    monkeypatch.setattr(server, "_assert_safe_resolved_path", lambda _: None)
    monkeypatch.setattr(server, "_validate_upload_assistant_args", lambda args: args)
    monkeypatch.setattr(server, "_spawn_webui_upload_process", lambda *_args: (WaitingProcess(), "subprocess"))
    monkeypatch.setattr(server, "_terminate_process_tree", lambda _: True)
    response = server.app.test_client().post("/api/execute", json={"path": str(queue_path), "session_id": session_id}, buffered=False)
    seen = []
    cleared = []
    try:
        deadline = time.monotonic() + 5
        for chunk in response.response:
            assert time.monotonic() < deadline
            event = json.loads(chunk.decode().removeprefix("data: "))
            if event["type"] == "html":
                assert "preview_target" not in event["data"]
            state = server.active_processes[session_id]
            if state["path"] in [str(target) for target in targets] and "meta_uuid" not in state:
                cleared.append(state["path"])
                assert server._find_execution_preview(session_id)["status"] == "waiting"
            if state.get("meta_uuid"):
                preview = server._find_execution_preview(session_id)
                assert preview["status"] == "ready"
                assert preview["title"] == next(target.stem for target in targets if str(target) == preview["path"])
                assert preview["poster_url"].startswith("https://example.invalid/poster-")
                assert preview["awaiting_input"] is True
                if preview["path"] not in seen:
                    seen.append(preview["path"])
                if len(seen) == 2 and len(cleared) == 2:
                    break
        assert seen == [str(target) for target in targets]
        assert cleared == [str(target) for target in targets]
    finally:
        response.close()
        server.active_processes.pop(session_id, None)


def test_replaced_execution_cannot_change_preview(monkeypatch) -> None:
    state = server._make_process_state("Fictional Finale.mkv", "")
    monkeypatch.setattr(server, "active_processes", {"preview-session": state})
    server.set_execution_preview_target("preview-session", "old-run-token", "Fictional Journey.mkv", "old-release")
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
    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_validate_execution_path", lambda *_args, **_kwargs: str(tmp_path))
    monkeypatch.setattr(server, "_assert_safe_resolved_path", lambda _: None)
    monkeypatch.setattr(server, "_validate_upload_assistant_args", lambda args: args)
    monkeypatch.setattr(server, "_spawn_webui_upload_process", lambda *_args: (process, "subprocess"))
    monkeypatch.setattr(server, "_terminate_process_tree", lambda _process: True)
    original_flush = server._should_flush_subprocess_output
    states_before_flush = []

    def observe_flush(buffer, char, *, idle=False):
        states_before_flush.append(server.active_processes[session_id]["awaiting_input"])
        return original_flush(buffer, char, idle=idle)

    monkeypatch.setattr(server, "_should_flush_subprocess_output", observe_flush)
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
        state = server.active_processes[session_id]
        assert state["awaiting_input"] is (expected_type is not None)
        if expected_type is not None:
            assert state["input_type"] == expected_type
    finally:
        response.close()
        server.active_processes.pop(session_id, None)


def test_subprocess_yes_no_prompt_is_classified_for_dedicated_buttons() -> None:
    assert server._subprocess_prompt_type(":: Continue? (y/N)\n") == "yes_no"
    assert server._subprocess_prompt_type("\x1b[1;31mContinue? (Y/n)\x1b[0m") == "yes_no"
    assert server._subprocess_prompt_type("Enter a new title:") == "text"
    assert server._subprocess_prompt_type(server.PROGRESS_STDOUT_PREFIX + '{"detail":"Please select a stream"}') is None
    assert server._subprocess_prompt_type("\x1b[32m> \x1b[0m", "yes_no") == "yes_no"
    assert server._subprocess_prompt_type("> ") == "text"


@pytest.mark.parametrize(
    "background_output, expected_type",
    [
        ("\n", "yes_no"),
        ("\x1b[0m\n", "yes_no"),
        ("\n" + server.PROGRESS_STDOUT_PREFIX + '{"op":"upsert","id":"scan","label":"Scanning","current":25,"total":100}\n', "yes_no"),
        ("\n" + server.PROGRESS_STDOUT_PREFIX + '{"op":"reset"}\n', "yes_no"),
        (server.PROGRESS_STDOUT_PREFIX + '{"op":"reset"}\n', "yes_no"),
        (server.PROMPT_SOUND_STDOUT_MARKER + "\n", "yes_no"),
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
    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_verify_same_origin", lambda: True)
    monkeypatch.setattr(server, "_validate_execution_path", lambda *_args, **_kwargs: str(tmp_path))
    monkeypatch.setattr(server, "_assert_safe_resolved_path", lambda _: None)
    monkeypatch.setattr(server, "_validate_upload_assistant_args", lambda args: args)
    monkeypatch.setattr(server, "_spawn_webui_upload_process", lambda *_args: (process, "subprocess"))
    monkeypatch.setattr(server, "_terminate_process_tree", lambda _process: True)
    client = server.app.test_client()
    response = client.post("/api/execute", json={"path": str(tmp_path), "session_id": session_id}, buffered=False)
    try:
        assert response.status_code == 200
        deadline = time.monotonic() + 5
        first_output = True
        for chunk in response.response:
            assert time.monotonic() < deadline, "Input marker never reached the browser"
            event = json.loads(chunk.decode().removeprefix("data: "))
            if event["type"] not in {"html", "progress"}:
                continue
            state = server.active_processes[session_id]
            marker_seen = event["type"] == "html" and "&gt;" in event["data"]
            current_type = "yes_no" if first_output else (expected_type or "text") if marker_seen else expected_type
            assert state["awaiting_input"] is (current_type is not None)
            assert state["input_type"] == current_type
            preview = server._find_execution_preview(session_id)
            assert preview["awaiting_input"] is (current_type is not None)
            assert preview["input_type"] == current_type
            first_output = False
            if marker_seen:
                break
        else:
            pytest.fail("No input marker received")

        answer = client.post("/api/input", json={"session_id": session_id, "input": "yes"})
        assert answer.status_code == 200
        assert process.stdin.getvalue() == "yes\n"
        assert state["awaiting_input"] is False
        assert state["input_type"] is None
    finally:
        response.close()
        server.active_processes.pop(session_id, None)


@pytest.mark.parametrize("prompt", ["> ", "\x1b[32m> \x1b[0m", "Enter a title: ", "Continue? (y/N)"])
def test_unterminated_prompts_flush_after_output_becomes_idle(prompt) -> None:
    assert not server._should_flush_subprocess_output(prompt, prompt[-1])
    assert server._should_flush_subprocess_output(prompt, "", idle=True)


@pytest.mark.parametrize("buffer", ["", "Ordinary output", "Enter title:\x1b[", "Enter title:\x1b[31", server.PROGRESS_STDOUT_PREFIX + '{"detail":"Enter a title:"'])
def test_idle_flush_keeps_incomplete_ansi_and_progress_records(buffer) -> None:
    assert not server._should_flush_subprocess_output(buffer, "", idle=True)


def test_browser_receives_cli_ui_marker_before_answering(tmp_path, monkeypatch) -> None:
    command = [sys.executable, "-u", "-c", "import src.console; import cli_ui; answer = cli_ui.ask_yes_no('Continue?', default=False); print(f'ANSWER={answer}', flush=True)"]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=server._webui_subprocess_env())  # noqa: S603 - fixed Python prompt fixture
    session_id = "prompt-marker-test"
    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_validate_execution_path", lambda *_args, **_kwargs: str(tmp_path))
    monkeypatch.setattr(server, "_assert_safe_resolved_path", lambda _: None)
    monkeypatch.setattr(server, "_validate_upload_assistant_args", lambda args: args)
    monkeypatch.setattr(server, "_spawn_webui_upload_process", lambda *_args: (process, "subprocess"))
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
                assert server.active_processes[session_id]["awaiting_input"] is True
                assert server.active_processes[session_id]["input_type"] == "yes_no"
                break
        assert marker_seen
        server._write_webui_process_input(process, "no")
        assert process.wait(timeout=5) == 0
    finally:
        if response is not None:
            response.close()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        server._close_webui_process_io(process)
        server.active_processes.pop(session_id, None)


def test_webui_child_environment_overrides_no_color(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")

    env = server._webui_subprocess_env()
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
        env=server._webui_subprocess_env(),
        check=True,
    )

    event = server._subprocess_progress_event(result.stdout)
    assert event is not None
    assert event["id"] == "hash"
    assert event["current"] == 9.0


def test_nyuu_webui_progress_does_not_render_terminal_progress() -> None:
    script = """
import asyncio
import sys

from src.usenetcreate import run_nyuu_with_progress

child = "print('Uploading 100 article(s)'); print('Article posting progress: 10 read, 10 posted, 5 checked')"
asyncio.run(run_nyuu_with_progress([sys.executable, '-u', '-c', child]))
"""
    result = subprocess.run(  # noqa: S603 - command and script are test-controlled
        [sys.executable, "-u", "-c", script],
        text=True,
        capture_output=True,
        env=server._webui_subprocess_env(),
        check=True,
    )

    output_lines = [line for line in result.stdout.splitlines() if line]
    events = [server._subprocess_progress_event(line) for line in output_lines]

    assert all(event is not None for event in events)
    assert [event["current"] for event in events if event is not None] == [0.0, 7.5, 100.0]


def test_pesto_webui_progress_does_not_render_terminal_progress() -> None:
    script = """
import asyncio
import sys

from src.usenetcreate import run_pesto_with_progress

child = '''import json
print(json.dumps({"type": "segment_done", "progress_pct": 25, "total_segments": 100, "segment_done": 25}))'''
asyncio.run(run_pesto_with_progress([sys.executable, '-u', '-c', child]))
"""
    result = subprocess.run(  # noqa: S603 - command and script are test-controlled
        [sys.executable, "-u", "-c", script],
        text=True,
        capture_output=True,
        env=server._webui_subprocess_env(),
        check=True,
    )

    output_lines = [line for line in result.stdout.splitlines() if line]
    events = [server._subprocess_progress_event(line) for line in output_lines]

    assert all(event is not None for event in events)
    assert [event["current"] for event in events if event is not None] == [0.0, 25.0, 100.0]


def test_bdinfo_webui_progress_does_not_render_terminal_progress() -> None:
    script = """
import asyncio
import sys

from src.discparse import DiscParse

child = "import sys; sys.stderr.write('Stream scan: 25% (1 GiB / 4 GiB, files 1/4, read 100 MiB/s, ETA 3s)\\\\n')"
asyncio.run(DiscParse({})._run_bdinfo_with_progress([sys.executable, '-u', '-c', child], 'bdinfo-scan'))
"""
    result = subprocess.run(  # noqa: S603 - command and script are test-controlled
        [sys.executable, "-u", "-c", script],
        text=True,
        capture_output=True,
        env=server._webui_subprocess_env(),
        check=True,
    )

    output_lines = [line for line in result.stdout.splitlines() if line]
    events = [server._subprocess_progress_event(line) for line in output_lines]

    assert all(event is not None for event in events)
    assert [event["current"] for event in events if event is not None] == [0.0, 25.0, 100.0]


def test_long_progress_record_waits_for_newline() -> None:
    partial = f"{server.PROGRESS_STDOUT_PREFIX}{'x' * 600}"

    assert not server._should_flush_subprocess_output(partial, "x")
    assert server._should_flush_subprocess_output(f"{partial}\n", "\n")
