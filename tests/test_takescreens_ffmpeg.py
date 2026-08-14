# Assertions are the idiomatic pytest checks for this focused subprocess test.
# ruff: noqa: S101

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import ffmpeg
import pytest

from src import takescreens
from src.meta import Meta


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

    command = ffmpeg.input(str(output.with_name("source.mkv"))).output(str(output), vframes=1).global_args("-y", "-loglevel", "quiet")

    process = await takescreens.run_ffmpeg(command)
    second_process = await takescreens.run_ffmpeg(command)

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
async def test_run_ffmpeg_prefers_configured_binary(tmp_path, monkeypatch):
    executable = tmp_path / "ffmpeg.exe"
    executable.touch()
    executable.chmod(executable.stat().st_mode | 0o111)
    captured: list[tuple[object, ...]] = []

    async def fake_create_subprocess_exec(*args, **_kwargs):
        captured.append(args)

        async def fake_communicate():
            return b"", b""

        return SimpleNamespace(returncode=0, communicate=fake_communicate)

    monkeypatch.setattr(takescreens.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(takescreens, "default_config", {"ffmpeg_path": str(executable)})

    command = ffmpeg.input(str(tmp_path / "source.mkv")).output(str(tmp_path / "frame.png"), vframes=1)
    await takescreens.run_ffmpeg(command)

    assert captured[0][0] == str(executable)


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


@pytest.mark.asyncio
async def test_determine_tonemapping_uses_verified_libplacebo(monkeypatch, tmp_path):
    meta = Meta(hdr="HDR")
    compatibility_calls = []

    async def compatible(*args):
        compatibility_calls.append(args)
        return True, True

    monkeypatch.setattr(takescreens, "tone_map", True)
    monkeypatch.setattr(takescreens, "use_libplacebo", True)
    monkeypatch.setattr(takescreens, "ffmpeg_is_good", False)
    monkeypatch.setattr(takescreens, "check_libplacebo_compatibility", compatible)

    enabled = await takescreens.determine_tonemapping(1, 1, 1920, 1080, "source.mkv", "10", str(tmp_path / "frame.png"), "quiet", meta)

    assert enabled is True
    assert meta.tonemapped is True
    assert meta.libplacebo is True
    assert len(compatibility_calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("hdr", ["DV", "HLG"])
async def test_determine_tonemapping_uses_zscale_fallback_for_dv_and_hlg(monkeypatch, tmp_path, hdr):
    monkeypatch.setattr(takescreens, "tone_map", True)
    monkeypatch.setattr(takescreens, "use_libplacebo", False)
    meta = Meta(hdr=hdr)

    enabled = await takescreens.determine_tonemapping(1, 1, 1920, 1080, "source.mkv", "10", str(tmp_path / "frame.png"), "quiet", meta)

    assert enabled is True
    assert meta.tonemapped is True
    assert meta.libplacebo is False


@pytest.mark.asyncio
async def test_capture_screenshot_applies_selected_libplacebo_tonemapping(monkeypatch, tmp_path):
    source = tmp_path / "source.mkv"
    output = tmp_path / "frame.png"
    source.write_bytes(b"video")
    commands: list[list[str]] = []

    async def run_stub(command):
        compiled = takescreens.compile_ffmpeg_command(command)
        commands.append(compiled)
        Path(takescreens.get_ffmpeg_output_path(command, compiled)).write_bytes(b"png")
        return 0, b"", b""

    monkeypatch.setattr(takescreens, "run_ffmpeg", run_stub)

    result = await takescreens.capture_screenshot((0, str(source), 10, str(output), 1920, 1080, 1, 1, "quiet", True, Meta(libplacebo=True)))

    assert result == (0, str(output))
    assert any("libplacebo=tonemapping=hable" in argument for argument in commands[0])
