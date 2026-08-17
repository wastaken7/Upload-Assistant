import asyncio
import json
import time

import psutil

from src import post_upload_hooks
from src.meta import Meta


def test_hook_receives_meta_and_relays_output(tmp_path, monkeypatch, caplog):
    hooks_dir = tmp_path / "custom_hooks"
    hooks_dir.mkdir()
    (hooks_dir / "notify.py").write_text(
        "import json, sys\npayload = json.load(sys.stdin)\nprint(f\"received {payload['meta']['name']}\", flush=True)\nprint('hook warning', file=sys.stderr, flush=True)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(post_upload_hooks, "HOOKS_DIR", hooks_dir)

    asyncio.run(post_upload_hooks.run_post_upload_hooks(Meta(name="Example.Release"), {"DEFAULT": {"post_upload_hooks": ["notify.py"]}}))

    assert "[hook: notify] received Example.Release" in caplog.text  # noqa: S101
    assert "[hook: notify] hook warning" in caplog.text  # noqa: S101


def test_hook_payload_is_versioned(tmp_path, monkeypatch):
    hooks_dir = tmp_path / "custom_hooks"
    hooks_dir.mkdir()
    received = tmp_path / "payload.json"
    (hooks_dir / "save.py").write_text(
        f"import json, sys\nopen({str(received)!r}, 'w', encoding='utf-8').write(sys.stdin.read())\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(post_upload_hooks, "HOOKS_DIR", hooks_dir)

    asyncio.run(post_upload_hooks.run_post_upload_hooks(Meta(name="Example.Release"), {"DEFAULT": {"post_upload_hooks": ["save.py"]}}))

    payload = json.loads(received.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1  # noqa: S101
    assert payload["event"] == "upload.finished"  # noqa: S101
    assert payload["meta"]["name"] == "Example.Release"  # noqa: S101
    assert payload["meta"]["tracker_status"] == {}  # noqa: S101


def test_invalid_hook_path_is_not_run(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(post_upload_hooks, "HOOKS_DIR", tmp_path / "custom_hooks")

    asyncio.run(post_upload_hooks.run_post_upload_hooks(Meta(), {"DEFAULT": {"post_upload_hooks": ["../outside.py"]}}))

    assert "Ignoring invalid post-upload hook" in caplog.text  # noqa: S101


def test_inprocess_hook_receives_an_isolated_meta_copy(tmp_path, monkeypatch):
    hooks_dir = tmp_path / "custom_hooks"
    hooks_dir.mkdir()
    observed = tmp_path / "observed.txt"
    (hooks_dir / "mutate.py").write_text(
        f"def on_upload_finished(meta, config):\n    meta.name = 'changed'\n    config['DEFAULT']['value'] = 'changed'\n    open({str(observed)!r}, 'w', encoding='utf-8').write(meta.name + config['DEFAULT']['value'])\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(post_upload_hooks, "HOOKS_DIR", hooks_dir)
    meta = Meta(name="Example.Release")

    config = {"DEFAULT": {"post_upload_inprocess_hooks": ["mutate.py"], "value": "original"}}
    asyncio.run(post_upload_hooks.run_post_upload_hooks(meta, config))

    assert observed.read_text(encoding="utf-8") == "changedchanged"  # noqa: S101
    assert meta.name == "Example.Release"  # noqa: S101
    assert config["DEFAULT"]["value"] == "original"  # noqa: S101


def test_timeout_terminates_hook_child_processes(tmp_path, monkeypatch):
    hooks_dir = tmp_path / "custom_hooks"
    hooks_dir.mkdir()
    child_pid_file = tmp_path / "child.pid"
    (hooks_dir / "spawn_child.py").write_text(
        "import subprocess, sys, time\n"
        f"child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\nopen({str(child_pid_file)!r}, 'w').write(str(child.pid))\ntime.sleep(60)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(post_upload_hooks, "HOOKS_DIR", hooks_dir)

    started = time.monotonic()
    asyncio.run(post_upload_hooks.run_post_upload_hooks(Meta(), {"DEFAULT": {"post_upload_hooks": ["spawn_child.py"], "post_upload_hook_timeout": 0.1}}))

    assert time.monotonic() - started < 5  # noqa: S101
    child_pid = int(child_pid_file.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 2
    while psutil.pid_exists(child_pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not psutil.pid_exists(child_pid)  # noqa: S101
