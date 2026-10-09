# ruff: noqa: S101
import hashlib
import io
import json
import shlex
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import src.webui_paths as policy
import web_ui.server as server
from src.meta import Meta
from src.queuemanage import QueueManager
from src.webui_paths import QUEUE_ENV, QUEUE_HASH_ENV, ROOTS_ENV, is_generated_queue_path, read_generated_queue, validate_content_path, validate_subprocess_queue


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "media"
    root.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    first = root / "Fictional Journey (2026).mkv"
    second = root / "Fictional Artist's [Group] & Concert.mkv"
    first.touch()
    second.touch()
    monkeypatch.setattr(server, "STATE_DIR", state)
    monkeypatch.setattr(server, "_get_browse_roots", lambda: [str(root)])
    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_verify_same_origin", lambda: True)
    monkeypatch.setattr(server.limiter, "enabled", False)
    monkeypatch.setattr(server, "_generated_queues", {})
    monkeypatch.delenv(ROOTS_ENV, raising=False)
    return server.app.test_client(), root, state, first, second


def test_single_path_is_validated_without_creating_queue(workspace):
    client, _, state, first, _ = workspace
    response = client.post("/api/save_queue", json={"items": [{"path": str(first)}], "return_single_path": True})
    assert response.status_code == 200
    assert response.json == {"success": True, "path": str(first), "queued": False}
    assert not (state / "tmp").exists()


def test_existing_api_call_with_one_item_still_creates_queue(workspace):
    client, _, _, first, _ = workspace
    response = client.post("/api/save_queue", json={"items": [{"path": str(first), "args": "--anon"}]})
    assert response.status_code == 200
    assert response.json["queued"] is True
    assert shlex.split(Path(response.json["path"]).read_text(encoding="utf-8")) == [str(first), "--anon"]


@pytest.mark.parametrize("kind", ["outside", "similar-prefix", "traversal", "missing", "nul", "text-queue", "log-queue"])
def test_queue_validation_is_atomic_and_reports_item(workspace, kind):
    client, root, state, first, _ = workspace
    invalid = root.parent / "external.mkv"
    invalid.touch()
    if kind == "similar-prefix":
        other = root.parent / "media-extra"
        other.mkdir()
        invalid = other / "Fictional.mkv"
        invalid.touch()
    elif kind == "traversal":
        invalid = "../external.mkv"
    elif kind == "missing":
        invalid = root / "missing.mkv"
    elif kind == "nul":
        invalid = str(first) + "\x00"
    elif kind in {"text-queue", "log-queue"}:
        queue = root / ("manual.txt" if kind == "text-queue" else "manual.log")
        queue.write_text(str(invalid), encoding="utf-8")
        invalid = queue
    response = client.post("/api/save_queue", json={"items": [{"path": str(first)}, {"path": str(invalid)}]})
    assert response.status_code == 400
    assert response.json["item"] == 2
    assert not (state / "tmp").exists()
    assert not server._generated_queues


@pytest.mark.parametrize("item", [None, "path", {}, {"path": 123}, {"path": ""}, {"path": [], "args": ""}])
def test_queue_rejects_malformed_items_without_skipping(workspace, item):
    client, _, _, first, _ = workspace
    response = client.post("/api/save_queue", json={"items": [{"path": str(first)}, item]})
    assert response.status_code == 400
    assert response.json["item"] == 2


def test_queue_limit_and_unconfigured_roots(workspace, monkeypatch):
    client, _, _, first, _ = workspace
    response = client.post("/api/save_queue", json={"items": [{"path": str(first)}] * 1001})
    assert response.status_code == 400
    monkeypatch.setattr(server, "_get_browse_roots", lambda: [])
    response = client.post("/api/save_queue", json={"items": [{"path": str(first)}]})
    assert response.status_code == 400


def test_generated_queue_is_registered_and_tampering_revokes_access(workspace):
    client, _, state, first, second = workspace
    response = client.post("/api/save_queue", json={"items": [{"path": str(first)}, {"path": str(second), "args": '--music-artist "Fictional Artist & Guest"'}]})
    assert response.status_code == 200
    queue = Path(response.json["path"])
    assert queue.parent == state / "tmp"
    lines = queue.read_text(encoding="utf-8").splitlines()
    assert shlex.split(lines[1]) == [str(second), "--music-artist", "Fictional Artist & Guest"]
    assert server._validate_execution_path(str(queue)) == str(queue)
    queue.write_text('"' + str(root_external := state / "external.mkv") + '"\n', encoding="utf-8")
    root_external.touch()
    assert not server._is_generated_queue(str(queue))
    with pytest.raises(ValueError):
        server._validate_execution_path(str(queue))


def test_queue_filename_does_not_grant_access_to_state_directory(workspace):
    _, _, state, _, _ = workspace
    (state / "tmp").mkdir()
    forged = state / "tmp" / "webui_queue_forged.txt"
    forged.touch()
    with pytest.raises(ValueError):
        server._resolve_user_path(str(forged))
    with pytest.raises(ValueError):
        server._assert_safe_resolved_path(forged)


class CompletedProcess:
    pid = 0

    def __init__(self):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()

    def poll(self):
        return 0

    def wait(self, _timeout=None):
        return 0


def test_generated_queue_executes_with_policy_and_is_cleaned_up(workspace, monkeypatch):
    client, root, _, first, second = workspace
    response = client.post("/api/save_queue", json={"items": [{"path": str(first)}, {"path": str(second)}]})
    queue = Path(response.json["path"])
    captured = []

    def spawn(command, _, env):
        captured.append((command, env))
        assert json.loads(env[ROOTS_ENV]) == [str(root)]
        assert env[QUEUE_ENV] == str(queue)
        assert env[QUEUE_HASH_ENV] == hashlib.sha256(queue.read_bytes()).hexdigest()
        return CompletedProcess(), "subprocess"

    monkeypatch.setattr(server, "_spawn_webui_upload_process", spawn)
    response = client.post("/api/execute", json={"path": str(queue), "session_id": "generated-queue-test"})
    try:
        output = response.get_data(as_text=True)
        assert '"type": "error"' not in output
        assert len(captured) == 1
        assert not queue.exists()
        assert not server._generated_queues
    finally:
        response.close()
        server.active_processes.pop("generated-queue-test", None)


def test_direct_execute_rejects_external_path_before_spawn(workspace, monkeypatch):
    client, root, _, _, _ = workspace
    external = root.parent / "external.mkv"
    external.touch()
    monkeypatch.setattr(server, "_spawn_webui_upload_process", lambda *_args: pytest.fail("Forbidden upload started"))
    response = client.post("/api/execute", json={"path": str(external), "session_id": "forbidden-path-test"})
    assert '"type": "error"' in response.get_data(as_text=True)
    response.close()


@pytest.mark.parametrize("invalid", ["path", "args"])
def test_invalid_execute_preserves_running_session(workspace, monkeypatch, invalid):
    client, root, _, first, _ = workspace
    session = "preserve-running-test"
    running = {"process": object()}
    server.active_processes[session] = running
    monkeypatch.setattr(server, "_terminate_process_tree", lambda *_args: pytest.fail("Existing upload was terminated"))
    external = root.parent / "external.mkv"
    external.touch()
    response = client.post(
        "/api/execute", json={"path": str(external if invalid == "path" else first), "args": "--queue ../escape" if invalid == "args" else "", "session_id": session}
    )
    try:
        assert '"type": "error"' in response.get_data(as_text=True)
        assert server.active_processes[session] is running
    finally:
        response.close()
        server.active_processes.pop(session, None)


def test_valid_execute_replaces_running_session(workspace, monkeypatch):
    client, _, _, first, _ = workspace

    class RunningProcess:
        def poll(self):
            return None

    running = RunningProcess()
    terminated = []
    session = "replace-valid-test"
    server.active_processes[session] = {"process": running}
    monkeypatch.setattr(server, "_terminate_process_tree", terminated.append)
    monkeypatch.setattr(server, "_spawn_webui_upload_process", lambda *_args: (CompletedProcess(), "subprocess"))
    response = client.post("/api/execute", json={"path": str(first), "session_id": session})
    try:
        assert '"type": "error"' not in response.get_data(as_text=True)
        assert terminated == [running]
    finally:
        response.close()
        server.active_processes.pop(session, None)


def test_csrf_is_required_for_path_preparation(workspace, monkeypatch):
    client, _, _, first, _ = workspace
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: False)
    response = client.post("/api/save_queue", json={"items": [{"path": str(first)}]})
    assert response.status_code == 403


def test_unavailable_configured_root_does_not_block_other_roots(workspace):
    _, root, _, first, _ = workspace
    assert validate_content_path(str(first), [str(root.parent / "offline-drive"), str(root)]) == str(first)


def _directory_link(link, target):
    if sys.platform == "win32":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, check=False)  # noqa: S603, S607 - only pytest-owned paths
        if result.returncode:
            pytest.fail(f"Could not create test junction: {result.stderr!r}")
    else:
        link.symlink_to(target, target_is_directory=True)


@pytest.mark.parametrize("external", [False, True])
def test_nested_directory_links_and_junctions_are_rejected(workspace, external):
    _, root, _, _, _ = workspace
    folder = root / "Fictional Season"
    folder.mkdir()
    target = (root.parent if external else root) / "linked-target"
    target.mkdir()
    (target / "Fictional Episode.mkv").touch()
    _directory_link(folder / "link", target)
    with pytest.raises(ValueError, match=r"outside allowed roots|directory links"):
        validate_content_path(str(folder), [str(root)])


def test_file_symlink_outside_roots_is_rejected(workspace):
    _, root, _, _, _ = workspace
    target = root.parent / "external.mkv"
    target.touch()
    link = root / "linked.mkv"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Creating file symlinks requires Windows developer mode or elevated privileges")
    with pytest.raises(ValueError, match="outside allowed roots"):
        validate_content_path(str(root), [str(root)])


@pytest.mark.parametrize(
    "args", ["--queue ../escape", "--queue=../escape", "--site-upload FICTIONAL", "-su FICTIONAL", "--unit3d", "--cleanup", "--webui", "--unknown-option", "external.mkv"]
)
def test_arguments_cannot_bypass_path_selection(workspace, args):
    _, _, _, _, _ = workspace
    with pytest.raises(ValueError):
        server._validate_upload_assistant_args(shlex.split(args))


def test_local_description_and_artwork_arguments_use_allowed_roots(workspace):
    _, root, _, _, _ = workspace
    description = root / "description.txt"
    description.touch()
    external = root.parent / "private.txt"
    external.touch()
    server._validate_upload_assistant_args(["--descfile", str(description)])
    for flag in ("--descfile", "--poster", "--banner", "--comparison"):
        with pytest.raises(ValueError, match="outside allowed roots"):
            server._validate_upload_assistant_args([flag, str(external)])


@pytest.mark.parametrize(
    ("args", "message"),
    [(["--unknown-option"], "Unrecognized argument: --unknown-option"), (["external.mkv"], "Additional paths must be entered one per line")],
)
@pytest.mark.usefixtures("workspace")
def test_invalid_arguments_explain_unknown_options_and_extra_paths(args, message):
    with pytest.raises(ValueError, match=message):
        server._validate_upload_assistant_args(args)


def test_generated_queue_without_expected_hash_is_rejected(tmp_path, monkeypatch):
    queue = tmp_path / "webui_queue_fictional.txt"
    queue.write_text("/media/Fictional.mkv\n", encoding="utf-8")
    monkeypatch.delenv(QUEUE_HASH_ENV, raising=False)
    with pytest.raises(ValueError, match="modified"):
        read_generated_queue(str(queue))


@pytest.mark.parametrize("flag", ["--torrenthash", "-th", "--torrenthash=../../private"])
def test_webui_rejects_torrent_reuse_in_global_and_queue_arguments(workspace, monkeypatch, flag):
    client, root, _, first, _ = workspace
    args = [flag] if "=" in flag else [flag, "../../private"]
    with pytest.raises(ValueError, match="Torrent reuse is only available in CLI mode"):
        server._validate_upload_assistant_args(args)
    response = client.post("/api/save_queue", json={"items": [{"path": str(first), "args": shlex.join(args)}]})
    assert response.status_code == 400
    monkeypatch.setenv(ROOTS_ENV, json.dumps([str(root)]))
    with pytest.raises(ValueError, match="Torrent reuse is only available in CLI mode"):
        validate_subprocess_queue([{"path": str(first), "args": [str(first), *args]}])
    monkeypatch.delenv(ROOTS_ENV)
    validate_subprocess_queue([{"path": str(first), "args": [str(first), *args]}])  # Ordinary CLI remains unrestricted.


@pytest.mark.asyncio
async def test_queue_skips_item_deleted_after_initial_validation_and_continues(workspace, monkeypatch):
    import importlib

    import src.stats as stats
    import upload
    from bin.get_mediainfo import MediaInfoBinaryManager

    _, root, state, first, second = workspace
    third = root / "Fictional Finale.mkv"
    third.touch()
    queue_path = state / "webui_queue_fictional.txt"
    queue_path.touch()
    monkeypatch.setenv(ROOTS_ENV, json.dumps([str(root)]))
    monkeypatch.setenv(QUEUE_ENV, str(queue_path))
    monkeypatch.setattr(sys, "argv", ["upload.py", str(queue_path)])
    monkeypatch.setattr(importlib, "reload", lambda _module: SimpleNamespace(config={"DEFAULT": {"sanitize_meta": True}}))
    monkeypatch.setattr(upload, "config", {})
    monkeypatch.setattr(upload, "load_heavy_globals", Mock())
    monkeypatch.setattr(upload, "update_notification", AsyncMock(return_value=None))
    monkeypatch.setattr("src.prowlarr.configured_prowlarr", lambda _config: None)
    monkeypatch.setattr("src.configvalidator.validate_config", lambda *_args: (True, [], []))
    monkeypatch.setattr(upload, "configured_binary", lambda *_args: True)
    monkeypatch.setattr(MediaInfoBinaryManager, "ensure_mediainfo_binary", AsyncMock())
    monkeypatch.setattr(upload, "get_mkbrr_path", AsyncMock(return_value=None))

    def parse(_args, meta):
        meta.path = str(queue_path)
        meta.queue = "fictional"
        return meta, None, None

    monkeypatch.setattr(upload, "parser", SimpleNamespace(parse=parse), raising=False)
    monkeypatch.setattr(QueueManager, "handle_queue", AsyncMock(return_value=([str(first), str(second), str(third)], None)))
    monkeypatch.setattr(upload, "cleanup_manager", SimpleNamespace(cleanup=AsyncMock(), reset_terminal=Mock()))
    monkeypatch.setattr(upload, "cancel_and_drain_early_artifact_tasks", AsyncMock())
    preview = Mock()
    monkeypatch.setattr(upload, "_publish_webui_preview_target", preview)
    for name in ("configure_stats", "set_stats_context"):
        monkeypatch.setattr(stats, name, Mock())
    for name in ("record_event_async", "record_release_profile_async"):
        monkeypatch.setattr(stats, name, AsyncMock())
    logger = Mock()
    monkeypatch.setattr(upload, "logger", logger)
    processed = []

    async def process(meta, _base_dir):
        processed.append(meta.path)
        if meta.path == str(first):
            second.unlink()
        return False

    monkeypatch.setattr(upload, "process_meta", process)
    await upload.do_the_thing(str(state))
    assert processed == [str(first), str(third)]
    assert [call.args[0] for call in preview.call_args_list] == processed
    assert any("Processed 3/3 files with 3 skipped" in str(call) for call in logger.info.call_args_list)


def test_subprocess_validates_all_expanded_items_and_cli_is_unchanged(workspace, monkeypatch):
    _, root, _, first, _ = workspace
    external = root.parent / "external.mkv"
    external.touch()
    items = [str(first), {"path": str(external), "args": [str(external)]}]
    validate_subprocess_queue(items)  # No WebUI environment means ordinary CLI.
    monkeypatch.setenv(ROOTS_ENV, json.dumps([str(root)]))
    with pytest.raises(ValueError, match="item 2"):
        validate_subprocess_queue(items)


@pytest.mark.asyncio
async def test_generated_queue_round_trip_preserves_quotes_and_arguments(workspace, monkeypatch):
    client, root, state, first, second = workspace
    response = client.post("/api/save_queue", json={"items": [{"path": str(first)}, {"path": str(second), "args": '--music-artist "Fictional Artist & Guest"'}]})
    path = response.json["path"]
    monkeypatch.setenv(ROOTS_ENV, json.dumps([str(root)]))
    monkeypatch.setenv(QUEUE_ENV, path)
    monkeypatch.setenv(QUEUE_HASH_ENV, hashlib.sha256(Path(path).read_bytes()).hexdigest())
    queue, _ = await QueueManager.handle_queue(path, Meta(), [path], str(state))
    assert [item["path"] for item in queue] == [str(first), str(second)]
    assert queue[1]["args"] == [str(second), "--music-artist", "Fictional Artist & Guest"]
    validate_subprocess_queue(queue)
    Path(path).write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="modified"):
        read_generated_queue(path)


@pytest.mark.parametrize("flag", ["--menus", "--menu", "-menus", "-menu"])
def test_menu_screenshots_are_validated_in_server_and_subprocess(workspace, monkeypatch, flag):
    client, root, _, first, _ = workspace
    menus = root / "Fictional Menus"
    menus.mkdir()
    (menus / "image.png").touch()
    external = root.parent / "private-menus"
    external.mkdir()
    for value in (str(menus), "auto", "AUTO"):
        server._validate_upload_assistant_args([flag, value])
    with pytest.raises(ValueError, match="outside allowed roots"):
        server._validate_upload_assistant_args([flag, str(external)])
    response = client.post("/api/save_queue", json={"items": [{"path": str(first), "args": shlex.join([flag, str(external)])}]})
    assert response.status_code == 400
    monkeypatch.setenv(ROOTS_ENV, json.dumps([str(root)]))
    with pytest.raises(ValueError, match="outside allowed roots"):
        validate_subprocess_queue([{"path": str(first), "args": [str(first), flag, str(external)]}])


@pytest.mark.asyncio
async def test_generated_queue_comparison_accepts_equivalent_paths(workspace, monkeypatch):
    client, root, state, first, second = workspace
    response = client.post("/api/save_queue", json={"items": [{"path": str(first)}, {"path": str(second)}]})
    path = response.json["path"]
    equivalent = str(Path(path).parent / "." / Path(path).name)
    if sys.platform == "win32":
        equivalent = path.swapcase().replace("\\", "/")
    monkeypatch.setenv(ROOTS_ENV, json.dumps([str(root)]))
    monkeypatch.setenv(QUEUE_ENV, equivalent)
    monkeypatch.setenv(QUEUE_HASH_ENV, hashlib.sha256(Path(path).read_bytes()).hexdigest())
    assert is_generated_queue_path(path)
    assert not is_generated_queue_path(str(first))
    queue, _ = await QueueManager.handle_queue(path, Meta(), [path], str(state))
    assert [item["path"] for item in queue] == [str(first), str(second)]


def test_queue_eviction_during_execution_fails_cleanly_without_spawning(workspace, monkeypatch):
    client, _, _, first, second = workspace
    response = client.post("/api/save_queue", json={"items": [{"path": str(first)}, {"path": str(second)}]})
    queue = response.json["path"]

    def clear_registration():
        server._generated_queues.clear()
        return {}

    monkeypatch.setattr(server, "_webui_subprocess_env", clear_registration)
    monkeypatch.setattr(server, "_spawn_webui_upload_process", lambda *_args: pytest.fail("Expired queue spawned"))
    response = client.post("/api/execute", json={"path": queue, "session_id": "eviction-race-test"})
    try:
        events = [json.loads(line[6:]) for line in response.get_data(as_text=True).splitlines() if line.startswith("data: ")]
        assert any(event.get("type") == "error" and "expired" in event.get("data", "") for event in events)
        assert "eviction-race-test" not in server.active_processes
    finally:
        response.close()


def test_eviction_removes_abandoned_queue_files_and_protects_active_ones(workspace, monkeypatch):
    client, _, _, first, _ = workspace
    monkeypatch.setattr(server, "MAX_UPLOAD_PATHS", 2)
    monkeypatch.setattr(server, "active_processes", {})

    def create():
        return client.post("/api/save_queue", json={"items": [{"path": str(first)}]})

    active = Path(create().json["path"])
    abandoned = Path(create().json["path"])
    server.active_processes["running-queue"] = {"path": str(active)}
    newest = Path(create().json["path"])
    assert active.exists()
    assert not abandoned.exists()
    assert newest.exists()
    assert len(server._generated_queues) == 2
    server.active_processes["new-running-queue"] = {"path": str(newest)}
    response = create()
    assert response.status_code == 429
    assert set(active.parent.glob("webui_queue_*.txt")) == {active, newest}


def test_queue_cleanup_never_deletes_outside_the_state_tmp_directory(workspace):
    _, root, _, _, _ = workspace
    outside = root / "webui_queue_external.txt"
    outside.touch()
    server._remove_generated_queue_file(str(outside))
    assert outside.exists()


def test_directory_inspection_is_reused_only_within_a_validation_phase(workspace, monkeypatch):
    client, root, _, first, second = workspace
    menus = root / "Fictional Menus"
    menus.mkdir()
    (menus / "image.png").touch()
    walks = []
    original_walk = policy.os.walk

    def count_walk(path, **kwargs):
        walks.append(str(path))
        yield from original_walk(path, **kwargs)

    monkeypatch.setattr(policy.os, "walk", count_walk)
    items = [{"path": str(path), "args": shlex.join(["--menus", str(menus)])} for path in (first, second)]
    response = client.post("/api/save_queue", json={"items": items})
    assert response.status_code == 200
    assert walks == [str(menus)]
    server._validate_execution_path(response.json["path"])
    assert walks == [str(menus)] * 2
    monkeypatch.setenv(ROOTS_ENV, json.dumps([str(root)]))
    validate_subprocess_queue([{"path": item["path"], "args": [item["path"], "--menus", str(menus)]} for item in items])
    assert walks == [str(menus)] * 3
    policy.validate_subprocess_path(str(menus))
    assert walks == [str(menus)] * 4
    external = root.parent / "external-menu-folder"
    external.mkdir()
    _directory_link(menus / "escaping-link", external)
    with pytest.raises(ValueError, match="outside allowed roots"):
        server._validate_execution_path(response.json["path"])


@pytest.mark.asyncio
async def test_invalid_interactive_path_reprompts_without_mutating_metadata(workspace, monkeypatch):
    import upload

    _, root, state, first, _ = workspace
    monkeypatch.setenv(ROOTS_ENV, json.dumps([str(root)]))
    meta = Meta(path=str(first), base_dir=str(state), imghost="fictional", category="MOVIE", item_args=[str(first)])
    prep = SimpleNamespace(gather_prep=AsyncMock(return_value=meta))
    monkeypatch.setattr(upload, "Prep", lambda **_kwargs: prep)
    monkeypatch.setattr(upload, "name_manager", SimpleNamespace(get_name=AsyncMock(return_value=("Fictional", "Fictional", "Fictional", []))), raising=False)
    monkeypatch.setattr(upload, "TrackerSetup", lambda **_kwargs: SimpleNamespace(filter_unsupported_trackers=lambda _meta: None))
    monkeypatch.setattr(upload, "UploadHelper", lambda _config: SimpleNamespace(get_confirmation=AsyncMock(return_value=False)))
    monkeypatch.setattr(upload, "write_meta_file", AsyncMock())
    monkeypatch.setattr(upload, "gen_desc", AsyncMock(return_value=meta))
    monkeypatch.setattr(upload, "_publish_webui_preview_target", Mock())
    external = root.parent / "external.mkv"
    external.touch()

    def parse(_args, candidate):
        candidate.path = str(external)
        candidate.anon = True
        return candidate, None, None

    monkeypatch.setattr(upload, "Args", lambda _config: SimpleNamespace(parse=parse))

    class RepromptedError(Exception):
        pass

    prompt = Mock(side_effect=["--anon", RepromptedError()])
    monkeypatch.setattr(upload, "CLI_UI", SimpleNamespace(ask_string=prompt))
    monkeypatch.setattr(upload, "config", {"DEFAULT": {"auto_mode": False}})
    with pytest.raises(RepromptedError):
        await upload.process_meta(meta, str(state))
    assert prompt.call_count == 2
    assert prep.gather_prep.await_count == 1
    assert meta.path == str(first)
    assert meta.anon is False
