# Assertions are the idiomatic pytest checks for this focused subprocess test.
# ruff: noqa: S101

from types import SimpleNamespace

import pytest

from src import takescreens


@pytest.mark.asyncio
async def test_run_ffmpeg_writes_report_next_to_output(tmp_path, monkeypatch):
    output = tmp_path / "release" / "screenshots" / "frame.png"
    captured: dict[str, object] = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured.update(args=args, kwargs=kwargs)

        async def fake_communicate():
            return b"", b""

        return SimpleNamespace(returncode=0, communicate=fake_communicate)

    monkeypatch.setattr(takescreens.platform, "system", lambda: "Windows")
    monkeypatch.setattr(takescreens.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    class Command:
        def compile(self):
            return ["ffmpeg", "-i", "source.mkv", str(output)]

    process = await takescreens.run_ffmpeg(Command())

    assert process == (0, b"", b"")
    env = captured["kwargs"]["env"]
    assert env["FFREPORT"] == f"file={output.parent.resolve() / 'ffmpeg.log'}:level=32"
    assert "FFREPORT" not in takescreens.os.environ
