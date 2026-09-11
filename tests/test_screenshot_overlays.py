"""Regression coverage for independent overlays and legacy configuration."""

from types import SimpleNamespace
import asyncio

import pytest

from src.screenshot_overlays import OVERLAY_KEYS, format_timestamp, overlay_enabled, overlay_filters, overlay_lines, overlay_options, overlays_active


@pytest.mark.parametrize("key", OVERLAY_KEYS)
def test_overlay_switch_types_are_validated(key):
    from src.configvalidator import _validate_default_section

    _, warnings = _validate_default_section({'tmdb_api': 'test', key: True})
    assert not any(warning.key == key for warning in warnings)
    _, warnings = _validate_default_section({'tmdb_api': 'test', key: 'invalid'})
    assert any(warning.key == key for warning in warnings)


@pytest.mark.parametrize("legacy", [None, False, True, "False", "True"])
def test_legacy_defaults(legacy):
    defaults = {} if legacy is None else {"frame_overlay": legacy}
    options = overlay_options(defaults)
    expected = legacy in (True, "True")
    assert options == dict(zip(OVERLAY_KEYS, [expected, expected, False, expected], strict=True))


def test_explicit_switches_override_legacy_independently():
    options = overlay_options({"frame_overlay": True, "overlay_frame_number": False, "overlay_timestamp": True})
    assert options == dict(zip(OVERLAY_KEYS, [False, True, True, True], strict=True))
    assert not any(overlay_options({"frame_overlay": True, **dict.fromkeys(OVERLAY_KEYS, False)}).values())


def test_master_gates_output_without_clearing_label_preferences():
    config = {"frame_overlay": False, "overlay_timestamp": True}
    assert overlay_options(config)["overlay_timestamp"] is True
    assert not overlay_enabled(config)
    assert not overlays_active(config)
    meta = SimpleNamespace(frame_overlay=True)
    assert overlay_filters(config, meta, 20, True) == []
    config["frame_overlay"] = True
    assert overlays_active(config)
    assert not overlays_active({"frame_overlay": True, **dict.fromkeys(OVERLAY_KEYS, False)})
    assert overlay_enabled({"overlay_timestamp": True})


def test_single_line_format_orders_timestamp_before_picture_type():
    options = dict.fromkeys(OVERLAY_KEYS, True)
    assert overlay_lines(options, 58342, "B", "00:40:33.097", True, layout="single_line") == [
        "Frame 58342 • 00:40:33.097 • B-Frame • Tonemapped"
    ]
    options["overlay_frame_number"] = False
    options["overlay_frame_type"] = False
    assert overlay_lines(options, 58342, "B", "00:40:33.097", False, layout="single_line") == ["00:40:33.097"]
    assert overlay_lines({}, 0, "?", "00:00:00.000", True, layout="single_line") == []


@pytest.mark.parametrize("layout,count", [("stacked", 4), ("single_line", 1)])
@pytest.mark.parametrize("position", ["left", "right"])
def test_layout_and_alignment_reach_ffmpeg_filters(layout, count, position):
    config = {"frame_overlay": True, **dict.fromkeys(OVERLAY_KEYS, True), "overlay_position": position, "overlay_layout": layout}
    meta = SimpleNamespace(frame_overlay=True, frame_info_map={}, frame_rate=24, resolution="1080p")
    filters = overlay_filters(config, meta, 20, True)
    assert len(filters) == count
    assert all(f":x={'w-tw-10' if position == 'right' else '10'}:" in entry for entry in filters)
    assert ":y=10:" in filters[0]


def test_conditional_label_is_last_and_disabled_labels_leave_no_gaps():
    options = overlay_options({"overlay_timestamp": True, "overlay_tonemapped": True})
    assert overlay_lines(options, 24, "P", "00:00:01.000", True) == ["Timestamp: 00:00:01.000", "Tonemapped"]
    assert overlay_lines(options, 24, "P", "00:00:01.000", False) == ["Timestamp: 00:00:01.000"]


@pytest.mark.parametrize("seconds,expected", [(0, "00:00:00.000"), (2538.375, "00:42:18.375"), (3599.9999, "01:00:00.000")])
def test_timestamp_rounding(seconds, expected):
    assert format_timestamp(seconds) == expected


@pytest.mark.parametrize("dvd", [False, True])
def test_capture_filters_respect_selection_spacing_and_upload_suppression(dvd):
    meta = SimpleNamespace(frame_overlay=True, frame_info_map={}, frame_rate=24, resolution='576p' if dvd else '1080p')
    defaults = {"overlay_timestamp": True, "overlay_tonemapped": True}
    filters = overlay_filters(defaults, meta, 12.345, True, dvd=dvd)
    assert len(filters) == 2
    assert "Timestamp" in filters[0] and "pts\\:hms\\:12.345000" in filters[0]
    assert ":y=10:" in filters[0] and ":y=30:" in filters[1]
    assert "Tonemapped" in filters[1]
    assert len(overlay_filters(defaults, meta, 12.345, False, dvd=dvd)) == 1
    meta.frame_overlay = False
    assert overlay_filters(defaults, meta, 12.345, True, dvd=dvd) == []


def test_all_off_is_clean_even_with_stale_runtime_flag():
    meta = SimpleNamespace(frame_overlay=True, frame_info_map={}, frame_rate=24, resolution='1080p')
    assert overlay_filters({}, meta, 0, True) == []


@pytest.mark.parametrize("backend", ["video", "disc", "dvd"])
def test_timestamp_only_reaches_each_ffmpeg_capture_backend(tmp_path, monkeypatch, backend):
    import ffmpeg
    from src import takescreens
    from src.meta import Meta

    source = tmp_path / 'video.mkv'
    source.touch()
    output = tmp_path / 'capture.png'
    monkeypatch.setattr(takescreens, 'default_config', {'overlay_timestamp': True})
    monkeypatch.setattr(takescreens.MediaInfo, 'parse', lambda _: SimpleNamespace(tracks=[]))
    commands = []

    async def run(command):
        commands.append(ffmpeg.compile(command))
        output.touch()
        return 0, b'', b''

    monkeypatch.setattr(takescreens, 'run_ffmpeg', run)
    meta = Meta(frame_overlay=True, frame_rate=24, resolution='720p')
    if backend == 'disc':
        task = takescreens.capture_disc_task(0, str(source), '1.26', str(output), 'none', 'quiet', False, meta)
    elif backend == 'dvd':
        task = takescreens.capture_dvd_screenshot((0, str(source), str(output), '1.26', meta, 1280, 720, 1, 1))
    else:
        task = takescreens.capture_screenshot((0, str(source), 1.26, str(output), 1280, 720, 1, 1, 'quiet', False, meta))
    assert asyncio.run(task) == (0, str(output))
    filters = commands[0][commands[0].index('-vf') + 1]
    assert 'Timestamp' in filters and 'pts\\:hms\\:1.260000' in filters
    assert 'Frame Number' not in filters and 'Frame Type' not in filters and 'Tonemapped' not in filters


def test_new_switches_set_capture_flag_before_tracker_suppression(tmp_path):
    from src import prep_helpers
    from src.meta import Meta

    prep = SimpleNamespace(config={'DEFAULT': {'overlay_timestamp': True}})
    meta = Meta(base_dir=str(tmp_path), path=str(tmp_path))
    prep_helpers.init_meta(prep, meta, 'cli')
    assert meta.frame_overlay is True


def test_vapoursynth_labels_use_selected_fields_and_frame_time(monkeypatch):
    import importlib.util
    import sys
    from pathlib import Path

    rendered = []
    frame = SimpleNamespace(props={'_PictType': b'B'})
    clip = SimpleNamespace(fps_num=24000, fps_den=1001)
    core = SimpleNamespace(
        std=SimpleNamespace(FrameEval=lambda clip, callback, prop_src: callback(24000, frame)),
        text=SimpleNamespace(Text=lambda clip, text, **kwargs: rendered.append((text, kwargs["alignment"]))),
    )
    monkeypatch.setitem(sys.modules, 'vapoursynth', SimpleNamespace(core=core))
    monkeypatch.setitem(sys.modules, 'awsmfunc', SimpleNamespace(DynamicTonemap=None, ScreenGen=None, zresize=None))
    spec = importlib.util.spec_from_file_location('overlay_vs_test', Path(__file__).parents[1] / 'src/vs.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.custom_frame_info(clip, {'overlay_timestamp': True, 'overlay_tonemapped': True}, True)
    assert rendered == [(b'Timestamp: 00:16:41.000\nTonemapped', 7)]
    rendered.clear()
    module.custom_frame_info(clip, {'overlay_timestamp': True, 'overlay_tonemapped': True}, True, layout='single_line', position='right')
    assert rendered == [('00:16:41.000 • Tonemapped'.encode('cp1252'), 9)]
    rendered.clear()
    module.custom_frame_info(clip, {}, True)
    assert rendered == []
