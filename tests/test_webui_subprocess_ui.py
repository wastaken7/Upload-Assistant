# ruff: noqa: S101
import io
import json
import subprocess
import sys
import time

import pytest

import web_ui.server as server


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
    monkeypatch.setattr(server, "_resolve_user_path", lambda *_args, **_kwargs: str(tmp_path))
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


@pytest.mark.parametrize("prompt", ["> ", "\x1b[32m> \x1b[0m", "Enter a title: ", "Continue? (y/N)"])
def test_unterminated_prompts_flush_after_output_becomes_idle(prompt) -> None:
    assert not server._should_flush_subprocess_output(prompt, prompt[-1])
    assert server._should_flush_subprocess_output(prompt, "", idle=True)


@pytest.mark.parametrize("buffer", ["", "Ordinary output", "Enter title:\x1b[", "Enter title:\x1b[31", server.PROGRESS_STDOUT_PREFIX + '{"detail":"Enter a title:"'])
def test_idle_flush_keeps_incomplete_ansi_and_progress_records(buffer) -> None:
    assert not server._should_flush_subprocess_output(buffer, "", idle=True)


def test_browser_receives_cli_ui_marker_before_answering(tmp_path, monkeypatch) -> None:
    command = [sys.executable, "-u", "-c", "import src.console; import cli_ui; answer = cli_ui.ask_yes_no('Continue?', default=False); print(f'ANSWER={answer}', flush=True)"]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=server._webui_subprocess_env())
    session_id = "prompt-marker-test"
    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_resolve_user_path", lambda *_args, **_kwargs: str(tmp_path))
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
