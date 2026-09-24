# ruff: noqa: S101
import io
import json
import sys

import pytest

import web_ui.server as server


class CompletedProcess:
    pid = 0

    def __init__(self) -> None:
        self.stdin = io.StringIO()
        self.stdout = io.StringIO("completed\n")
        self.stderr = io.StringIO()

    def poll(self) -> int:
        return 0

    def wait(self, _timeout: float | None = None) -> int:
        return 0


def _sse_events(response) -> list[dict[str, object]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in response.get_data(as_text=True).splitlines()
        if line.startswith("data: ")
    ]


def test_execute_preserves_shell_punctuation_in_path_and_option_value(tmp_path, monkeypatch) -> None:
    release_path = tmp_path / "Foo.&.Bar.mkv"
    release_path.touch()
    process = CompletedProcess()
    spawned_commands: list[list[str]] = []
    session_id = "shell-sensitive-path-test"

    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_get_browse_roots", lambda: [str(tmp_path)])

    def fake_spawn(command, *_args):
        spawned_commands.append(command)
        return process, "subprocess"

    monkeypatch.setattr(server, "_spawn_webui_upload_process", fake_spawn)

    response = server.app.test_client().post(
        "/api/execute",
        json={
            "path": str(release_path),
            "args": '--music-artist "Artist One & Artist Two"',
            "session_id": session_id,
        },
    )
    try:
        assert response.status_code == 200
        events = _sse_events(response)
        assert not any(event.get("type") == "error" for event in events)
        assert len(spawned_commands) == 1
        command = spawned_commands[0]
        assert command[3] == str(release_path)
        assert command[4:] == ["--music-artist", "Artist One & Artist Two"]
    finally:
        response.close()
        with server.active_processes_lock:
            server.active_processes.pop(session_id, None)


@pytest.mark.parametrize(
    "value",
    ["bad\x00name", "bad\nname", "bad\rname", "bad\x1bname", "bad\x7fname"],
)
def test_validate_upload_assistant_args_rejects_control_characters(value: str) -> None:
    with pytest.raises(ValueError, match="Invalid control character"):
        server._validate_upload_assistant_args([value])


@pytest.mark.parametrize("value", [".", ".."])
def test_validate_upload_assistant_args_rejects_bare_directory_references(value: str) -> None:
    with pytest.raises(ValueError, match="Invalid arg"):
        server._validate_upload_assistant_args([value])


@pytest.mark.skipif(sys.platform == "win32", reason="The fallback Popen path is POSIX-only")
def test_spawn_webui_upload_process_does_not_use_a_shell(tmp_path) -> None:
    marker = tmp_path / "marker"
    payload = f"literal; touch {marker}"
    command = [sys.executable, "-c", "import sys; print(sys.argv[1])", payload]
    process, mode = server._spawn_webui_upload_process(command, tmp_path, server._webui_subprocess_env())
    try:
        stdout, _stderr = process.communicate(timeout=5)
        assert mode == "subprocess"
        assert stdout.strip() == payload
        assert not marker.exists()
    finally:
        server._close_webui_process_io(process)
