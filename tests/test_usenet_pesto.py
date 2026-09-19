# ruff: noqa: S101

import os
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

    async def fake_run_pesto(cmd, cwd=None, env=None):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["env"] = env
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


@pytest.mark.asyncio
async def test_pesto_season_upload_collects_episode_and_pack_nzbs(tmp_path: Path, monkeypatch) -> None:
    season_dir = tmp_path / "Show.S01.1080p.WEB-DL-GROUP"
    season_dir.mkdir()
    (season_dir / "Show.S01E01.1080p.WEB-DL-GROUP.mkv").write_bytes(b"episode one")
    (season_dir / "Show.S01E02.1080p.WEB-DL-GROUP.mkv").write_bytes(b"episode two")
    captured: dict[str, object] = {}

    managed_7z = tmp_path / "managed" / "7zz"
    managed_7z.parent.mkdir()
    managed_7z.write_bytes(b"fake 7zip executable")

    async def fake_check_binary(binary_name, *_args, **_kwargs):
        return str(managed_7z) if binary_name == "7z" else binary_name

    async def fake_run_pesto(cmd, cwd=None, env=None):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["env"] = env
        nzb_dir = Path(cmd[cmd.index("--nzb-dir") + 1])
        nzb_dir.mkdir(parents=True, exist_ok=True)
        content = "<nzb>" + (" " * 100) + "</nzb>"
        (nzb_dir / "Show.S01E01.1080p.WEB-DL-GROUP.nzb").write_text(content, encoding="utf-8")
        (nzb_dir / "Show.S01E02.1080p.WEB-DL-GROUP.nzb").write_text(content, encoding="utf-8")
        (nzb_dir / f"{season_dir.name}.nzb").write_text(content, encoding="utf-8")

    monkeypatch.setattr(usenetcreate, "check_binary", fake_check_binary)
    monkeypatch.setattr(usenetcreate, "run_pesto_with_progress", fake_run_pesto)

    output_dir = tmp_path / "output"
    meta = Meta(
        base_dir=str(tmp_path),
        path=str(season_dir),
        uuid="season-test",
        basename_no_ext=season_dir.name,
        category="TV",
        tv_pack=True,
    )
    result = await usenetcreate.prepare_and_upload_usenet(
        meta,
        {
            "USENET": {
                "host": "news.example.com",
                "username": "poster",
                "password": "secret",
                "newsgroups": "alt.binaries.test",
                "usenet_uploader": "pesto",
                "pesto_season_upload": True,
                "skip_archive": False,
                "archive_password": "pack-secret",
                "rar_volume_size": "auto",
                "nzb_output_dir": str(output_dir),
            }
        },
    )

    command = captured["cmd"]
    assert isinstance(command, list)
    assert "--season" in command
    assert "--nzb-dir" in command
    assert command[command.index("--ext") + 1] == "avi,m2ts,m4v,mkv,mov,mp4,ts,webm,wmv"
    assert command[command.index("--compress-temp-dir") + 1].endswith("usenet/pesto-compress")
    assert "--out" not in command
    assert "--compress=7z" in command
    assert command[command.index("--compress-volume-size") + 1] == "100m"
    assert "--password=pack-secret" in command
    assert command[command.index("--nzb-password") + 1] == "pack-secret"
    assert command[-1] == str(season_dir.resolve())
    assert captured["cwd"] == str(season_dir)
    assert isinstance(captured["env"], dict)
    staged_7z_dir = Path(captured["env"]["PATH"].split(os.pathsep)[0])
    assert staged_7z_dir.name == "pesto-bin"
    assert result == output_dir / f"{season_dir.name}.nzb"
    assert [Path(path).name for path in meta.usenet_nzb_paths] == [
        "Show.S01E01.1080p.WEB-DL-GROUP.nzb",
        "Show.S01E02.1080p.WEB-DL-GROUP.nzb",
        f"{season_dir.name}.nzb",
    ]
    assert all(Path(path).is_file() for path in meta.usenet_nzb_paths)


def test_pesto_season_entries_reject_top_level_sample_video(tmp_path: Path) -> None:
    season_dir = tmp_path / "Show.S01"
    season_dir.mkdir()
    (season_dir / "Show.S01E01.mkv").write_bytes(b"episode")
    (season_dir / "Sample.mkv").write_bytes(b"sample")

    with pytest.raises(ValueError, match=r"Sample\.mkv"):
        usenetcreate.discover_pesto_season_entries(season_dir)


def test_pesto_season_entries_ignore_sidecars(tmp_path: Path) -> None:
    season_dir = tmp_path / "Show.S01"
    season_dir.mkdir()
    episode = season_dir / "Show.S01E01.mkv"
    episode.write_bytes(b"episode")
    (season_dir / "Show.S01E01.srt").write_text("subtitle", encoding="utf-8")
    (season_dir / "release.sfv").write_text("checksum", encoding="utf-8")

    assert usenetcreate.discover_pesto_season_entries(season_dir) == {episode.stem: episode}


@pytest.mark.asyncio
async def test_build_usenet_indexer_metas_uses_episode_metadata_and_keeps_pack_last(tmp_path: Path, monkeypatch) -> None:
    season_dir = tmp_path / "Show.S01"
    season_dir.mkdir()
    episode_file = season_dir / "Show.S01E01E02.1080p.WEB-DL-GROUP.mkv"
    episode_file.write_bytes(b"video")
    episode_nzb = tmp_path / "Show.S01E01E02.1080p.WEB-DL-GROUP.nzb"
    pack_nzb = tmp_path / "Show.S01.nzb"
    meta = Meta(
        path=str(season_dir),
        name="Show.S01.1080p.WEB-DL-GROUP",
        basename_no_ext="Show.S01.1080p.WEB-DL-GROUP",
        category="TV",
        season="S01",
        season_int=1,
        tv_pack=True,
        tracker_status={"CURUPIRA": {"upload": True}},
    )

    async def fake_export_info(*_args, **_kwargs):
        return {"media": {"track": []}}

    monkeypatch.setattr("src.exportmi.export_info", fake_export_info)
    submissions = await usenetcreate.build_usenet_indexer_metas(meta, [str(episode_nzb), str(pack_nzb)], ["CURUPIRA"])

    assert len(submissions) == 2
    episode_meta, pack_meta = submissions
    assert episode_meta is not meta
    assert episode_meta.name == episode_nzb.stem
    assert episode_meta.basename_no_ext == episode_nzb.stem
    assert episode_meta.season == "S01"
    assert episode_meta.season_int == 1
    assert episode_meta.episode == "E01E02"
    assert episode_meta.episode_int == 1
    assert episode_meta.tv_pack is False
    assert episode_meta.path == str(episode_file)
    assert episode_meta.filelist == [str(episode_file)]
    assert episode_meta.tracker_status == {"CURUPIRA": {}}
    assert episode_meta.uuid != meta.uuid
    assert pack_meta is not meta
    assert pack_meta.nzb_path == str(pack_nzb)
    assert pack_meta.tv_pack is True


def test_episode_only_indexer_filter_applies_only_to_pack() -> None:
    trackers = ["CURUPIRA", "NZBNEST", "NZBGEEK"]
    episodes_only = {"CURUPIRA", "NZBGEEK"}

    assert usenetcreate.select_usenet_indexers_for_submission(trackers, episodes_only, is_pack=False) == trackers
    assert usenetcreate.select_usenet_indexers_for_submission(trackers, episodes_only, is_pack=True) == ["NZBNEST"]
