# Assertions are the idiomatic pytest checks for this focused subprocess test.
# ruff: noqa: S101

from types import SimpleNamespace

import pytest

from src import takescreens


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
