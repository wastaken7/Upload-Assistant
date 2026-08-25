# ruff: noqa: S101

import asyncio

from src import early_tasks
from src.console import progress_display, suppress_cli_progress
from src.webui_progress import PROGRESS_STDOUT_PREFIX, clear_progress_callback, publish_progress, set_progress_callback


async def _wait_for_cancellation(cancelled: asyncio.Event) -> None:
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        cancelled.set()
        raise


def test_cancel_and_drain_early_tasks_cancels_both_tasks() -> None:
    async def exercise() -> None:
        cancelled = asyncio.Event()
        release_id = "early-task-test"
        tasks = (
            asyncio.create_task(_wait_for_cancellation(cancelled)),
            asyncio.create_task(_wait_for_cancellation(cancelled)),
        )
        early_tasks._early_artifact_tasks[release_id] = tasks  # pyright: ignore[reportPrivateUsage]

        await asyncio.sleep(0)
        await early_tasks.cancel_and_drain_early_artifact_tasks(release_id)

        assert cancelled.is_set()
        assert all(task.cancelled() for task in tasks)
        assert early_tasks.get_early_artifact_tasks(release_id) is None

    asyncio.run(exercise())


def test_release_early_artifact_progress_releases_its_gate() -> None:
    release_id = "progress-gate-test"
    gate = early_tasks.CliProgressGate()
    early_tasks._early_progress_gates[release_id] = gate  # pyright: ignore[reportPrivateUsage]

    with suppress_cli_progress(gate), progress_display() as progress:
        assert not progress.live.is_started
        early_tasks.release_early_artifact_progress(release_id)
        assert progress.live.is_started

    assert gate.released
    early_tasks._early_progress_gates.pop(release_id)


def test_released_gate_keeps_new_progress_on_its_live_display() -> None:
    gate = early_tasks.CliProgressGate()

    with suppress_cli_progress(gate), progress_display() as first:
        gate.release()
        with progress_display() as second:
            assert second is first


def test_release_early_artifact_progress_stays_hidden_with_webui_callback() -> None:
    release_id = "webui-progress-gate-test"
    gate = early_tasks.CliProgressGate()
    early_tasks._early_progress_gates[release_id] = gate  # pyright: ignore[reportPrivateUsage]
    set_progress_callback(lambda _event: None)

    try:
        early_tasks.release_early_artifact_progress(release_id)
        assert not gate.released
    finally:
        clear_progress_callback()
        early_tasks._early_progress_gates.pop(release_id)


def test_finishing_run_cannot_clear_newer_webui_progress_callback() -> None:
    def old_callback(_event: object) -> None:
        pass

    def new_callback(_event: object) -> None:
        pass

    set_progress_callback(old_callback)
    set_progress_callback(new_callback)

    try:
        clear_progress_callback(old_callback)
        assert early_tasks.has_progress_callback()
    finally:
        clear_progress_callback(new_callback)


def test_webui_subprocess_progress_uses_structured_stdout(monkeypatch, capsys) -> None:
    monkeypatch.setenv("UA_WEBUI_PROGRESS_STDOUT", "1")

    publish_progress("hash", "Hashing", current=9, total=100)

    output = capsys.readouterr().out
    assert output.strip().startswith(PROGRESS_STDOUT_PREFIX)
    assert '"id":"hash"' in output
