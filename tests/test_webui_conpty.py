# ruff: noqa: S101
import re
import sys
import time

import psutil
import pytest

import web_ui.server as server
from src.console import ansi_to_html

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="ConPTY is Windows-only")


def _read_until(process: server._WebUIProcess, expected: str, timeout: float = 5.0) -> str:
    deadline = time.monotonic() + timeout
    output = ""
    while expected not in output and time.monotonic() < deadline:
        try:
            output += process.read(1024)  # type: ignore[attr-defined]
        except EOFError:
            break
    return output


def test_conpty_preserves_ansi_and_accepts_webui_input() -> None:
    command = [
        sys.executable,
        "-u",
        "-c",
        "from src.console import logger; import cli_ui; logger.info('[green]Gathering info[/green]'); answer = cli_ui.ask_yes_no('Continue?', default=False); print(f'ANSWER={answer}')",
    ]
    process, mode = server._spawn_webui_upload_process(command, server.CODE_DIR, server._webui_subprocess_env())

    try:
        output = _read_until(process, "(y/N)")
        assert mode == "conpty"
        assert "\x1b[32m" in output
        assert server._subprocess_prompt_type(":: Continue? (y/N)") == "yes_no"
        assert "color:" in ansi_to_html(output)

        server._write_webui_process_input(process, "yes")
        output += _read_until(process, "ANSWER=True")
        assert "ANSWER=True" in output
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            server._terminate_process_tree(process)
        server._close_webui_process_io(process)


def test_kill_endpoint_stops_conpty_controller_and_worker(monkeypatch) -> None:
    child_code = "import time; time.sleep(60)"
    controller_code = (
        f"import subprocess, sys, time; worker = subprocess.Popen([sys.executable, '-c', {child_code!r}]); print(f'WORKER={{worker.pid}}', flush=True); time.sleep(60)"
    )
    command = [sys.executable, "-u", "-c", controller_code]
    process, mode = server._spawn_webui_upload_process(command, server.CODE_DIR, server._webui_subprocess_env())

    try:
        output = _read_until(process, "WORKER=")
        worker_pid_match = re.search(r"WORKER=(\d+)", output)
        assert mode == "conpty"
        assert worker_pid_match is not None
        worker_pid = int(worker_pid_match.group(1))
        monkeypatch.setattr(server, "_get_bearer_from_header", lambda: None)
        monkeypatch.setattr(server, "_is_authenticated", lambda: True)
        monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
        monkeypatch.setattr(server, "_verify_same_origin", lambda: True)
        session_id = "conpty-kill-tree-test"
        with server.active_processes_lock:
            server.active_processes[session_id] = {"mode": mode, "process": process}

        response = server.app.test_client().post("/api/kill", json={"session_id": session_id})

        assert response.status_code == 200
        assert response.get_json() == {"success": True, "message": "Process terminated"}
        deadline = time.monotonic() + 5
        while psutil.pid_exists(worker_pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not psutil.pid_exists(worker_pid)
    finally:
        with server.active_processes_lock:
            server.active_processes.pop("conpty-kill-tree-test", None)
        if process.poll() is None:
            server._terminate_process_tree(process)
        server._close_webui_process_io(process)
