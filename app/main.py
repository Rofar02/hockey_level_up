import asyncio
import contextlib
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.events.consumer import run_consumer
from app.events.outbox_relay import run_outbox_relay
from app.events.publisher import close_publisher
from app.routers import (
    admin_users,
    assessment,
    auth,
    exercises,
    leaderboard,
    push,
    reference_articles,
    schedule,
    session_blocks,
    set_completions,
    skills,
    teams,
    training_block,
    training_sessions,
    users,
)
from app.services.reminder_scheduler import run_reminder_scheduler

settings = get_settings()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    consumer_task = asyncio.create_task(run_consumer())
    relay_task = asyncio.create_task(run_outbox_relay())
    reminder_task = asyncio.create_task(run_reminder_scheduler())
    yield
    consumer_task.cancel()
    relay_task.cancel()
    reminder_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await consumer_task
    with contextlib.suppress(asyncio.CancelledError):
        await relay_task
    with contextlib.suppress(asyncio.CancelledError):
        await reminder_task
    await close_publisher()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # None (not "") disables allow_origin_regex outright -- an empty string
    # would otherwise match as a regex against every origin.
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(exercises.router)
app.include_router(users.router)
app.include_router(schedule.router)
app.include_router(session_blocks.router)
app.include_router(set_completions.router)
app.include_router(assessment.router)
app.include_router(skills.router)
app.include_router(training_block.router)
app.include_router(training_sessions.router)
app.include_router(reference_articles.router)
app.include_router(leaderboard.router)
app.include_router(push.router)
app.include_router(admin_users.router)
app.include_router(teams.router)

# Mounted at the shared parent of avatar_upload_dir and
# reference_article_image_upload_dir, so "/static/avatars/..." and
# "/static/reference-articles/..." both serve from it; the directory is
# created up front since StaticFiles errors at mount time if it doesn't
# exist yet.
static_root = Path(settings.avatar_upload_dir).parent
static_root.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_root)), name="static")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
