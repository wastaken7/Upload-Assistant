# ruff: noqa: S101

import os
from pathlib import Path
from unittest.mock import AsyncMock

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
        config_root = env["APPDATA"] if os.name == "nt" else env["XDG_CONFIG_HOME"]
        captured["config_root"] = config_root
        captured["archive_dir_exists"] = Path(config_root, "pesto", "nzb").is_dir()
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
    assert isinstance(captured["env"], dict)
    assert Path(captured["config_root"]).parts[-2:] == ("usenet", "pesto-config")
    assert captured["archive_dir_exists"] is True
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


def test_pesto_obfuscation_mode_validation() -> None:
    from src.configvalidator import _validate_usenet_section

    _, valid_warnings = _validate_usenet_section({"pesto_obfuscation_mode": "light"})
    _, invalid_warnings = _validate_usenet_section({"pesto_obfuscation_mode": "hidden"})

    assert not any(warning.key == "pesto_obfuscation_mode" for warning in valid_warnings)
    assert any(warning.key == "pesto_obfuscation_mode" for warning in invalid_warnings)


def test_unused_pesto_obfuscation_mode_does_not_block_nyuu() -> None:
    assert usenetcreate.get_pesto_obfuscation_mode({"pesto_obfuscation_mode": "unused-invalid"}, use_pesto=False) == "unused-invalid"
    with pytest.raises(ValueError, match="pesto_obfuscation_mode"):
        usenetcreate.get_pesto_obfuscation_mode({"pesto_obfuscation_mode": "invalid"}, use_pesto=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("include_pack", [True, False])
async def test_pesto_season_upload_collects_episode_and_optional_pack_nzbs(tmp_path: Path, monkeypatch, include_pack: bool) -> None:
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
        config_root = env["APPDATA"] if os.name == "nt" else env["XDG_CONFIG_HOME"]
        captured["config_root"] = config_root
        captured["archive_dir_exists"] = Path(config_root, "pesto", "nzb").is_dir()
        nzb_dir = Path(cmd[cmd.index("--nzb-dir") + 1])
        nzb_dir.mkdir(parents=True, exist_ok=True)
        content = "<nzb>" + (" " * 100) + "</nzb>"
        (nzb_dir / "Show.S01E01.1080p.WEB-DL-GROUP.nzb").write_text(content, encoding="utf-8")
        (nzb_dir / "Show.S01E02.1080p.WEB-DL-GROUP.nzb").write_text(content, encoding="utf-8")
        if include_pack:
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
                "pesto_obfuscation_mode": "light",
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
    assert "--obfuscate=light" in command
    assert "--nzb-dir" in command
    assert command[command.index("--ext") + 1] == "avi,m2ts,m4v,mkv,mov,mp4,ts,webm,wmv"
    assert Path(command[command.index("--compress-temp-dir") + 1]).parts[-2:] == ("usenet", "pesto-compress")
    assert "--out" not in command
    assert "--compress=7z" in command
    assert command[command.index("--compress-volume-size") + 1] == "100m"
    assert "--password=pack-secret" in command
    assert command[command.index("--nzb-password") + 1] == "pack-secret"
    assert command[-1] == str(season_dir.resolve())
    assert captured["cwd"] == str(season_dir)
    assert isinstance(captured["env"], dict)
    assert Path(captured["config_root"]).parts[-2:] == ("usenet", "pesto-config")
    assert captured["archive_dir_exists"] is True
    staged_7z_dir = Path(captured["env"]["PATH"].split(os.pathsep)[0])
    assert staged_7z_dir.name == "pesto-bin"
    expected_episode_names = [
        "Show.S01E01.1080p.WEB-DL-GROUP.nzb",
        "Show.S01E02.1080p.WEB-DL-GROUP.nzb",
    ]
    expected_names = expected_episode_names + ([f"{season_dir.name}.nzb"] if include_pack else [])
    expected_result = output_dir / (f"{season_dir.name}.nzb" if include_pack else expected_episode_names[0])
    assert result == expected_result
    assert meta.usenet_pack_nzb_path == (str(output_dir / f"{season_dir.name}.nzb") if include_pack else None)
    assert [Path(path).name for path in meta.usenet_nzb_paths] == expected_names
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
        mediainfo={"media": {"track": [{"@type": "General", "Duration": "pack"}]}},
        tracker_image_collections={"CURUPIRA": {"screenshots": [{"raw_url": "pack.png"}]}},
        usenet_nzb_paths=[str(episode_nzb), str(pack_nzb)],
        usenet_pack_nzb_path=str(pack_nzb),
    )

    async def fake_export_info(*_args, **_kwargs):
        return {"media": {"track": []}}

    monkeypatch.setattr("src.exportmi.export_info", fake_export_info)
    submissions = await usenetcreate.build_usenet_indexer_metas(meta, [str(episode_nzb), str(pack_nzb)], ["CURUPIRA"], str(pack_nzb))

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
    assert episode_meta.usenet_is_pack is False
    assert episode_meta.usenet_is_episode_submission is True
    assert episode_meta.path == str(episode_file)
    assert episode_meta.filelist == [str(episode_file)]
    assert episode_meta.tracker_status == {"CURUPIRA": {}}
    assert episode_meta.uuid != meta.uuid
    assert episode_meta.usenet_media_source == str(episode_file)
    assert episode_meta.mediainfo == {"media": {"track": []}}
    assert episode_meta.tracker_image_collections == {}
    assert pack_meta is not meta
    assert pack_meta.nzb_path == str(pack_nzb)
    assert pack_meta.tv_pack is True
    assert pack_meta.usenet_is_pack is True
    assert pack_meta.usenet_is_episode_submission is False


@pytest.mark.asyncio
async def test_build_usenet_indexer_metas_keeps_all_episodes_when_pack_is_missing(tmp_path: Path, monkeypatch) -> None:
    season_dir = tmp_path / "Show.S01"
    season_dir.mkdir()
    episode_file = season_dir / "Show.S01E01.mkv"
    episode_file.write_bytes(b"video")
    episode_nzb = tmp_path / "Show.S01E01.nzb"
    meta = Meta(
        path=str(season_dir),
        category="TV",
        tv_pack=True,
        usenet_nzb_paths=[str(episode_nzb)],
    )

    monkeypatch.setattr("src.exportmi.export_info", AsyncMock(return_value={"media": {"track": []}}))

    submissions = await usenetcreate.build_usenet_indexer_metas(meta, meta.usenet_nzb_paths, ["CURUPIRA"], None)

    assert len(submissions) == 1
    assert submissions[0].nzb_path == str(episode_nzb)
    assert submissions[0].tv_pack is False
    assert submissions[0].usenet_is_pack is False


@pytest.mark.asyncio
async def test_build_usenet_indexer_metas_marks_regular_single_nzb_as_pack() -> None:
    meta = Meta(nzb_path="release.nzb")

    submissions = await usenetcreate.build_usenet_indexer_metas(meta, ["release.nzb"], ["CURUPIRA"])

    assert len(submissions) == 1
    assert submissions[0].usenet_is_pack is True


@pytest.mark.asyncio
async def test_pesto_rebuilds_missing_pack_from_saved_episode_nzbs(tmp_path: Path, monkeypatch) -> None:
    season_dir = tmp_path / "Show.S01"
    season_dir.mkdir()
    for episode in ("Show.S01E01", "Show.S01E02"):
        (season_dir / f"{episode}.mkv").write_bytes(b"video")

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    valid_nzb = "<nzb>" + (" " * 100) + "</nzb>"
    for episode in ("Show.S01E01", "Show.S01E02"):
        (output_dir / f"{episode}.nzb").write_text(valid_nzb, encoding="utf-8")

    async def fake_check_binary(binary_name, *_args, **_kwargs):
        return binary_name

    async def fake_run_pesto(cmd, **_kwargs):
        assert "--merge-season" in cmd
        assert "tmdb:tv:123" in cmd
        assert "imdb:tt1234567" in cmd
        merge_dir = Path(cmd[cmd.index("--merge-season") + 1])
        (merge_dir / "Show.S01.nzb").write_text(valid_nzb, encoding="utf-8")

    monkeypatch.setattr(usenetcreate, "check_binary", fake_check_binary)
    monkeypatch.setattr(usenetcreate, "run_pesto_with_progress", fake_run_pesto)
    meta = Meta(
        base_dir=str(tmp_path),
        path=str(season_dir),
        uuid="season-retry",
        basename_no_ext=season_dir.name,
        category="TV",
        tv_pack=True,
        archive_password="pack-secret",  # noqa: S106
        tmdb_id=123,
        imdb_tt="tt1234567",
    )

    result = await usenetcreate.prepare_and_upload_usenet(
        meta,
        {
            "USENET": {
                "usenet_uploader": "pesto",
                "pesto_season_upload": True,
                "nzb_output_dir": str(output_dir),
            }
        },
    )

    expected_pack = output_dir / f"{season_dir.name}.nzb"
    assert result == expected_pack
    assert meta.usenet_pack_nzb_path == str(expected_pack)
    assert [Path(path).name for path in meta.usenet_nzb_paths] == ["Show.S01E01.nzb", "Show.S01E02.nzb", "Show.S01.nzb"]
    assert await usenetcreate.verify_nzb_has_password(str(expected_pack)) is True


def test_episode_upload_summary_records_real_uploads_without_pack() -> None:
    meta = Meta(tracker_status={"CURUPIRA": {}})

    usenetcreate.apply_episode_upload_summary(meta, {"CURUPIRA": []}, {"CURUPIRA": 2}, {"CURUPIRA": 0}, {"CURUPIRA": 0}, set())

    assert meta.tracker_status["CURUPIRA"]["upload_success"] is True
    assert meta.tracker_status["CURUPIRA"]["status_message"] == "2 episode NZB upload(s) succeeded"


def test_episode_upload_summary_does_not_treat_duplicates_as_uploads() -> None:
    meta = Meta(tracker_status={"CURUPIRA": {}})

    usenetcreate.apply_episode_upload_summary(meta, {"CURUPIRA": []}, {"CURUPIRA": 0}, {"CURUPIRA": 2}, {"CURUPIRA": 0}, {"CURUPIRA"})

    assert meta.tracker_status["CURUPIRA"]["dupe"] is True
    assert meta.tracker_status["CURUPIRA"]["upload_success"] is False


def test_episode_upload_summary_does_not_call_mixed_duplicates_and_skips_all_duplicate() -> None:
    meta = Meta(tracker_status={"CURUPIRA": {"dupe": True}})

    usenetcreate.apply_episode_upload_summary(meta, {"CURUPIRA": []}, {"CURUPIRA": 0}, {"CURUPIRA": 1}, {"CURUPIRA": 1}, {"CURUPIRA"})

    assert meta.tracker_status["CURUPIRA"]["dupe"] is False
    assert meta.tracker_status["CURUPIRA"]["upload_success"] is False
    assert "1 duplicate, 1 skipped" in meta.tracker_status["CURUPIRA"]["status_message"]


def test_episode_only_indexer_filter_applies_only_to_pack() -> None:
    trackers = ["CURUPIRA", "NZBNEST", "NZBGEEK"]
    episodes_only = {"CURUPIRA", "NZBGEEK"}

    assert usenetcreate.select_usenet_indexers_for_submission(trackers, episodes_only, is_pack=False) == trackers
    assert usenetcreate.select_usenet_indexers_for_submission(trackers, episodes_only, is_pack=True) == ["NZBNEST"]


def test_episode_indexers_do_not_bypass_declined_upload() -> None:
    trackers = ["CURUPIRA", "NZBNEST", "NZBGEEK"]
    statuses = {
        "CURUPIRA": {"upload": False, "dupe": False},
        "NZBNEST": {"upload": False, "dupe": True},
        "NZBGEEK": {"upload": True, "dupe": False},
    }

    assert usenetcreate.select_usenet_episode_indexers(trackers, statuses, {"CURUPIRA", "NZBNEST"}) == ["NZBNEST", "NZBGEEK"]


@pytest.mark.asyncio
async def test_episode_screenshots_capture_and_host_configured_count(tmp_path: Path, monkeypatch) -> None:
    video = tmp_path / "Show.S01E01.mkv"
    video.write_bytes(b"video")
    captures = [str(tmp_path / f"screen-{index}.png") for index in range(3)]
    for capture in captures:
        Path(capture).write_bytes(b"png")
    uploaded = [{"img_url": f"thumb-{index}", "raw_url": f"raw-{index}", "web_url": f"web-{index}"} for index in range(3)]

    screenshot_mock = AsyncMock(return_value=captures)
    upload_mock = AsyncMock(return_value=(uploaded, 3))
    monkeypatch.setattr("src.takescreens.TakeScreensManager.screenshots", screenshot_mock)
    monkeypatch.setattr("src.uploadscreens.UploadScreensManager.upload_screens", upload_mock)

    meta = Meta(
        base_dir=str(tmp_path),
        uuid="episode-screens",
        name="Show.S01E01",
        category="TV",
        screens=3,
        usenet_media_source=str(video),
        imghost="imgbox",
    )
    count = await usenetcreate.prepare_usenet_episode_screenshots(meta, {"DEFAULT": {"img_host_1": "imgbox"}})

    assert count == 3
    assert meta.image_list == uploaded
    assert screenshot_mock.await_args.kwargs["num_screens"] == 3
    assert upload_mock.await_args.args[1] == 3


@pytest.mark.asyncio
async def test_episode_screenshots_keep_working_directory(tmp_path: Path, monkeypatch) -> None:
    starting_dir = tmp_path / "working"
    screenshot_dir = tmp_path / "tmp" / "episode-screens" / "screenshots"
    starting_dir.mkdir()
    screenshot_dir.mkdir(parents=True)
    video = tmp_path / "Show.S01E01.mkv"
    capture = screenshot_dir / "screen.png"
    video.write_bytes(b"video")
    capture.write_bytes(b"png")
    monkeypatch.chdir(starting_dir)

    async def upload_from_screenshot_dir(*_args, **_kwargs):
        return ([{"img_url": "thumb", "raw_url": "raw", "web_url": "web"}], 1)

    monkeypatch.setattr("src.takescreens.TakeScreensManager.screenshots", AsyncMock(return_value=[str(capture)]))
    monkeypatch.setattr("src.uploadscreens.UploadScreensManager.upload_screens", upload_from_screenshot_dir)
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="episode-screens",
        name="Show.S01E01",
        category="TV",
        screens=1,
        usenet_media_source=str(video),
        imghost="imgbox",
    )

    await usenetcreate.prepare_usenet_episode_screenshots(meta, {"DEFAULT": {"img_host_1": "imgbox"}})

    assert Path.cwd() == starting_dir


@pytest.mark.asyncio
async def test_episode_screenshots_fail_when_not_all_are_hosted(tmp_path: Path, monkeypatch) -> None:
    video = tmp_path / "Show.S01E01.mkv"
    video.write_bytes(b"video")
    captures = [str(tmp_path / f"screen-{index}.png") for index in range(2)]
    for capture in captures:
        Path(capture).write_bytes(b"png")

    monkeypatch.setattr("src.takescreens.TakeScreensManager.screenshots", AsyncMock(return_value=captures))
    meta = Meta(base_dir=str(tmp_path), uuid="episode-screens", name="Show.S01E01", category="TV", screens=3, usenet_media_source=str(video))

    with pytest.raises(RuntimeError, match="2/3 screenshots were captured"):
        await usenetcreate.prepare_usenet_episode_screenshots(meta, {"DEFAULT": {}})
