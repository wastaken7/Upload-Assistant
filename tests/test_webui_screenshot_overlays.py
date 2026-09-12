"""Verify that WebUI edits and capture agree on legacy overlay values."""

from pathlib import Path

import pytest

import web_ui.server as server
from src.screenshot_overlays import OVERLAY_KEYS, overlay_enabled, overlay_options


@pytest.mark.parametrize("legacy", [False, True])
def test_legacy_overlay_fields_round_trip_independently(tmp_path: Path, monkeypatch, legacy):
    example = {"DEFAULT": {"frame_overlay": False, **dict.fromkeys(OVERLAY_KEYS, False), "overlay_text_size": "18", "overlay_position": "left", "overlay_layout": "stacked"}}
    user = {"DEFAULT": {"frame_overlay": legacy, "overlay_text_size": "24", "unrelated": "keep"}}
    example_path = tmp_path / 'code/data/example_config.py'
    config_path = tmp_path / 'state/data/config.py'
    for path, config in ((example_path, example), (config_path, user)):
        path.parent.mkdir(parents=True)
        path.write_text(f"config = {config!r}\n", encoding='utf-8')
    monkeypatch.setattr(server, 'CODE_DIR', example_path.parent.parent)
    monkeypatch.setattr(server, 'STATE_DIR', config_path.parent.parent)
    for name in ('_is_authenticated', '_verify_csrf_header', '_verify_same_origin'):
        monkeypatch.setattr(server, name, lambda: True)
    monkeypatch.setattr(server, '_write_audit_log', lambda *args, **kwargs: None)

    def displayed_options():
        with server.app.test_request_context('/api/config_options'):
            items = server.config_options().get_json()['sections'][0]['items']
        assert next(item['value'] for item in items if item['key'] == 'frame_overlay') == overlay_enabled(user['DEFAULT'])
        return {item['key']: item['value'] for item in items if item['key'] in OVERLAY_KEYS}

    assert displayed_options() == overlay_options(user['DEFAULT'])
    # Changing the old master persists its prior label selections before the
    # fallback value changes, so off/on cycles do not reset user preferences.
    original_options = overlay_options(user['DEFAULT'])
    for enabled in (not legacy, legacy):
        with server.app.test_request_context('/api/config_update', method='POST', json={'path': ['DEFAULT', 'frame_overlay'], 'value': enabled}):
            assert server.config_update().get_json()['success'] is True
        user['DEFAULT'].update(original_options)
        user['DEFAULT']['frame_overlay'] = enabled
        assert server._load_config_from_file(config_path) == user
        assert displayed_options() == original_options
    for key, value in [('overlay_timestamp', True), ('overlay_frame_type', False), ('overlay_tonemapped', False), ('overlay_frame_number', False), ('overlay_timestamp', False)]:
        with server.app.test_request_context('/api/config_update', method='POST', json={'path': ['DEFAULT', key], 'value': value}):
            result = server.config_update()
            response, status = result if isinstance(result, tuple) else (result, 200)
            assert status == 200, response.get_json()
        user['DEFAULT'][key] = value
        saved = server._load_config_from_file(config_path)
        assert saved == user
        assert displayed_options() == overlay_options(saved['DEFAULT'])
    assert not any(displayed_options().values())
    for key, value in [('overlay_position', 'right'), ('overlay_layout', 'single_line')]:
        with server.app.test_request_context('/api/config_update', method='POST', json={'path': ['DEFAULT', key], 'value': value}):
            assert server.config_update().get_json()['success'] is True
        user['DEFAULT'][key] = value
        assert server._load_config_from_file(config_path) == user
        before = config_path.read_bytes()
        with server.app.test_request_context('/api/config_update', method='POST', json={'path': ['DEFAULT', key], 'value': 'invalid'}):
            assert server.config_update()[1] == 400
        assert config_path.read_bytes() == before
    assert server._load_config_from_file(example_path) == example


@pytest.mark.parametrize("prior_defaults, expected_master", [({}, False), ({"overlay_frame_number": True}, True)])
def test_editing_labels_preserves_implicit_master_state(tmp_path: Path, monkeypatch, prior_defaults, expected_master):
    example_path = tmp_path / 'code/data/example_config.py'
    config_path = tmp_path / 'state/data/config.py'
    for path, config in (
        (example_path, {"DEFAULT": {"frame_overlay": False, **dict.fromkeys(OVERLAY_KEYS, False)}}),
        (config_path, {"DEFAULT": prior_defaults}),
    ):
        path.parent.mkdir(parents=True)
        path.write_text(f"config = {config!r}\n", encoding='utf-8')
    monkeypatch.setattr(server, 'CODE_DIR', example_path.parent.parent)
    monkeypatch.setattr(server, 'STATE_DIR', config_path.parent.parent)
    for name in ('_is_authenticated', '_verify_csrf_header', '_verify_same_origin'):
        monkeypatch.setattr(server, name, lambda: True)
    monkeypatch.setattr(server, '_write_audit_log', lambda *args, **kwargs: None)

    for key in OVERLAY_KEYS:
        with server.app.test_request_context('/api/config_update', method='POST', json={'path': ['DEFAULT', key], 'value': True}):
            assert server.config_update().get_json()['success'] is True
        saved = server._load_config_from_file(config_path)['DEFAULT']
        assert saved['frame_overlay'] is expected_master
        assert saved[key] is True
