"""Long-running background loops: the RabbitMQ consumer, the outbox relay,
the reminder / check-in / team-event schedulers, the coach memory
summarizer and the daily event-table cleanup.

Started by the API's lifespan when settings.run_background_tasks is true
(local dev: one process does everything), or on their own:

    python -m app.background

which is what prod's `worker` service runs, so the multi-worker `backend`
service can set RUN_BACKGROUND_TASKS=false and every loop still runs
exactly once.

Every loop is meant to run until cancelled. If one ends on its own -- the
consumer gives up when its first RabbitMQ connect fails, or a loop raises
past its own try/except -- the worker exits non-zero so Docker restarts it,
instead of living on with that loop silently gone (XP/stats/streaks stop
being applied while the container still shows "Up").
"""
import asyncio
import logging
import signal
import sys

import sentry_sdk

from app.core.config import get_settings
from app.events.consumer import run_consumer
from app.events.outbox_relay import run_outbox_relay
from app.events.publisher import close_publisher
from app.services.checkin_scheduler import run_checkin_scheduler
from app.services.coach_memory_service import run_coach_memory_scheduler
from app.services.event_retention import run_event_retention
from app.services.reminder_scheduler import run_reminder_scheduler
from app.services.team_event_scheduler import run_team_event_scheduler


def start_background_tasks() -> list[asyncio.Task]:
    return [
        asyncio.create_task(run_consumer()),
        asyncio.create_task(run_outbox_relay()),
        asyncio.create_task(run_reminder_scheduler()),
        asyncio.create_task(run_checkin_scheduler()),
        asyncio.create_task(run_team_event_scheduler()),
        asyncio.create_task(run_event_retention()),
        asyncio.create_task(run_coach_memory_scheduler()),
    ]


async def stop_background_tasks(tasks: list[asyncio.Task]) -> None:
    for task in tasks:
        task.cancel()
    # return_exceptions: a task that already died with an error (see
    # run_until_stopped_or_task_dies) must not re-raise here and skip the rest
    # of shutdown.
    await asyncio.gather(*tasks, return_exceptions=True)


logger = logging.getLogger(__name__)


async def run_until_stopped_or_task_dies(tasks: list[asyncio.Task], stop: asyncio.Event) -> int:
    """Returns the process exit code: 0 on a stop signal, 1 if a loop ended."""
    stop_waiter = asyncio.create_task(stop.wait())
    try:
        done, _ = await asyncio.wait([stop_waiter, *tasks], return_when=asyncio.FIRST_COMPLETED)
    finally:
        stop_waiter.cancel()
    dead = [task for task in tasks if task in done]
    for task in dead:
        error = None if task.cancelled() else task.exception()
        # logger.error reaches GlitchTip through sentry_sdk's logging integration.
        logger.error(
            "Background task %s ended unexpectedly; exiting so the worker restarts",
            task.get_coro().__qualname__,
            exc_info=error,
        )
    return 1 if dead else 0


async def _run_forever() -> int:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)
    tasks = start_background_tasks()
    try:
        return await run_until_stopped_or_task_dies(tasks, stop)
    finally:
        await stop_background_tasks(tasks)
        await close_publisher()


if __name__ == "__main__":
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if settings.glitchtip_dsn:
        sentry_sdk.init(dsn=settings.glitchtip_dsn, environment=settings.environment, traces_sample_rate=0.0)
    sys.exit(asyncio.run(_run_forever()))
