"""Regression tests for XXX contact-sheet screenshot capture."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from PIL import Image

from src import takescreens
from src.meta import Meta
from src.screenshot_manifest import entries as manifest_entries
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
    recorded = []

    def fake_probe(_path):
        return {"format": {"duration": "60"}, "streams": [{"codec_type": "video"}]}

    async def fake_run_ffmpeg(command):
        commands.append(" ".join(takescreens.compile_ffmpeg_command(command)))
        output = Path(takescreens.get_ffmpeg_output_path(command, takescreens.compile_ffmpeg_command(command)))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"contact sheet")
        return 0, b"", b""

    async def fake_record_event(family, **values):
        recorded.append((family, values))

    monkeypatch.setattr(takescreens.ffmpeg, "probe", fake_probe)
    monkeypatch.setattr(takescreens, "run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(takescreens, "_xxx_contact_sheet_fontfile", lambda: "C:/Windows/Fonts/arial.ttf")
    monkeypatch.setattr(takescreens, "record_event_async", fake_record_event)
    meta = Meta(base_dir=str(tmp_path), uuid="xxx-release", category="XXX")

    sheets = await takescreens.xxx_contact_sheets(videos, meta.uuid, meta.base_dir, meta)

    assert len(sheets) == 2
    assert all(Path(sheet).suffix == ".png" for sheet in sheets)
    assert meta.screens == 2
    assert len(manifest_files(meta.base_dir, meta.uuid, "main")) == 2
    # Each video: one seeking capture per tile, then one stack of the 3x2 grid.
    assert len(commands) == 2 * (6 + 1)
    tile_commands = [command for command in commands if "xxx-contact-sheet-" not in command]
    stack_commands = [command for command in commands if "xxx-contact-sheet-" in command]
    assert len(tile_commands) == 12
    assert all(command.count(" -i ") == 1 and "-ss " in command and "-vframes 1" in command for command in tile_commands)
    assert all("drawtext" in command and "fontfile" in command for command in tile_commands)
    assert all("vstack=inputs=2" in command and "hstack=inputs=3" in command for command in stack_commands)
    assert recorded == [("artifact", {"service": "screenshot", "operation": "created", "category": "standard", "count": 2})]


def test_static_tile_draws_a_literal_timestamp_after_scaling():
    """ffmpeg rejected the escaped pts expression, and text drawn before scaling was ~3 px tall."""
    tile = takescreens._xxx_contact_sheet_tile(Path("Studio.Scene.mp4"), 3661.9, 0.0, "C:/Windows/Fonts/arial.ttf")
    graph = takescreens.compile_ffmpeg_command(takescreens._ffmpeg.output(tile, "tile.png", vframes=1))
    filters = graph[graph.index("-filter_complex") + 1]

    assert "pts" not in filters
    assert "text=01\\\\:01\\\\:01:" in filters
    assert filters.index("scale=320:-2") < filters.index("drawtext")
    assert graph[graph.index("-ss") + 1] == "3661.9"


def test_contact_sheet_tiles_skip_the_opening_frame_and_stay_inside_the_video():
    starts = takescreens._xxx_contact_sheet_start_times(4, 100.0, 1.0)

    assert starts == pytest.approx([12.375, 37.125, 61.875, 86.625])
    assert starts[0] > 0
    assert starts[-1] < 100.0 - 1.0


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
    # Tiles are decoded one per ffmpeg run so only one decoder is in memory.
    *tile_commands, stack_command = commands
    assert len(tile_commands) == 2
    assert all(command.count(" -i ") == 1 for command in tile_commands)
    assert all("ffv1" in command and "drawtext" in command for command in tile_commands)
    assert stack_command.count(" -i ") == 2
    assert "libwebp_anim" in stack_command
    assert "-quality 75" in stack_command
    assert "-t 5.0" in stack_command
    assert "hstack" in stack_command
    # The intermediate clips are removed once the sheet is written.
    assert not list((tmp_path / "tmp" / meta.uuid).glob("xxx-tiles-*"))


@pytest.mark.asyncio
async def test_animated_xxx_contact_sheet_stops_when_a_tile_fails(tmp_path, monkeypatch):
    video = tmp_path / "Studio.Scene.mp4"
    video.write_bytes(b"video")
    takescreens._apply_config({"DEFAULT": {"xxx_contact_sheet_rows": 1, "xxx_contact_sheet_columns": 3, "xxx_contact_sheet_animated_webp": True}})
    commands = []

    def fake_probe(_path):
        return {"format": {"duration": "60"}, "streams": [{"codec_type": "video"}]}

    async def fake_run_ffmpeg(command):
        command_args = takescreens.compile_ffmpeg_command(command)
        commands.append(" ".join(command_args))
        output = Path(takescreens.get_ffmpeg_output_path(command, command_args))
        if len(commands) == 3:
            # run_ffmpeg writes its report beside the output.
            (output.parent / "ffmpeg-failed.log").write_text("decoder error")
            return 1, b"", b""
        output.write_bytes(b"tile clip")
        return 0, b"", b""

    monkeypatch.setattr(takescreens.ffmpeg, "probe", fake_probe)
    monkeypatch.setattr(takescreens, "run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(takescreens, "_xxx_contact_sheet_fontfile", lambda: None)
    meta = Meta(base_dir=str(tmp_path), uuid="failed-xxx", category="XXX")

    sheets = await takescreens.xxx_contact_sheets([str(video)], meta.uuid, meta.base_dir, meta)

    release_dir = tmp_path / "tmp" / meta.uuid
    assert sheets == []
    # The third tile fails after two clips exist; the stack step never runs.
    assert len(commands) == 3
    assert not any("libwebp_anim" in command for command in commands)
    assert not list(release_dir.glob("xxx-tiles-*"))
    # The failed tile's ffmpeg report outlives the removed tile directory.
    assert (release_dir / "ffmpeg-failed.log").read_text() == "decoder error"


@pytest.mark.asyncio
@pytest.mark.parametrize(("rows", "columns"), [(2, 1), (1, 1)])
async def test_animated_xxx_contact_sheet_skips_single_input_stacks(tmp_path, monkeypatch, rows, columns):
    video = tmp_path / "Studio.Clip.mp4"
    video.write_bytes(b"video")
    takescreens._apply_config({"DEFAULT": {"xxx_contact_sheet_rows": rows, "xxx_contact_sheet_columns": columns, "xxx_contact_sheet_animated_webp": True}})
    commands = []

    def fake_probe(_path):
        return {"format": {"duration": "60"}, "streams": [{"codec_type": "video"}]}

    async def fake_run_ffmpeg(command):
        command_args = takescreens.compile_ffmpeg_command(command)
        commands.append(" ".join(command_args))
        Path(takescreens.get_ffmpeg_output_path(command, command_args)).write_bytes(b"clip")
        return 0, b"", b""

    monkeypatch.setattr(takescreens.ffmpeg, "probe", fake_probe)
    monkeypatch.setattr(takescreens, "run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(takescreens, "_xxx_contact_sheet_fontfile", lambda: None)
    meta = Meta(base_dir=str(tmp_path), uuid=f"stack-{rows}x{columns}", category="XXX")

    sheets = await takescreens.xxx_contact_sheets([str(video)], meta.uuid, meta.base_dir, meta)

    stack_command = commands[-1]
    assert len(sheets) == 1
    # ffmpeg rejects hstack/vstack with inputs=1.
    assert "hstack" not in stack_command
    assert ("vstack=inputs=2" in stack_command) == (rows == 2)
    assert "inputs=1" not in stack_command


@pytest.mark.asyncio
async def test_xxx_single_file_screens_stay_fixed_across_reruns(tmp_path, monkeypatch):
    video = tmp_path / "Studio.Performer.mp4"
    video.write_bytes(b"video")
    takescreens._apply_config({"DEFAULT": {"xxx_contact_sheet_rows": 1, "xxx_contact_sheet_columns": 2, "xxx_single_file_screens": 2}})
    requested = []

    def fake_probe(_path):
        return {"format": {"duration": "60"}, "streams": [{"codec_type": "video"}]}

    async def fake_run_ffmpeg(command):
        command_args = takescreens.compile_ffmpeg_command(command)
        output = Path(takescreens.get_ffmpeg_output_path(command, command_args))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"contact sheet")
        return 0, b"", b""

    async def fake_screenshots(_path, _filename, folder_id, base_dir, _meta, num_screens, force_screenshots, *_args, capture_group="main", **_kwargs):
        requested.append((num_screens, force_screenshots))
        existing = len(manifest_files(base_dir, folder_id, capture_group))
        # A forced capture adds every requested frame; otherwise it tops up to the target.
        target = existing + num_screens if force_screenshots else num_screens
        frames = []
        for index in range(existing, target):
            frame = takescreens.screenshots_dir(base_dir, folder_id) / f"frame-{index}.png"
            frame.write_bytes(b"frame")
            frames.append(str(frame))
        takescreens.register_screenshots(base_dir, folder_id, frames, capture_group)

    monkeypatch.setattr(takescreens.ffmpeg, "probe", fake_probe)
    monkeypatch.setattr(takescreens, "run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(takescreens, "_xxx_contact_sheet_fontfile", lambda: "C:/Windows/Fonts/arial.ttf")
    monkeypatch.setattr(takescreens, "screenshots", fake_screenshots)
    meta = Meta(base_dir=str(tmp_path), uuid="xxx-rerun", category="XXX")

    for _run in range(3):
        await takescreens.xxx_contact_sheets([str(video)], meta.uuid, meta.base_dir, meta)

    assert requested == [(3, False)] * 3
    assert meta.screens == 3
    assert len(manifest_files(meta.base_dir, meta.uuid, "main")) == 3

    # Rehosting can still top up frames it has to replace.
    await takescreens.xxx_contact_sheets([str(video)], meta.uuid, meta.base_dir, meta, extra_screens=2)

    assert requested[-1] == (2, True)
    assert meta.screens == 5


def _fake_ffmpeg(monkeypatch, commands, sheet_bytes=b"contact sheet"):
    """Patch probe and ffmpeg so every output is written; sheet outputs get ``sheet_bytes``."""

    def fake_probe(_path):
        return {"format": {"duration": "60"}, "streams": [{"codec_type": "video"}]}

    async def fake_run_ffmpeg(command):
        command_args = takescreens.compile_ffmpeg_command(command)
        commands.append(" ".join(command_args))
        output = Path(takescreens.get_ffmpeg_output_path(command, command_args))
        output.parent.mkdir(parents=True, exist_ok=True)
        is_tile = output.name.startswith("tile-")
        output.write_bytes(b"tile" if is_tile else sheet_bytes(output) if callable(sheet_bytes) else sheet_bytes)
        return 0, b"", b""

    async def fake_record_event(_family, **_values):
        return None

    monkeypatch.setattr(takescreens.ffmpeg, "probe", fake_probe)
    monkeypatch.setattr(takescreens, "run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(takescreens, "_xxx_contact_sheet_fontfile", lambda: None)
    monkeypatch.setattr(takescreens, "record_event_async", fake_record_event)


@pytest.mark.asyncio
async def test_oversized_animated_sheet_lowers_quality_then_falls_back_to_png(tmp_path, monkeypatch):
    video = tmp_path / "Studio.Scene.mp4"
    video.write_bytes(b"video")
    takescreens._apply_config({"DEFAULT": {"xxx_contact_sheet_rows": 1, "xxx_contact_sheet_columns": 2, "xxx_contact_sheet_animated_webp": True}})
    monkeypatch.setattr(takescreens, "XXX_CONTACT_SHEET_MAX_BYTES", 10)
    commands = []
    # Every WebP is too large; the PNG fits.
    _fake_ffmpeg(monkeypatch, commands, lambda output: b"x" * 50 if output.suffix == ".webp" else b"png")
    meta = Meta(base_dir=str(tmp_path), uuid="oversized-xxx", category="XXX")

    sheets = await takescreens.xxx_contact_sheets([str(video)], meta.uuid, meta.base_dir, meta)

    webp_commands = [command for command in commands if "libwebp_anim" in command]
    assert [command.split("-quality ")[1].split()[0] for command in webp_commands] == ["75", "60", "45", "30"]
    assert len(sheets) == 1
    assert Path(sheets[0]).suffix == ".png"
    assert not list(takescreens.screenshots_dir(meta.base_dir, meta.uuid).glob("*.webp"))


@pytest.mark.asyncio
async def test_animated_sheet_stops_lowering_quality_once_it_fits(tmp_path, monkeypatch):
    video = tmp_path / "Studio.Scene.mp4"
    video.write_bytes(b"video")
    takescreens._apply_config({"DEFAULT": {"xxx_contact_sheet_rows": 1, "xxx_contact_sheet_columns": 2, "xxx_contact_sheet_animated_webp": True}})
    monkeypatch.setattr(takescreens, "XXX_CONTACT_SHEET_MAX_BYTES", 10)
    commands = []
    sizes = iter([50, 5])
    _fake_ffmpeg(monkeypatch, commands, lambda _output: b"x" * next(sizes))
    meta = Meta(base_dir=str(tmp_path), uuid="fits-xxx", category="XXX")

    sheets = await takescreens.xxx_contact_sheets([str(video)], meta.uuid, meta.base_dir, meta)

    assert len([command for command in commands if "libwebp_anim" in command]) == 2
    assert Path(sheets[0]).suffix == ".webp"


@pytest.mark.asyncio
async def test_cached_sheets_are_marked_and_regenerated_when_settings_change(tmp_path, monkeypatch):
    video = tmp_path / "Studio.Scene.mp4"
    video.write_bytes(b"video")
    commands = []
    _fake_ffmpeg(monkeypatch, commands)
    meta = Meta(base_dir=str(tmp_path), uuid="cached-xxx", category="XXX")

    takescreens._apply_config({"DEFAULT": {"xxx_contact_sheet_rows": 1, "xxx_contact_sheet_columns": 2}})
    first = await takescreens.xxx_contact_sheets([str(video)], meta.uuid, meta.base_dir, meta)
    entries = manifest_entries(meta.base_dir, meta.uuid, "main")
    assert entries[0][1]["kind"] == takescreens.XXX_CONTACT_SHEET_KIND
    assert entries[0][1]["source"] == str(video)
    assert takescreens.is_xxx_contact_sheet(meta.base_dir, meta.uuid, Path(first[0]))

    commands.clear()
    assert await takescreens.xxx_contact_sheets([str(video)], meta.uuid, meta.base_dir, meta) == first
    assert commands == []

    takescreens._apply_config({"DEFAULT": {"xxx_contact_sheet_rows": 1, "xxx_contact_sheet_columns": 2, "xxx_contact_sheet_animated_webp": True}})
    second = await takescreens.xxx_contact_sheets([str(video)], meta.uuid, meta.base_dir, meta)

    assert Path(second[0]).suffix == ".webp"
    assert not Path(first[0]).exists()
    assert manifest_files(meta.base_dir, meta.uuid, "main") == [Path(second[0])]


@pytest.mark.asyncio
async def test_unmarked_screenshots_from_older_runs_are_regenerated(tmp_path, monkeypatch):
    video = tmp_path / "Studio.Scene.mp4"
    video.write_bytes(b"video")
    takescreens._apply_config({"DEFAULT": {"xxx_contact_sheet_rows": 1, "xxx_contact_sheet_columns": 2}})
    commands = []
    _fake_ffmpeg(monkeypatch, commands)
    meta = Meta(base_dir=str(tmp_path), uuid="legacy-xxx", category="XXX")
    legacy = takescreens.screenshots_dir(meta.base_dir, meta.uuid) / "old-sheet.png"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(b"old sheet")
    (old,) = takescreens.register_screenshots(meta.base_dir, meta.uuid, [legacy], "main")

    sheets = await takescreens.xxx_contact_sheets([str(video)], meta.uuid, meta.base_dir, meta)

    assert not old.exists()
    assert manifest_files(meta.base_dir, meta.uuid, "main") == [Path(sheets[0])]
    assert takescreens.is_xxx_contact_sheet(meta.base_dir, meta.uuid, Path(sheets[0]))


@pytest.mark.asyncio
async def test_deleted_sheet_is_not_replaced_by_a_single_frame(tmp_path, monkeypatch):
    video = tmp_path / "Studio.Performer.mp4"
    video.write_bytes(b"video")
    takescreens._apply_config({"DEFAULT": {"xxx_contact_sheet_rows": 1, "xxx_contact_sheet_columns": 2, "xxx_single_file_screens": 1}})
    commands = []
    _fake_ffmpeg(monkeypatch, commands)

    async def fake_screenshots(_path, _filename, folder_id, base_dir, _meta, num_screens, _force, *_args, capture_group="main", **_kwargs):
        existing = len(manifest_files(base_dir, folder_id, capture_group))
        frames = []
        for index in range(existing, num_screens):
            frame = takescreens.screenshots_dir(base_dir, folder_id) / f"frame-{index}.png"
            frame.write_bytes(b"frame")
            frames.append(str(frame))
        takescreens.register_screenshots(base_dir, folder_id, frames, capture_group)

    monkeypatch.setattr(takescreens, "screenshots", fake_screenshots)
    meta = Meta(base_dir=str(tmp_path), uuid="deleted-sheet", category="XXX")
    (sheet,) = await takescreens.xxx_contact_sheets([str(video)], meta.uuid, meta.base_dir, meta)
    frame = next(path for path in manifest_files(meta.base_dir, meta.uuid, "main") if str(path) != sheet)

    # The Web UI review deletes the sheet and keeps the frame.
    takescreens.discard_screenshot_file(meta.base_dir, meta.uuid, Path(sheet))
    (new_sheet,) = await takescreens.xxx_contact_sheets([str(video)], meta.uuid, meta.base_dir, meta)

    assert Path(new_sheet) != frame
    assert takescreens.is_xxx_contact_sheet(meta.base_dir, meta.uuid, Path(new_sheet))
    assert frame in manifest_files(meta.base_dir, meta.uuid, "main")


@pytest.mark.asyncio
async def test_retake_keeps_the_new_sheet_when_single_frames_are_added(tmp_path, monkeypatch):
    video = tmp_path / "Studio.Performer.mp4"
    video.write_bytes(b"video")
    takescreens._apply_config({"DEFAULT": {"xxx_contact_sheet_rows": 1, "xxx_contact_sheet_columns": 2, "xxx_single_file_screens": 1}})
    commands = []
    _fake_ffmpeg(monkeypatch, commands)
    retake_seen = []

    async def fake_screenshots(_path, _filename, folder_id, base_dir, meta, num_screens, _force, *_args, capture_group="main", **_kwargs):
        retake_seen.append(meta.retake)
        if meta.retake:
            takescreens.clear_screenshot_group(base_dir, folder_id, capture_group)
        frame = takescreens.screenshots_dir(base_dir, folder_id) / "frame.png"
        frame.write_bytes(b"frame")
        takescreens.register_screenshots(base_dir, folder_id, [frame], capture_group)

    monkeypatch.setattr(takescreens, "screenshots", fake_screenshots)
    meta = Meta(base_dir=str(tmp_path), uuid="retake-xxx", category="XXX", retake=True)

    (sheet,) = await takescreens.xxx_contact_sheets([str(video)], meta.uuid, meta.base_dir, meta)

    assert retake_seen == [False]
    assert meta.retake is True
    assert Path(sheet).is_file()
    assert Path(sheet) in manifest_files(meta.base_dir, meta.uuid, "main")
    assert meta.screens == 2


@pytest.mark.asyncio
async def test_a_stalled_ffmpeg_fails_the_sheet_instead_of_hanging(tmp_path, monkeypatch):
    video = tmp_path / "Studio.Scene.mp4"
    video.write_bytes(b"video")
    takescreens._apply_config({"DEFAULT": {"xxx_contact_sheet_rows": 1, "xxx_contact_sheet_columns": 2}})
    commands = []
    _fake_ffmpeg(monkeypatch, commands)
    cancelled = []

    async def stalled_ffmpeg(_command):
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    monkeypatch.setattr(takescreens, "run_ffmpeg", stalled_ffmpeg)
    monkeypatch.setattr(takescreens, "_XXX_FFMPEG_TIMEOUT_SECONDS", 0.01)
    meta = Meta(base_dir=str(tmp_path), uuid="stalled-xxx", category="XXX")

    assert await takescreens.xxx_contact_sheets([str(video)], meta.uuid, meta.base_dir, meta) == []
    assert cancelled == [True]


def test_replace_file_keeps_the_old_file_when_the_manifest_save_fails(tmp_path, monkeypatch):
    from src import screenshot_manifest

    screens = takescreens.screenshots_dir(tmp_path, "save-fails")
    screens.mkdir(parents=True, exist_ok=True)
    old = screens / "sheet.webp"
    old.write_bytes(b"old")
    (registered,) = takescreens.register_screenshots(tmp_path, "save-fails", [old], "main")
    new = screens / "new.png"
    new.write_bytes(b"new")

    def failing_save(*_args):
        raise OSError("disk full")

    monkeypatch.setattr(screenshot_manifest, "_save", failing_save)
    with pytest.raises(OSError, match="disk full"):
        screenshot_manifest.replace_file(tmp_path, "save-fails", registered, new)

    assert registered.read_bytes() == b"old"
    assert manifest_files(tmp_path, "save-fails", "main") == [registered]


@pytest.mark.asyncio
async def test_regenerating_a_sheet_keeps_its_entry_and_uses_its_video(tmp_path, monkeypatch):
    videos = [tmp_path / f"Studio.Scene.{index}.mp4" for index in range(2)]
    for video in videos:
        video.write_bytes(b"video")
    takescreens._apply_config({"DEFAULT": {"xxx_contact_sheet_rows": 1, "xxx_contact_sheet_columns": 2}})
    commands = []
    _fake_ffmpeg(monkeypatch, commands)
    meta = Meta(base_dir=str(tmp_path), uuid="regenerate-xxx", category="XXX")
    sheets = await takescreens.xxx_contact_sheets([str(video) for video in videos], meta.uuid, meta.base_dir, meta)

    commands.clear()
    regenerated = await takescreens.regenerate_xxx_contact_sheet(meta.base_dir, meta.uuid, Path(sheets[1]), meta)

    assert regenerated == Path(sheets[1])
    assert all(str(videos[1]) in command for command in commands if "-ss " in command)
    assert manifest_files(meta.base_dir, meta.uuid, "main") == [Path(sheet) for sheet in sheets]
    assert not [path for path in takescreens.screenshots_dir(meta.base_dir, meta.uuid).iterdir() if path.name.startswith(".")]

    frame = takescreens.screenshots_dir(meta.base_dir, meta.uuid) / "frame.png"
    frame.write_bytes(b"frame")
    (registered_frame,) = takescreens.register_screenshots(meta.base_dir, meta.uuid, [frame], "main")
    assert await takescreens.regenerate_xxx_contact_sheet(meta.base_dir, meta.uuid, registered_frame, meta) is None


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
async def test_regenerated_xxx_cover_frame_is_reused_in_later_runs(tmp_path, monkeypatch):
    """A cover picked with the Web UI button is rebuilt from the same frame on the next run."""
    from src.artwork import COVER_FRAME_ANSWER, remember_cover_frame

    video = tmp_path / "Fictional.Scene.mp4"
    video.write_bytes(b"video")
    commands: list[str] = []

    async def fake_run_ffmpeg(command):
        command_args = takescreens.compile_ffmpeg_command(command)
        commands.append(" ".join(command_args))
        output = Path(takescreens.get_ffmpeg_output_path(command, command_args))
        output.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (120, 80), "purple").save(output, format="PNG")
        return 0, b"", b""

    monkeypatch.setattr(takescreens.ffmpeg, "probe", lambda _path: {"format": {"duration": "60"}, "streams": [{"codec_type": "video"}]})
    monkeypatch.setattr(takescreens, "run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(takescreens.secrets.SystemRandom, "uniform", lambda _self, _low, _high: 33.25)

    # The Web UI server regenerates from its own copy of meta.
    server_meta = Meta(base_dir=str(tmp_path), uuid="release", category="XXX")
    assert await takescreens.xxx_fallback_cover([str(video)], server_meta.uuid, server_meta.base_dir, server_meta, random_frame=True)
    assert "-ss 33.25" in commands[-1]

    # The upload process picks the choice up before it saves the release's answers.
    upload_meta = Meta(base_dir=str(tmp_path), uuid="release", category="XXX")
    remember_cover_frame(upload_meta)
    assert upload_meta.manual_answers[COVER_FRAME_ANSWER] == 33.25

    # A later run, with the saved answers reloaded, uses that frame instead of the default one.
    later_meta = Meta(base_dir=str(tmp_path / "later"), uuid="release", category="XXX", manual_answers={COVER_FRAME_ANSWER: 33.25})
    assert await takescreens.xxx_fallback_cover([str(video)], later_meta.uuid, later_meta.base_dir, later_meta)
    assert "-ss 33.25" in commands[-1]

    # A saved frame past the end of the video is ignored.
    short_meta = Meta(base_dir=str(tmp_path / "short"), uuid="release", category="XXX", manual_answers={COVER_FRAME_ANSWER: 90})
    assert await takescreens.xxx_fallback_cover([str(video)], short_meta.uuid, short_meta.base_dir, short_meta)
    assert "-ss 6.0" in commands[-1]


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


def test_flat_release_keeps_its_first_videos_for_contact_sheets(tmp_path):
    videos = [tmp_path / f"Scene.{index}.mp4" for index in range(5)]

    assert takescreens._select_xxx_contact_sheet_videos(videos, 3) == videos[:3]


def test_nested_pack_spreads_contact_sheets_across_folders(tmp_path):
    part_one = [tmp_path / "Part 1" / f"Scene.{index}.mp4" for index in range(4)]
    part_two = [tmp_path / "Part 2" / f"Scene.{index}.mp4" for index in range(4)]
    part_three = [tmp_path / "Part 3" / "Scene.0.mp4"]
    videos = [tmp_path / "Root.Scene.mp4", *part_one, *part_two, *part_three]

    selected = takescreens._select_xxx_contact_sheet_videos(videos, 5)

    # One from each folder first, then a second round.
    assert selected == [videos[0], part_one[0], part_two[0], part_three[0], part_one[1]]


def test_contact_sheet_selection_is_a_prefix_of_any_larger_limit(tmp_path):
    # Cached sheets are reused by position, so a lower limit must not reorder them.
    videos = [tmp_path / part / f"Scene.{index}.mp4" for part in ("Part 1", "Part 2", "Part 3") for index in range(3)]
    selections = [takescreens._select_xxx_contact_sheet_videos(videos, limit) for limit in range(1, len(videos) + 2)]

    for smaller, larger in zip(selections, selections[1:], strict=False):
        assert larger[: len(smaller)] == smaller
    assert sorted(selections[-1]) == sorted(videos)


def test_contact_sheet_selection_ignores_duplicate_paths(tmp_path):
    part_one = tmp_path / "Part 1" / "Scene.mp4"
    part_two = tmp_path / "Part 2" / "Scene.mp4"

    assert takescreens._select_xxx_contact_sheet_videos([part_one, part_one, part_one, part_two], 3) == [part_one, part_two]


def test_nested_pack_contact_sheet_titles_show_the_subfolder(tmp_path):
    root = tmp_path / "Studio Pack"
    videos = [root / "Root.Scene.mp4", root / "Part 1" / "Scene.mp4"]

    assert takescreens._xxx_contact_sheet_titles(videos, str(root)) == {videos[0]: "Root.Scene.mp4", videos[1]: "Part 1/Scene.mp4"}
    assert takescreens._xxx_contact_sheet_titles(videos[1:], str(root)) == {videos[1]: "Scene.mp4"}
    assert takescreens._xxx_contact_sheet_titles(videos, None) == {videos[0]: "Root.Scene.mp4", videos[1]: "Scene.mp4"}


@pytest.mark.asyncio
async def test_nested_pack_contact_sheets_cover_each_part(tmp_path, monkeypatch):
    root = (tmp_path / "Studio Pack").resolve()
    videos = []
    for part in ("Part 1", "Part 2"):
        for index in range(3):
            video = root / part / f"Scene.{index}.mp4"
            video.parent.mkdir(parents=True, exist_ok=True)
            video.write_bytes(b"video")
            videos.append(str(video))
    takescreens._apply_config({"DEFAULT": {"xxx_contact_sheet_rows": 1, "xxx_contact_sheet_columns": 1, "xxx_contact_sheet_max_videos": 2}})
    commands = []

    def fake_probe(_path):
        return {"format": {"duration": "60"}, "streams": [{"codec_type": "video"}]}

    async def fake_run_ffmpeg(command):
        command_args = takescreens.compile_ffmpeg_command(command)
        commands.append(command_args)
        output = Path(takescreens.get_ffmpeg_output_path(command, command_args))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"contact sheet")
        return 0, b"", b""

    async def fake_record_event(_family, **_values):
        return None

    monkeypatch.setattr(takescreens.ffmpeg, "probe", fake_probe)
    monkeypatch.setattr(takescreens, "run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(takescreens, "_xxx_contact_sheet_fontfile", lambda: "C:/Windows/Fonts/arial.ttf")
    monkeypatch.setattr(takescreens, "record_event_async", fake_record_event)
    meta = Meta(base_dir=str(tmp_path), uuid="nested-xxx", category="XXX", path=str(root), isdir=True)

    sheets = await takescreens.xxx_contact_sheets(videos, meta.uuid, meta.base_dir, meta)

    assert len(sheets) == 2
    # The title is checked in the drawtext filter, not in the input path.
    # Each 1x1 sheet is one tile capture, then the titled stack.
    assert any("drawtext" in argument and "Part 1/Scene.0.mp4" in argument for argument in commands[1])
    assert any("drawtext" in argument and "Part 2/Scene.0.mp4" in argument for argument in commands[3])
