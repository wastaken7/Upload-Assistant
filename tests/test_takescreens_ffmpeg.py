# Assertions are the idiomatic pytest checks for this focused subprocess test.
# ruff: noqa: S101

import asyncio
import sys
from types import SimpleNamespace

import pytest

from src import takescreens


async def _stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is None:
        process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=3)
    except TimeoutError:
        process.kill()
        await process.wait()


@pytest.mark.asyncio
async def test_run_ffmpeg_writes_report_next_to_output(tmp_path, monkeypatch):
    output = tmp_path / "release" / "screenshots" / "frame.png"
    captured: list[dict[str, object]] = []

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured.append({"args": args, "kwargs": kwargs})

        async def fake_communicate():
            return b"", b""

        return SimpleNamespace(returncode=0, communicate=fake_communicate)

    monkeypatch.setattr(takescreens.platform, "system", lambda: "Windows")
    monkeypatch.setattr(takescreens.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    class Command:
        def compile(self):
            return ["ffmpeg", "-i", output.with_name("source.mkv"), output]

    process = await takescreens.run_ffmpeg(Command())
    second_process = await takescreens.run_ffmpeg(Command())

    assert process == (0, b"", b"")
    assert second_process == (0, b"", b"")
    first_env = captured[0]["kwargs"]["env"]
    second_env = captured[1]["kwargs"]["env"]
    first_report = first_env["FFREPORT"]
    second_report = second_env["FFREPORT"]
    expected_prefix = f"file={output.parent.resolve().as_posix().replace(':', r'\:')}/ffmpeg-"
    assert first_report.startswith(expected_prefix)
    assert first_report.endswith(".log:level=32")
    assert second_report.startswith(expected_prefix)
    assert second_report.endswith(".log:level=32")
    assert first_report != second_report
    assert "FFREPORT" not in takescreens.os.environ
    assert all(isinstance(argument, str) for argument in captured[0]["args"])


@pytest.mark.asyncio
async def test_cancelling_run_ffmpeg_terminates_only_its_owned_process(tmp_path, monkeypatch):
    unrelated = await asyncio.create_subprocess_exec(sys.executable, "-c", "import time; time.sleep(60)")
    original_create_subprocess_exec = asyncio.create_subprocess_exec
    owned_processes: list[asyncio.subprocess.Process] = []
    owned_started = asyncio.Event()

    async def capture_create_subprocess_exec(*args, **kwargs):
        process = await original_create_subprocess_exec(*args, **kwargs)
        owned_processes.append(process)
        owned_started.set()
        return process

    monkeypatch.setattr(takescreens.platform, "system", lambda: "Windows")
    monkeypatch.setattr(takescreens.asyncio, "create_subprocess_exec", capture_create_subprocess_exec)

    class Command:
        def compile(self):
            return [sys.executable, "-c", "import time; time.sleep(60)", tmp_path / "owned.out"]

    task = asyncio.create_task(takescreens.run_ffmpeg(Command()))
    try:
        await asyncio.wait_for(owned_started.wait(), timeout=3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        owned = owned_processes[0]
        for _ in range(100):
            if owned.returncode is not None:
                break
            await asyncio.sleep(0.01)
        if owned.returncode is None:
            pytest.fail("cancelled run_ffmpeg left its owned subprocess running")

        assert unrelated.returncode is None, "cancelling run_ffmpeg terminated an unrelated sibling process"
    finally:
        if not task.done():
            task.cancel()
        for process in owned_processes:
            await _stop_process(process)
        await _stop_process(unrelated)
