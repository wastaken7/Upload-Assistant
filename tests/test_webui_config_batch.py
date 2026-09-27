from copy import deepcopy
from pathlib import Path

import pytest

import web_ui.server as server
from src.config_sync import sync_user_config


@pytest.fixture
def batch_config(tmp_path, monkeypatch):
    keys = server._TRACKER_DEFAULT_OVERRIDE_KEYS[:22]
    example = {
        "DEFAULT": {"screens": 6, **dict.fromkeys(keys, True)},
        "TRACKERS": {name: {"api_key": "", **dict.fromkeys(keys, True)} for name in ("AITHER", "BLU", "LST")},
    }
    user = deepcopy(example)
    for tracker in user["TRACKERS"].values():
        tracker["api_key"] = "test-key"
    example_path = tmp_path / "code/data/example_config.py"
    config_path = tmp_path / "state/data/config.py"
    for path, config in ((example_path, example), (config_path, user)):
        path.parent.mkdir(parents=True)
        path.write_text(f"config = {config!r}\n", encoding="utf-8")
    monkeypatch.setattr(server, "CODE_DIR", example_path.parent.parent)
    monkeypatch.setattr(server, "STATE_DIR", config_path.parent.parent)
    for guard in ("_is_authenticated", "_verify_csrf_header", "_verify_same_origin", "_is_ip_allowed"):
        monkeypatch.setattr(server, guard, lambda *args: True)
    records = []
    monkeypatch.setattr(server, "_write_audit_log", lambda *args: records.append(args))
    server.limiter.reset()
    yield config_path, example_path, keys, records
    server.limiter.reset()


def post_updates(updates):
    with server.app.test_request_context("/api/config_update", method="POST", json={"updates": updates}):
        result = server.config_update()
        response, status = result if isinstance(result, tuple) else (result, 200)
        return response.get_json(), status


def test_66_overrides_use_one_rate_limit_slot_and_one_file_write(batch_config, monkeypatch):
    config_path, example_path, keys, records = batch_config
    writes = []
    write_text = Path.write_text

    def record_write(path, *args, **kwargs):
        if path == config_path:
            writes.append(path)
        return write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", record_write)
    client = server.app.test_client()
    # Spend 49 of the existing 50 hourly requests first. A 66-field save still
    # fits in the last slot; raising or bypassing the limiter is unnecessary.
    for _ in range(49):
        assert client.post("/api/config_update", json={"path": ["DEFAULT", "screens"], "value": 6}).status_code == 200
    writes.clear()
    records.clear()
    updates = [{"path": ["TRACKERS", name, key], "value": None} for name in ("AITHER", "BLU", "LST") for key in keys]
    response = client.post("/api/config_update", json={"updates": updates})
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["values"] == [None] * 66
    assert writes == [config_path]
    assert len(records) == 66
    assert all(record[4] is True for record in records)
    assert not sync_user_config(config_path, example_path).changed
    saved = server._load_config_from_file(config_path)
    for tracker in saved["TRACKERS"].values():
        assert tracker == {"api_key": "test-key", **dict.fromkeys(keys)}

    before = config_path.read_bytes()
    limited = client.post("/api/config_update", json={"updates": [{"path": ["DEFAULT", "screens"], "value": 8}]})
    assert limited.status_code == 429
    assert limited.is_json
    assert limited.get_json()["success"] is False
    assert "Too many requests" in limited.get_json()["error"]
    assert config_path.read_bytes() == before


@pytest.mark.parametrize("invalid", [
    {"path": ["TRACKERS", "UNKNOWN", "add_logo"], "value": None},
    {"path": ["DEFAULT", "screens"], "value": "invalid-number"},
    {"path": ["DEFAULT", None, "screens"], "value": 8},
    {"path": ["TRACKERS", "AITHER", "tag_overrides"], "value": {"Group": "invalid-group"}},
])
def test_invalid_later_field_leaves_entire_batch_unsaved(batch_config, invalid):
    config_path, _, _, records = batch_config
    before = config_path.read_bytes()
    result, status = post_updates([{"path": ["TRACKERS", "AITHER", "add_logo"], "value": None}, invalid])
    assert status == 400, result
    assert config_path.read_bytes() == before
    assert records == []


def test_missing_tracker_creation_and_falsy_values_save_together(batch_config):
    config_path, _, _, _ = batch_config
    config_path.write_text("config = {'DEFAULT': {'screens': 6}, 'TRACKERS': {}}\n", encoding="utf-8")
    updates = [
        {"path": ["TRACKERS", "AITHER"], "value": "{}"},
        {"path": ["TRACKERS", "AITHER", "add_logo"], "value": False},
        {"path": ["TRACKERS", "AITHER", "custom_header"], "value": None},
        {"path": ["DEFAULT", "screens"], "value": 0},
        {"path": ["DEFAULT", "sonarr_url_1"], "value": "http://localhost:8989"},
        {"path": ["DEFAULT", "sonarr_url_1"], "value": "", "remove": True},
    ]
    assert post_updates(updates)[1] == 200
    assert server._load_config_from_file(config_path) == {
        "DEFAULT": {"screens": 0},
        "TRACKERS": {"AITHER": {"add_logo": False, "custom_header": None}},
    }


def test_write_failure_does_not_report_success_and_can_be_retried(batch_config, monkeypatch):
    config_path, _, _, records = batch_config
    original = config_path.read_bytes()
    updates = [{"path": ["TRACKERS", "AITHER", "add_logo"], "value": None}]

    def fail_write(*args, **kwargs):
        raise OSError("Disk unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "write_text", fail_write)
        assert post_updates(updates)[1] == 500
    assert config_path.read_bytes() == original
    assert records[0][4] is False
    assert post_updates(updates)[1] == 200
    assert server._load_config_from_file(config_path)["TRACKERS"]["AITHER"]["add_logo"] is None
    assert records[-1][4] is True


@pytest.mark.parametrize("updates", [[], None, {}, [None], [{}] * 1001])
def test_invalid_batch_shape_does_not_write(batch_config, updates):
    config_path, _, _, _ = batch_config
    before = config_path.read_bytes()
    assert post_updates(updates)[1] == 400
    assert config_path.read_bytes() == before


@pytest.mark.parametrize("guard,status", [("_is_authenticated", 401), ("_verify_csrf_header", 403), ("_verify_same_origin", 403)])
def test_batch_requires_authenticated_same_origin_session(batch_config, monkeypatch, guard, status):
    config_path, _, _, _ = batch_config
    before = config_path.read_bytes()
    monkeypatch.setattr(server, guard, lambda: False)
    assert post_updates([{"path": ["DEFAULT", "screens"], "value": 8}])[1] == status
    assert config_path.read_bytes() == before
