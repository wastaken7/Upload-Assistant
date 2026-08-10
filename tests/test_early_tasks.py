# ruff: noqa: S101

import asyncio

from src import early_tasks


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
