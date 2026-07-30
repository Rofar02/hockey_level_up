import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app.core.config import get_settings
from app.events.consumer import run_consumer
from app.events.outbox_relay import run_outbox_relay
from app.events.publisher import close_publisher
from app.routers import assessment, auth, exercises, schedule, session_blocks, skills, users

settings = get_settings()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    consumer_task = asyncio.create_task(run_consumer())
    relay_task = asyncio.create_task(run_outbox_relay())
    yield
    consumer_task.cancel()
    relay_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await consumer_task
    with contextlib.suppress(asyncio.CancelledError):
        await relay_task
    await close_publisher()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(auth.router)
app.include_router(exercises.router)
app.include_router(users.router)
app.include_router(schedule.router)
app.include_router(session_blocks.router)
app.include_router(assessment.router)
app.include_router(skills.router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
