# ruff: noqa: S101
import json
import os
from pathlib import Path

import pytest

import web_ui.server as server


def _norm(path: Path) -> str:
    return os.path.normcase(os.path.realpath(path))


def _execute_events(monkeypatch: pytest.MonkeyPatch, target: Path, session_id: str) -> tuple[list[dict[str, object]], list[object]]:
    spawned: list[object] = []

    def fail_spawn(*_args: object) -> object:
        spawned.append(_args)
        raise AssertionError("conflicting execution must not spawn a process")

    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_validate_execution_path", lambda *_args, **_kwargs: str(target))
    monkeypatch.setattr(server, "_assert_safe_resolved_path", lambda _: None)
    monkeypatch.setattr(server, "_spawn_webui_upload_process", fail_spawn)
    response = server.app.test_client().post("/api/execute", json={"path": str(target), "session_id": session_id}, buffered=False)
    events = [json.loads(chunk.decode().removeprefix("data: ")) for chunk in response.response]
    return events, spawned


def test_execute_refuses_more_than_the_session_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    running = {f"tab-{index}": {"content_paths": frozenset({_norm(tmp_path / f"Fictional Show {index}")})} for index in range(server.MAX_CONCURRENT_SESSIONS)}
    monkeypatch.setattr(server, "active_processes", running)

    events, spawned = _execute_events(monkeypatch, tmp_path / "Fictional Film.mkv", "new-tab")

    assert events == [{"type": "error", "code": "capacity", "data": f"Maximum of {server.MAX_CONCURRENT_SESSIONS} concurrent uploads reached; wait for one to finish"}]
    assert not spawned
    assert "new-tab" not in server.active_processes
    assert len(server.active_processes) == server.MAX_CONCURRENT_SESSIONS


def test_execute_refuses_content_running_in_another_tab(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    season = tmp_path / "Fictional Show S01"
    monkeypatch.setattr(server, "active_processes", {"older-tab": {"content_paths": frozenset({_norm(season)})}})

    events, spawned = _execute_events(monkeypatch, season / "Fictional Show S01E01.mkv", "new-tab")

    assert events == [{"type": "error", "code": "duplicate", "data": "This content is already being uploaded in another tab"}]
    assert not spawned
    assert set(server.active_processes) == {"older-tab"}


def test_generated_queue_content_paths_cover_every_item(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = tmp_path / "Fictional Film.mkv"
    second = tmp_path / "Fictional Folder"
    queue = tmp_path / "webui_queue_fictional.txt"
    queue.write_text(f'"{first}"\n\n"{second}" --unattended\n', encoding="utf-8")
    monkeypatch.setattr(server, "_is_generated_queue", lambda _path: True)

    assert server._execution_content_paths(str(queue)) == frozenset({_norm(first), _norm(second)})


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        ("Fictional Show S01", "Fictional Show S01", True),
        ("Fictional Show S01", "Fictional Show S01/Fictional Show S01E01.mkv", True),
        ("Fictional Show S01", "Fictional Show S02", False),
        ("Fictional Show S01", "Fictional Show S01 Extras", False),
    ],
)
def test_content_path_overlap(tmp_path: Path, first: str, second: str, expected: bool) -> None:
    assert server._content_paths_overlap(frozenset({_norm(tmp_path / first)}), frozenset({_norm(tmp_path / second)})) is expected
