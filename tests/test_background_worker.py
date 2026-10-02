"""The worker exits non-zero when one of its loops ends on its own, so
Docker restarts it -- rather than staying "Up" with that loop silently gone.
"""
import asyncio

import pytest

from app.background import run_until_stopped_or_task_dies, stop_background_tasks


async def _forever() -> None:
    await asyncio.Event().wait()


async def _gives_up() -> None:
    return None


async def _crashes() -> None:
    raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_stop_signal_exits_cleanly() -> None:
    tasks = [asyncio.create_task(_forever()), asyncio.create_task(_forever())]
    stop = asyncio.Event()
    stop.set()

    assert await run_until_stopped_or_task_dies(tasks, stop) == 0
    await stop_background_tasks(tasks)


@pytest.mark.asyncio
@pytest.mark.parametrize("dying", [_gives_up, _crashes])
async def test_a_loop_ending_exits_non_zero(dying) -> None:
    tasks = [asyncio.create_task(_forever()), asyncio.create_task(dying())]

    assert await run_until_stopped_or_task_dies(tasks, asyncio.Event()) == 1
    # Shutdown must not re-raise the crashed task's error.
    await stop_background_tasks(tasks)
    assert all(task.done() for task in tasks)
