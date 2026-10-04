import contextlib
from collections.abc import AsyncIterator
from pathlib import Path

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.background import start_background_tasks, stop_background_tasks
from app.core.config import get_settings
from app.events.publisher import close_publisher
from app.routers import (
    admin_users,
    assessment,
    auth,
    drill_templates,
    exercises,
    feedback,
    friends,
    leaderboard,
    push,
    quests,
    reference_articles,
    schedule,
    session_blocks,
    set_completions,
    skills,
    team_events,
    team_ice_schedule_templates,
    teams,
    training_block,
    training_parties,
    training_sessions,
    users,
)

settings = get_settings()

if settings.glitchtip_dsn:
    # traces_sample_rate=0 -- error tracking only, not APM/performance
    # tracing (a single-VM, low-traffic app has nothing that budget would
    # usefully surface right now, and it's extra overhead per request for
    # no current benefit). Revisit if request-latency visibility is ever
    # actually needed.
    sentry_sdk.init(dsn=settings.glitchtip_dsn, environment=settings.environment, traces_sample_rate=0.0)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Off on prod's multi-worker backend -- see Settings.run_background_tasks.
    tasks = start_background_tasks() if settings.run_background_tasks else []
    yield
    await stop_background_tasks(tasks)
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
app.include_router(feedback.router)
app.include_router(teams.router)
app.include_router(team_events.router)
app.include_router(team_ice_schedule_templates.router)
app.include_router(drill_templates.router)
app.include_router(friends.router)
app.include_router(training_parties.router)
app.include_router(quests.router)

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
