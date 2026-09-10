# ruff: noqa: S101

from pathlib import Path

import pytest

from src import usenetcreate
from src.meta import Meta


@pytest.mark.asyncio
async def test_pesto_uses_stable_auth_password_flag(tmp_path: Path, monkeypatch) -> None:
    source_file = tmp_path / "release.mkv"
    source_file.write_bytes(b"video")
    captured: dict[str, object] = {}

    async def fake_check_binary(binary_name, *_args, **_kwargs):
        return binary_name

    async def fake_run_pesto(cmd, cwd=None):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        nzb_path = Path(cmd[cmd.index("--out") + 1])
        nzb_path.write_text("<nzb>" + (" " * 100) + "</nzb>", encoding="utf-8")

    monkeypatch.setattr(usenetcreate, "check_binary", fake_check_binary)
    monkeypatch.setattr(usenetcreate, "run_pesto_with_progress", fake_run_pesto)

    meta = Meta(base_dir=str(tmp_path), path=str(source_file), uuid="test", basename_no_ext="release")
    result = await usenetcreate.prepare_and_upload_usenet(
        meta,
        {
            "USENET": {
                "host": "news.example.com",
                "username": "poster",
                "password": "secret",
                "newsgroups": "alt.binaries.test",
                "usenet_uploader": "pesto",
                "skip_archive": True,
            }
        },
    )

    command = captured["cmd"]
    assert isinstance(command, list)
    assert command[command.index("--auth-password") + 1] == "secret"
    assert "-p" not in command
    assert result == tmp_path / "tmp" / "release.mkv" / "release.nzb"


def test_pesto_command_redaction_masks_all_sensitive_values() -> None:
    rendered = usenetcreate._redact_pesto_command(
        [
            "pesto",
            "-u",
            "poster",
            "--auth-password",
            "server-secret",
            "--nzb-password=nzb-secret",
            "--proxy",
            "socks5://proxy-user:proxy-secret@localhost:1080",
            "release.bin",
        ]
    )

    assert "poster" not in rendered
    assert "server-secret" not in rendered
    assert "nzb-secret" not in rendered
    assert "proxy-secret" not in rendered
    assert rendered == "pesto -u ******** --auth-password ******** --nzb-password=******** --proxy ******** release.bin"
