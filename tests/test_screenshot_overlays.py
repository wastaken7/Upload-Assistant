"""Regression coverage for independent overlays and legacy configuration."""

from types import SimpleNamespace
import asyncio

import pytest

from src.screenshot_overlays import OVERLAY_KEYS, format_timestamp, overlay_enabled, overlay_filters, overlay_lines, overlay_options, overlay_text_size, overlays_active


@pytest.mark.parametrize("key", OVERLAY_KEYS)
def test_overlay_switch_types_are_validated(key):
    from src.configvalidator import _validate_default_section

    _, warnings = _validate_default_section({'tmdb_api': 'test', key: True})
    assert not any(warning.key == key for warning in warnings)
    _, warnings = _validate_default_section({'tmdb_api': 'test', key: 'invalid'})
    assert any(warning.key == key for warning in warnings)


@pytest.mark.parametrize("value", [1, "1", 18, "18", 100, "100"])
def test_valid_overlay_text_sizes_are_preserved(value):
    """Manual configs accept integer and string sizes throughout the supported range."""
    from src.configvalidator import _validate_default_section

    config = {"tmdb_api": "test", "overlay_text_size": value}
    errors, warnings = _validate_default_section(config)
    assert not errors
    assert not any(warning.key == "overlay_text_size" for warning in warnings)
    assert config["overlay_text_size"] == value
    assert overlay_text_size(config) == int(value)


@pytest.mark.parametrize("value", [0, "0", -1, 101, "101", "abc", "18.5", 18.5, "", True, None, [], float('inf')])
def test_invalid_overlay_text_sizes_warn_without_rewriting_config(value):
    """Invalid manual values warn while capture retains a safe size fallback."""
    from src.configvalidator import _validate_default_section

    config = {"tmdb_api": "test", "overlay_text_size": value}
    errors, warnings = _validate_default_section(config)
    assert not errors
    assert any(warning.key == "overlay_text_size" for warning in warnings)
    assert config["overlay_text_size"] is value
    assert 1 <= overlay_text_size(config) <= 100


@pytest.mark.parametrize("key,values", [("overlay_position", ("left", "right")), ("overlay_layout", ("stacked", "single_line"))])
def test_manual_overlay_choices_warn_on_unsupported_values(key, values):
    """The CLI validator accepts exactly the choices offered by the WebUI."""
    from src.configvalidator import _validate_default_section

    for value in (*values, "invalid", values[0].upper(), "", None, []):
        config = {"tmdb_api": "test", key: value}
        errors, warnings = _validate_default_section(config)
        assert not errors
        assert any(warning.key == key for warning in warnings) == (value not in values)
        assert config[key] is value


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


@pytest.mark.parametrize("backend", ["disc", "dvd"])
@pytest.mark.parametrize("parsed_rate", [25.0, 29.97])
@pytest.mark.parametrize("previous_rate", [None, 24.0])
def test_disc_overlay_uses_parsed_rate_before_capture(tmp_path, monkeypatch, backend, parsed_rate, previous_rate):
    """Disc timing and overlay frame numbers must use the same parsed frame rate."""
    from unittest.mock import AsyncMock

    from src import takescreens
    from src.meta import Meta

    class CaptureReached(Exception):
        """Stop once metadata has reached the capture scheduling boundary."""

    meta = Meta(base_dir=str(tmp_path), uuid='frame-rate', screens=1, frame_overlay=True, frame_rate=previous_rate, resolution='1080p')
    config = {'frame_overlay': True, **dict.fromkeys(OVERLAY_KEYS, False), 'overlay_frame_number': True}
    monkeypatch.setattr(takescreens, 'cutoff', 6)
    monkeypatch.setattr(takescreens, 'get_image_host', AsyncMock(return_value='imgbb'))

    async def capture_times(_times, _count, _length, frame_rate, capture_meta, **_kwargs):
        assert frame_rate == parsed_rate
        assert capture_meta.frame_rate == parsed_rate
        filters = overlay_filters(config, capture_meta, 10.0, False)
        assert f'Frame Number\\: {int(10 * parsed_rate)}' in filters[0]
        raise CaptureReached

    monkeypatch.setattr(takescreens, 'valid_ss_time', capture_times)
    if backend == 'disc':
        (tmp_path / 'source.m2ts').touch()
        bdinfo = {
            'path': str(tmp_path),
            'files': [{'file': 'source.m2ts', 'length': '00:02:00'}],
            'video': [{'fps': f'{parsed_rate} fps', 'codec': 'AVC', 'hdr_dv': ''}],
        }
        task = takescreens.disc_screenshots(meta, 'Release', bdinfo, meta.uuid, str(tmp_path), False)
    else:
        meta.discs = [{'path': str(tmp_path), 'name': 'DVD', 'main_set': ['01_1.VOB']}]
        track = SimpleNamespace(track_type='Video', duration=120000, pixel_aspect_ratio=1, display_aspect_ratio=1.5, width=720, height=480, frame_rate=str(parsed_rate))

        def media_info(_path, **kwargs):
            if kwargs.get('output') == 'JSON':
                return '{"media":{"track":[{"Width":720,"Height":480,"Duration":120}]}}'
            return SimpleNamespace(tracks=[track])

        monkeypatch.setattr(takescreens.MediaInfo, 'parse', media_info)
        task = takescreens.dvd_screenshots(meta, 0)
    with pytest.raises(CaptureReached):
        asyncio.run(task)


@pytest.mark.parametrize("text_size,height,expected_scale", [(18, 1080, 1), (36, 1080, 2), (18, 2160, 2), (36, 2160, 4), (1, 720, 1), (100, 1080, 6)])
def test_vapoursynth_labels_use_selected_fields_and_frame_time(monkeypatch, text_size, height, expected_scale):
    """VapourSynth preserves labels and time while applying size and resolution scaling."""
    import importlib.util
    import sys
    from pathlib import Path

    rendered = []
    frame = SimpleNamespace(props={'_PictType': b'B'})
    clip = SimpleNamespace(fps_num=24000, fps_den=1001, height=height)
    core = SimpleNamespace(
        std=SimpleNamespace(FrameEval=lambda clip, callback, prop_src: callback(24000, frame)),
        text=SimpleNamespace(Text=lambda clip, text, **kwargs: rendered.append((text, kwargs["alignment"], kwargs["scale"]))),
    )
    monkeypatch.setitem(sys.modules, 'vapoursynth', SimpleNamespace(core=core))
    monkeypatch.setitem(sys.modules, 'awsmfunc', SimpleNamespace(DynamicTonemap=None, ScreenGen=None, zresize=None))
    spec = importlib.util.spec_from_file_location('overlay_vs_test', Path(__file__).parents[1] / 'src/vs.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.custom_frame_info(clip, {'overlay_timestamp': True, 'overlay_tonemapped': True}, True, text_size=text_size)
    assert rendered == [(b'Timestamp: 00:16:41.000\nTonemapped', 7, expected_scale)]
    rendered.clear()
    module.custom_frame_info(clip, {'overlay_timestamp': True, 'overlay_tonemapped': True}, True, layout='single_line', position='right', text_size=text_size)
    assert rendered == [('00:16:41.000 • Tonemapped'.encode('cp1252'), 9, expected_scale)]
    rendered.clear()
    module.custom_frame_info(clip, {}, True)
    assert rendered == []


@pytest.mark.parametrize("configured_size, expected_scale", [("36", 2), (36, 2), ("invalid", 1)])
def test_vapoursynth_capture_forwards_size_to_source_and_encode(tmp_path, monkeypatch, configured_size, expected_scale):
    """Both sides of a VapourSynth comparison honor the configured text size."""
    import importlib.util
    import sys
    from pathlib import Path

    class Clip:
        """Supply only the video properties exercised by the capture path."""
        width, height, fps_num, fps_den = 1920, 1080, 24, 1

        def __len__(self):
            return 20000

        def get_frame(self, _number):
            return SimpleNamespace(props={'_Primaries': 1, '_PictType': b'B'})

    source, encode = tmp_path / 'source.mkv', tmp_path / 'encode.mkv'
    source.touch()
    encode.touch()
    (tmp_path / 'screens.txt').write_text('100\n', encoding='utf-8')
    source_clip, encode_clip = Clip(), Clip()
    rendered, generated = [], []

    def render(clip, text, **kwargs):
        rendered.append((clip, text, kwargs['scale'], kwargs['alignment']))
        return clip

    core = SimpleNamespace(
        ffms2=SimpleNamespace(Source=lambda path, **_kwargs: source_clip if path == str(source) else encode_clip),
        std=SimpleNamespace(FrameEval=lambda clip, callback, prop_src: callback(100, clip.get_frame(100))),
        text=SimpleNamespace(Text=render),
    )
    monkeypatch.setitem(sys.modules, 'vapoursynth', SimpleNamespace(core=core))
    monkeypatch.setitem(sys.modules, 'awsmfunc', SimpleNamespace(DynamicTonemap=None, ScreenGen=lambda clip, _dir, suffix: generated.append((clip, suffix)), zresize=None))
    spec = importlib.util.spec_from_file_location('overlay_vs_capture_test', Path(__file__).parents[1] / 'src/vs.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'optimize_images', lambda *_args: None)
    config = {'frame_overlay': True, **dict.fromkeys(OVERLAY_KEYS, False), 'overlay_timestamp': True, 'overlay_text_size': configured_size, 'overlay_position': 'right'}
    module.vs_screengn(str(source), str(encode), num=1, dir=str(tmp_path), config=config)
    assert rendered == [
        (source_clip, b'Timestamp: 00:00:04.167', expected_scale, 9),
        (encode_clip, b'Timestamp: 00:00:04.167', expected_scale, 9),
    ]
    assert generated == [(source_clip, 'a'), (encode_clip, 'b')]
