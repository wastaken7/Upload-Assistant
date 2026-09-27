from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

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
    replace = Path.replace

    def record_write(path, target):
        if target == config_path:
            writes.append(target)
        return replace(path, target)

    monkeypatch.setattr(Path, "replace", record_write)
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
        patch.setattr(Path, "replace", fail_write)
        assert post_updates(updates)[1] == 500
    assert config_path.read_bytes() == original
    assert list(config_path.parent.glob(".config.py.*.tmp")) == []
    assert records[0][4] is False
    assert post_updates(updates)[1] == 200
    assert server._load_config_from_file(config_path)["TRACKERS"]["AITHER"]["add_logo"] is None
    assert records[-1][4] is True


@pytest.mark.parametrize("user", [{}, {"DEFAULT": {"screens": 6}}, {"TORRENT_CLIENTS": {}}])
def test_batch_creates_missing_torrent_client_parents(batch_config, user):
    config_path, example_path, _, _ = batch_config
    example = server._load_config_from_file(example_path)
    example["TORRENT_CLIENTS"] = {"qbittorrent": {"torrent_client": "qbit", "host": ""}}
    example_path.write_text(f"config = {example!r}\n", encoding="utf-8")
    config_path.write_text(f"config = {user!r}\n", encoding="utf-8")
    updates = [
        {"path": ["TORRENT_CLIENTS", "qbittorrent"], "value": "{}"},
        {"path": ["TORRENT_CLIENTS", "qbittorrent", "torrent_client"], "value": "qbit"},
        {"path": ["TORRENT_CLIENTS", "qbittorrent", "host"], "value": "localhost"},
    ]
    before = config_path.read_bytes()
    assert post_updates(updates + [{"path": ["DEFAULT", "unknown"], "value": True}])[1] == 400
    assert config_path.read_bytes() == before
    assert post_updates(updates)[1] == 200
    assert server._load_config_from_file(config_path) == {
        **user, "TORRENT_CLIENTS": {"qbittorrent": {"torrent_client": "qbit", "host": "localhost"}},
    }


def test_missing_parents_do_not_replace_existing_scalar_sections(batch_config):
    config_path, _, _, _ = batch_config
    original = "config = {'TRACKERS': 'managed elsewhere'}\n"
    config_path.write_text(original, encoding="utf-8")
    assert post_updates([{"path": ["TRACKERS", "AITHER", "add_logo"], "value": None}])[1] == 400
    assert config_path.read_text(encoding="utf-8") == original


def test_concurrent_batches_preserve_both_writers_edits(batch_config, monkeypatch):
    config_path, _, _, _ = batch_config
    first_staged, release_first, second_staged = Event(), Event(), Event()
    apply_update = server._apply_config_update

    def pause_first(source, example, update):
        result = apply_update(source, example, update)
        if update["path"] == ["DEFAULT", "screens"]:
            first_staged.set()
            assert release_first.wait(5)
        else:
            second_staged.set()
        return result

    monkeypatch.setattr(server, "_apply_config_update", pause_first)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(post_updates, [{"path": ["DEFAULT", "screens"], "value": 8}])
        try:
            assert first_staged.wait(5)
            second = executor.submit(post_updates, [{"path": ["TRACKERS", "AITHER", "add_logo"], "value": None}])
            assert not second_staged.wait(0.15)
        finally:
            release_first.set()
        assert first.result(timeout=5)[1] == second.result(timeout=5)[1] == 200
    saved = server._load_config_from_file(config_path)
    assert saved["DEFAULT"]["screens"] == 8
    assert saved["TRACKERS"]["AITHER"]["add_logo"] is None


def test_startup_sync_coordinates_with_a_webui_save(batch_config, monkeypatch):
    config_path, example_path, _, _ = batch_config
    example = server._load_config_from_file(example_path)
    example["DEFAULT"]["new_option"] = "from-sync"
    example_path.write_text(f"config = {example!r}\n", encoding="utf-8")
    staged, release = Event(), Event()
    apply_update = server._apply_config_update

    def pause_update(*args):
        result = apply_update(*args)
        staged.set()
        assert release.wait(5)
        return result

    monkeypatch.setattr(server, "_apply_config_update", pause_update)
    with ThreadPoolExecutor(max_workers=2) as executor:
        save = executor.submit(post_updates, [{"path": ["TRACKERS", "AITHER", "add_logo"], "value": None}])
        try:
            assert staged.wait(5)
            sync = executor.submit(sync_user_config, config_path, example_path)
        finally:
            release.set()
        assert save.result(timeout=5)[1] == 200
        assert sync.result(timeout=5).changed
    saved = server._load_config_from_file(config_path)
    assert saved["TRACKERS"]["AITHER"]["add_logo"] is None
    assert saved["DEFAULT"]["new_option"] == "from-sync"


def test_external_edit_during_save_is_preserved_and_reported(batch_config, monkeypatch):
    config_path, _, _, records = batch_config
    external_source = "config = {'DEFAULT': {'screens': 99}, 'CUSTOM': 'external edit'}\n"
    replace = server.replace_config_source

    def external_edit(path, source, original):
        path.write_text(external_source, encoding="utf-8")
        return replace(path, source, original)

    monkeypatch.setattr(server, "replace_config_source", external_edit)
    result, status = post_updates([{"path": ["DEFAULT", "screens"], "value": 8}])
    assert status == 409
    assert "Configuration changed" in result["error"]
    assert config_path.read_text(encoding="utf-8") == external_source
    assert list(config_path.parent.glob(".config.py.*.tmp")) == []
    assert records[-1][4] is False


def test_failed_temp_file_flush_keeps_original_and_cleans_temp(batch_config, monkeypatch):
    import src.config_sync as config_sync
    config_path, _, _, _ = batch_config
    original = config_path.read_bytes()

    def fail_flush(*args):
        raise OSError("Disk unavailable")

    monkeypatch.setattr(config_sync.os, "fsync", fail_flush)
    assert post_updates([{"path": ["DEFAULT", "screens"], "value": 8}])[1] == 500
    assert config_path.read_bytes() == original
    assert list(config_path.parent.glob(".config.py.*.tmp")) == []


@pytest.mark.parametrize("endpoint,payload", [
    ("config_update", {"updates": [{"path": ["DEFAULT", "screens"], "value": 8}]}),
    ("config_set_tracker_overrides", {"tracker": "AITHER", "enabled": False}),
    ("config_remove_subsection", {"path": ["TRACKERS", "AITHER"]}),
    ("config_add_torrent_client", {"name": "another", "template": "qbittorrent"}),
    ("config_rename_torrent_client", {"old_name": "seedbox", "new_name": "renamed"}),
])
def test_all_config_writers_wait_for_shared_lock_and_read_latest_file(batch_config, endpoint, payload):
    config_path, example_path, _, _ = batch_config
    for path, name in ((config_path, "seedbox"), (example_path, "qbittorrent")):
        config = server._load_config_from_file(path)
        config["TORRENT_CLIENTS"] = {name: {"torrent_client": "qbit", "host": "localhost"}}
        path.write_text(f"config = {config!r}\n", encoding="utf-8")
    started = Event()

    def run_request():
        with server.app.test_request_context(f"/api/{endpoint}", method="POST", json=payload):
            started.set()
            result = getattr(server, endpoint)()
            response, status = result if isinstance(result, tuple) else (result, 200)
            return response.get_json(), status

    with ThreadPoolExecutor(max_workers=1) as executor:
        with server.config_write_lock(config_path):
            pending = executor.submit(run_request)
            assert started.wait(5)
            with pytest.raises(TimeoutError):
                pending.result(timeout=0.15)
            latest = server._load_config_from_file(config_path)
            latest["CUSTOM"] = "another writer's edit"
            config_path.write_text(f"config = {latest!r}\n", encoding="utf-8")
        result, status = pending.result(timeout=5)
        assert status == 200, result
    assert server._load_config_from_file(config_path)["CUSTOM"] == "another writer's edit"


def prepare_aliases(batch_config):
    config_path, example_path, _, _ = batch_config
    for path in (config_path, example_path):
        config = server._load_config_from_file(path)
        config["TRACKERS"]["AITHER"]["cli_alias"] = "ATH"
        config["TRACKERS"]["LST"]["cli_alias"] = "LION"
        path.write_text(f"config = {config!r}\n", encoding="utf-8")
    return config_path


@pytest.mark.parametrize("alias", ["lion", "BEYONDHD", "BHD", "two words", "A,B"])
def test_invalid_alias_save_rejects_entire_batch(batch_config, alias):
    config_path = prepare_aliases(batch_config)
    original = config_path.read_bytes()
    result, status = post_updates([
        {"path": ["DEFAULT", "screens"], "value": 8},
        {"path": ["TRACKERS", "AITHER", "cli_alias"], "value": alias},
    ])
    assert status == 400, result
    assert "cli_alias" in result["error"]
    assert config_path.read_bytes() == original


def test_alias_swap_is_validated_against_final_batch(batch_config):
    config_path = prepare_aliases(batch_config)
    assert post_updates([
        {"path": ["TRACKERS", "AITHER", "cli_alias"], "value": "LION"},
        {"path": ["TRACKERS", "LST", "cli_alias"], "value": "ATH"},
    ])[1] == 200
    saved = server._load_config_from_file(config_path)
    assert server.tracker_cli_aliases(saved) == {"LION": "AITHER", "ATH": "LST"}
    assert post_updates([{"path": ["TRACKERS", "AITHER", "cli_alias"], "value": ""}])[1] == 200
    assert server._load_config_from_file(config_path)["TRACKERS"]["AITHER"]["cli_alias"] == ""


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
