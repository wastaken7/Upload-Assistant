"""Regression tests for XXX contact-sheet screenshot capture."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from src import takescreens
from src.meta import Meta
from src.screenshot_manifest import files as manifest_files


def test_xxx_contact_sheet_settings_have_expected_defaults():
    takescreens._apply_config({"DEFAULT": {}})

    assert takescreens.xxx_contact_sheet_settings() == (12, 5, 6)


def test_xxx_contact_sheet_settings_allow_overrides():
    takescreens._apply_config({"DEFAULT": {"xxx_contact_sheet_rows": "3", "xxx_contact_sheet_columns": 4, "xxx_contact_sheet_max_videos": "2"}})

    assert takescreens.xxx_contact_sheet_settings() == (3, 4, 2)


def test_xxx_contact_sheet_animation_defaults_to_a_five_second_webp_option():
    takescreens._apply_config({"DEFAULT": {"xxx_contact_sheet_animated_webp": True}})

    assert takescreens.xxx_contact_sheet_animation_settings() == (True, 5.0)


def test_xxx_contact_sheet_timestamp_formatting():
    assert takescreens._format_contact_sheet_timestamp(3661.9) == "01:01:01"


@pytest.mark.asyncio
async def test_xxx_contact_sheets_create_one_grid_per_video_up_to_configured_limit(tmp_path, monkeypatch):
    videos = []
    for index in range(3):
        video = tmp_path / f"OnlyFans.Creator.{index}.mp4"
        video.write_bytes(b"video")
        videos.append(str(video))

    takescreens._apply_config({"DEFAULT": {"xxx_contact_sheet_rows": 2, "xxx_contact_sheet_columns": 3, "xxx_contact_sheet_max_videos": 2}})
    commands = []

    def fake_probe(_path):
        return {"format": {"duration": "60"}, "streams": [{"codec_type": "video"}]}

    async def fake_run_ffmpeg(command):
        commands.append(" ".join(takescreens.compile_ffmpeg_command(command)))
        output = Path(takescreens.get_ffmpeg_output_path(command, takescreens.compile_ffmpeg_command(command)))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"contact sheet")
        return 0, b"", b""

    monkeypatch.setattr(takescreens.ffmpeg, "probe", fake_probe)
    monkeypatch.setattr(takescreens, "run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(takescreens, "_xxx_contact_sheet_fontfile", lambda: "C:/Windows/Fonts/arial.ttf")
    meta = Meta(base_dir=str(tmp_path), uuid="xxx-release", category="XXX")

    sheets = await takescreens.xxx_contact_sheets(videos, meta.uuid, meta.base_dir, meta)

    assert len(sheets) == 2
    assert meta.screens == 2
    assert len(manifest_files(meta.base_dir, meta.uuid, "main")) == 2
    assert all("tile=layout=3x2" in command for command in commands)
    assert all("drawtext" in command for command in commands)
    assert all("fontfile" in command for command in commands)
    assert all("pts" in command for command in commands)


@pytest.mark.asyncio
async def test_animated_xxx_contact_sheet_is_registered_as_webp(tmp_path, monkeypatch):
    video = tmp_path / "OnlyFans.Creator.mp4"
    video.write_bytes(b"video")
    takescreens._apply_config({"DEFAULT": {"xxx_contact_sheet_rows": 1, "xxx_contact_sheet_columns": 2, "xxx_contact_sheet_animated_webp": True}})
    commands = []

    def fake_probe(_path):
        return {"format": {"duration": "60"}, "streams": [{"codec_type": "video"}]}

    async def fake_run_ffmpeg(command):
        command_args = takescreens.compile_ffmpeg_command(command)
        commands.append(" ".join(command_args))
        output = Path(takescreens.get_ffmpeg_output_path(command, command_args))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"animated webp")
        return 0, b"", b""

    monkeypatch.setattr(takescreens.ffmpeg, "probe", fake_probe)
    monkeypatch.setattr(takescreens, "run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(takescreens, "_xxx_contact_sheet_fontfile", lambda: "C:/Windows/Fonts/arial.ttf")
    meta = Meta(base_dir=str(tmp_path), uuid="animated-xxx", category="XXX")

    sheets = await takescreens.xxx_contact_sheets([str(video)], meta.uuid, meta.base_dir, meta)

    assert len(sheets) == 1
    assert Path(sheets[0]).suffix == ".webp"
    assert "libwebp_anim" in commands[0]
    assert "-t 5.0" in commands[0]
    assert "drawtext" in commands[0]


@pytest.mark.asyncio
async def test_xxx_fallback_cover_uses_a_video_frame(tmp_path, monkeypatch):
    video = tmp_path / "OnlyFans.Creator.mp4"
    video.write_bytes(b"video")
    commands = []

    def fake_probe(_path):
        return {"format": {"duration": "60"}, "streams": [{"codec_type": "video"}]}

    async def fake_run_ffmpeg(command):
        command_args = takescreens.compile_ffmpeg_command(command)
        commands.append(" ".join(command_args))
        output = Path(takescreens.get_ffmpeg_output_path(command, command_args))
        output.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (120, 80), "purple").save(output, format="PNG")
        return 0, b"", b""

    monkeypatch.setattr(takescreens.ffmpeg, "probe", fake_probe)
    monkeypatch.setattr(takescreens, "run_ffmpeg", fake_run_ffmpeg)
    meta = Meta(base_dir=str(tmp_path), uuid="fallback-cover", category="XXX")

    cover = await takescreens.xxx_fallback_cover([str(video)], meta.uuid, meta.base_dir, meta)

    assert cover == str(tmp_path / "tmp" / "fallback-cover" / "artwork" / "POSTER.png")
    assert meta.artwork_path == cover
    assert meta.artwork_url == ""
    assert "scale=1200:-2:force_original_aspect_ratio=decrease" in commands[0]
    assert "-ss 6.0" in commands[0]


@pytest.mark.asyncio
async def test_xxx_fallback_cover_skips_unprobeable_candidates(tmp_path, monkeypatch):
    invalid = tmp_path / "release.mkv"
    video = tmp_path / "OnlyFans.Creator.mp4"
    invalid.write_bytes(b"nfo")
    video.write_bytes(b"video")
    probed = []

    def fake_probe(path):
        probed.append(Path(path).name)
        if Path(path) == invalid:
            return {"format": {"duration": "0"}, "streams": [{"codec_type": "video"}]}
        return {"format": {"duration": "60"}, "streams": [{"codec_type": "video"}]}

    async def fake_run_ffmpeg(command):
        command_args = takescreens.compile_ffmpeg_command(command)
        output = Path(takescreens.get_ffmpeg_output_path(command, command_args))
        output.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (120, 80), "purple").save(output, format="PNG")
        return 0, b"", b""

    monkeypatch.setattr(takescreens.ffmpeg, "probe", fake_probe)
    monkeypatch.setattr(takescreens, "run_ffmpeg", fake_run_ffmpeg)
    meta = Meta(base_dir=str(tmp_path), uuid="fallback-candidate", category="XXX")

    cover = await takescreens.xxx_fallback_cover([str(invalid), str(video)], meta.uuid, meta.base_dir, meta)

    assert cover is not None
    assert probed == [invalid.name, video.name]


@pytest.mark.asyncio
async def test_xxx_fallback_cover_skips_audio_only_candidates(tmp_path, monkeypatch):
    audio = tmp_path / "release.mkv"
    video = tmp_path / "OnlyFans.Creator.mp4"
    audio.write_bytes(b"audio")
    video.write_bytes(b"video")
    probed = []

    def fake_probe(path):
        probed.append(Path(path).name)
        if Path(path) == audio:
            return {"format": {"duration": "42"}, "streams": [{"codec_type": "audio"}]}
        return {"format": {"duration": "60"}, "streams": [{"codec_type": "video"}]}

    async def fake_run_ffmpeg(command):
        command_args = takescreens.compile_ffmpeg_command(command)
        output = Path(takescreens.get_ffmpeg_output_path(command, command_args))
        output.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (120, 80), "purple").save(output, format="PNG")
        return 0, b"", b""

    monkeypatch.setattr(takescreens.ffmpeg, "probe", fake_probe)
    monkeypatch.setattr(takescreens, "run_ffmpeg", fake_run_ffmpeg)
    meta = Meta(base_dir=str(tmp_path), uuid="fallback-audio-only", category="XXX")

    cover = await takescreens.xxx_fallback_cover([str(audio), str(video)], meta.uuid, meta.base_dir, meta)

    assert cover is not None
    assert probed == [audio.name, video.name]
