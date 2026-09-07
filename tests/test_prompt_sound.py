import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import web_ui.server as server
from src.meta import Meta
from src.prompt_sound import PROMPT_SOUND_STDOUT_MARKER, play_prompt_sound
from src.uphelper import UploadHelper


def test_browser_prompt_sound() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for browser sound tests")
    subprocess.run([node, "--test", str(Path(__file__).with_name("webui_prompt_sound.test.cjs"))], check=True)


@pytest.mark.parametrize("webui", [False, True])
def test_sound_is_written_directly_and_flushed(monkeypatch, webui) -> None:
    class Output(io.StringIO):
        flushed = False

        def flush(self):
            self.flushed = True

    output = Output()
    monkeypatch.setenv("UA_WEBUI_PROMPT_SOUND_STDOUT", "1" if webui else "0")
    monkeypatch.setattr(sys, "stdout", output)

    play_prompt_sound()

    assert output.getvalue() == (f"\n{PROMPT_SOUND_STDOUT_MARKER}\n" if webui else "\a")
    assert output.flushed


@pytest.mark.asyncio
@pytest.mark.parametrize("webui", [False, True])
@pytest.mark.parametrize(
    ("settings", "unattended", "unattended_confirm", "expected_sound"),
    [
        ({}, False, False, True),
        ({"sfx_on_prompt": True}, False, False, True),
        ({"sfx_on_prompt": False}, False, False, False),
        ({}, True, False, False),
        ({}, True, True, True),
    ],
)
async def test_confirmation_honors_sound_setting_and_unattended_mode(
    monkeypatch, capsys, settings, unattended, unattended_confirm, expected_sound, webui
) -> None:
    monkeypatch.setenv("UA_WEBUI_PROMPT_SOUND_STDOUT", "1" if webui else "0")
    monkeypatch.setattr("src.uphelper.logger.info", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("src.uphelper.cli_ui.ask_yes_no", lambda *_args, **_kwargs: False)
    helper = UploadHelper({"DEFAULT": settings})

    await helper.get_confirmation(Meta(category="MOVIE", unattended=unattended, unattended_confirm=unattended_confirm))

    expected = f"\n{PROMPT_SOUND_STDOUT_MARKER}\n" if webui else "\a"
    assert capsys.readouterr().out == (expected if expected_sound else "")


def test_webui_child_uses_printable_sound_record() -> None:
    result = subprocess.run(
        [sys.executable, "-u", "-c", "from src.prompt_sound import play_prompt_sound; play_prompt_sound()"],
        text=True,
        capture_output=True,
        env=server._webui_subprocess_env(),
        check=True,
    )

    assert result.stdout == f"\n{PROMPT_SOUND_STDOUT_MARKER}\n"
    assert server._subprocess_prompt_type(result.stdout) is None


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_execute_stream_delivers_sound_once_without_rendering_marker(tmp_path, monkeypatch, newline) -> None:
    class Process:
        pid = 1
        stdin = io.StringIO()
        stdout = io.StringIO(newline.join(["Before", PROMPT_SOUND_STDOUT_MARKER, "After", ""]))
        stderr = io.StringIO()

        def poll(self):
            return 0 if self.stdout.tell() == len(self.stdout.getvalue()) else None

        def wait(self):
            return 0

    process = Process()
    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_verify_same_origin", lambda: True)
    monkeypatch.setattr(server, "_resolve_user_path", lambda *_args, **_kwargs: str(tmp_path))
    monkeypatch.setattr(server, "_assert_safe_resolved_path", lambda _: None)
    monkeypatch.setattr(server, "_spawn_webui_upload_process", lambda *_args: (process, "subprocess"))
    monkeypatch.setattr(server, "_close_webui_process_io", lambda _: None)
    response = server.app.test_client().post("/api/execute", json={"path": str(tmp_path), "session_id": "sound-test"})
    events = [json.loads(line[6:]) for line in response.get_data(as_text=True).splitlines() if line.startswith("data: ")]

    assert response.status_code == 200
    assert [event for event in events if event["type"] == "prompt_sound"] == [{"type": "prompt_sound"}]
    html = "".join(event["data"] for event in events if event["type"] == "html")
    assert "Before" in html and "After" in html
    assert PROMPT_SOUND_STDOUT_MARKER not in html
    assert events[-1] == {"type": "exit", "code": 0}
