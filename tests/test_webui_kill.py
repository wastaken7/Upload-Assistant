# ruff: noqa: S101, S603
import io
import subprocess
import sys
import threading
import time

import psutil

import web_ui.server as server


def test_execute_missing_path_preserves_running_session_process(monkeypatch) -> None:
    class RunningProcess:
        def poll(self):
            return None

    process = RunningProcess()
    terminated_processes = []
    session_id = "replace-running-process-test"

    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_terminate_process_tree", terminated_processes.append)
    with server.active_processes_lock:
        server.active_processes[session_id] = {"mode": "subprocess", "process": process}

    try:
        response = server.app.test_client().post("/api/execute", json={"path": "", "session_id": session_id})

        assert response.status_code == 400
        assert terminated_processes == []
        assert server.active_processes[session_id]["process"] is process
    finally:
        with server.active_processes_lock:
            server.active_processes.pop(session_id, None)


def test_kill_endpoint_stops_upload_controller_and_worker(monkeypatch) -> None:
    child_code = "import time; time.sleep(60)"
    controller_code = f"import subprocess, sys, time; worker = subprocess.Popen([sys.executable, '-c', {child_code!r}]); print(worker.pid, flush=True); time.sleep(60)"
    controller = subprocess.Popen(
        [sys.executable, "-c", controller_code],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert controller.stdout is not None
    worker_pid = int(controller.stdout.readline().strip())

    try:
        terminate_process_tree = server._terminate_process_tree
        monkeypatch.setattr(server, "_terminate_process_tree", lambda process: terminate_process_tree(process, timeout=0.5))
        monkeypatch.setattr(server, "_get_bearer_from_header", lambda: None)
        monkeypatch.setattr(server, "_is_authenticated", lambda: True)
        monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
        monkeypatch.setattr(server, "_verify_same_origin", lambda: True)
        session_id = "kill-tree-test"
        with server.active_processes_lock:
            server.active_processes[session_id] = {"mode": "subprocess", "process": controller}

        response = server.app.test_client().post("/api/kill", json={"session_id": session_id})

        assert response.status_code == 200
        assert response.get_json() == {"success": True, "message": "Process terminated"}
        controller.wait(timeout=5)

        deadline = time.monotonic() + 5
        while psutil.pid_exists(worker_pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not psutil.pid_exists(worker_pid)
    finally:
        with server.active_processes_lock:
            server.active_processes.pop("kill-tree-test", None)
        if controller.poll() is None:
            controller.kill()
            controller.wait(timeout=5)


def test_kill_keeps_session_when_process_tree_termination_fails(monkeypatch) -> None:
    process = object()
    session_id = "failed-kill-test"

    monkeypatch.setattr(server, "_get_bearer_from_header", lambda: None)
    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_verify_same_origin", lambda: True)
    monkeypatch.setattr(server, "_terminate_process_tree", lambda _: False)
    monkeypatch.setattr(server, "_close_webui_process_io", lambda _: None)
    with server.active_processes_lock:
        server.active_processes[session_id] = {"mode": "subprocess", "process": process}

    try:
        response = server.app.test_client().post("/api/kill", json={"session_id": session_id})

        assert response.status_code == 500
        assert response.get_json() == {"error": "Failed to terminate process tree", "success": False}
        assert server.active_processes[session_id]["process"] is process
    finally:
        with server.active_processes_lock:
            server.active_processes.pop(session_id, None)


def test_sse_disconnect_terminates_running_process_tree_when_keep_running_is_disabled(tmp_path, monkeypatch) -> None:
    class RunningProcess:
        pid = 1
        stdin = io.StringIO()
        stdout = io.StringIO()
        stderr = io.StringIO()

        def poll(self):
            return None

    process = RunningProcess()
    terminated_processes = []
    session_id = "sse-disconnect-test"

    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_validate_execution_path", lambda *_args, **_kwargs: str(tmp_path))
    monkeypatch.setattr(server, "_assert_safe_resolved_path", lambda _: None)
    monkeypatch.setattr(server, "_validate_upload_assistant_args", lambda args: args)
    monkeypatch.setattr(server, "_spawn_webui_upload_process", lambda *_args: (process, "subprocess"))
    monkeypatch.setattr(server, "_terminate_process_tree", terminated_processes.append)
    monkeypatch.setattr(server, "_close_webui_process_io", lambda _: None)
    monkeypatch.setattr(server, "_webui_session_settings", lambda: (False, 0.0))

    response = server.app.test_client().post("/api/execute", json={"path": str(tmp_path), "session_id": session_id}, buffered=False)
    try:
        next(response.response)  # Logged "Executing" event, replayed after startup.
        next(response.response)  # End of the replayed backlog.
        response.close()

        # The session pump may terminate the orphaned tree again; the stream does it first.
        assert terminated_processes[0] is process
        assert session_id not in server.active_processes
    finally:
        response.close()
        with server.active_processes_lock:
            server.active_processes.pop(session_id, None)
        # The session thread must finish while this test's patches are active.
        for thread in threading.enumerate():
            if thread.name == f"webui-session-{session_id}":
                thread.join(timeout=10)
                assert not thread.is_alive()


def test_process_tree_termination_refuses_init_and_idle_pids() -> None:
    class InitLookalike:
        pid = 1

        def poll(self):
            return None

    # Walking PID 1's children would stop every process on the machine.
    assert server._terminate_process_tree(InitLookalike()) is False
