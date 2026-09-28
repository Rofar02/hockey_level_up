"""Long-running background loops: the RabbitMQ consumer, the outbox relay and
the reminder / check-in / team-event schedulers.

Started by the API's lifespan when settings.run_background_tasks is true
(local dev: one process does everything), or on their own:

    python -m app.background

which is what prod's `worker` service runs, so the multi-worker `backend`
service can set RUN_BACKGROUND_TASKS=false and every loop still runs
exactly once.
"""
import asyncio
import contextlib
import logging
import signal

import sentry_sdk

from app.core.config import get_settings
from app.events.consumer import run_consumer
from app.events.outbox_relay import run_outbox_relay
from app.events.publisher import close_publisher
from app.services.checkin_scheduler import run_checkin_scheduler
from app.services.reminder_scheduler import run_reminder_scheduler
from app.services.team_event_scheduler import run_team_event_scheduler


def start_background_tasks() -> list[asyncio.Task]:
    return [
        asyncio.create_task(run_consumer()),
        asyncio.create_task(run_outbox_relay()),
        asyncio.create_task(run_reminder_scheduler()),
        asyncio.create_task(run_checkin_scheduler()),
        asyncio.create_task(run_team_event_scheduler()),
    ]


async def stop_background_tasks(tasks: list[asyncio.Task]) -> None:
    for task in tasks:
        task.cancel()
    for task in tasks:
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def _run_forever() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)
    tasks = start_background_tasks()
    try:
        await stop.wait()
    finally:
        await stop_background_tasks(tasks)
        await close_publisher()


if __name__ == "__main__":
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if settings.glitchtip_dsn:
        sentry_sdk.init(dsn=settings.glitchtip_dsn, environment=settings.environment, traces_sample_rate=0.0)
    asyncio.run(_run_forever())
