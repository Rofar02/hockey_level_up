import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.routers.deps import get_current_user
from app.routers.optional import OptionalFlag, or_none
from app.core.config import get_settings
from app.schemas.schedule import (
    ScheduleFeaturesRead,
    DayPlanRead,
    WeeklyPlanCreate,
    WeeklyPlanPatch,
    WeeklyPlanPatchResult,
    WeeklyPlanRead,
)
from app.services.schedule_service import ScheduleService

router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.post("/weekly", response_model=WeeklyPlanRead, status_code=status.HTTP_201_CREATED)
async def create_weekly_plan(
    payload: WeeklyPlanCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await ScheduleService(session).create_weekly_plan(current_user, payload)


@router.get("/features", response_model=ScheduleFeaturesRead)
async def get_schedule_features(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Optional week features switched on (release plan step 6)."""
    settings = get_settings()
    return ScheduleFeaturesRead(
        double_days=settings.double_days_enabled, offline_queue=settings.offline_queue_enabled
    )


@router.get("/weekly/current", response_model=WeeklyPlanRead | None)
async def get_current_weekly_plan(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    optional: OptionalFlag = False,
):
    return await or_none(ScheduleService(session).get_current_weekly_plan(current_user), optional)


@router.patch("/weekly/current", response_model=WeeklyPlanPatchResult)
async def patch_current_weekly_plan(
    payload: WeeklyPlanPatch,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await ScheduleService(session).patch_current_weekly_plan(current_user, payload)


# Parametrized siblings of the two /current endpoints above, which are left
# untouched for backward compatibility. week_start_date is optional and
# aliases to "current" (via date.today()) when omitted, so these two routes
# are strict supersets of /weekly/current -- existing clients that only know
# about /current keep working unmodified, new callers (e.g. "plan/view next
# week") use these instead.
@router.get("/weekly", response_model=WeeklyPlanRead | None)
async def get_weekly_plan(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    week_start_date: Annotated[date | None, Query()] = None,
    optional: OptionalFlag = False,
):
    return await or_none(ScheduleService(session).get_weekly_plan(current_user, week_start_date), optional)


@router.patch("/weekly", response_model=WeeklyPlanPatchResult)
async def patch_weekly_plan(
    payload: WeeklyPlanPatch,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    week_start_date: Annotated[date | None, Query()] = None,
):
    return await ScheduleService(session).patch_weekly_plan(current_user, payload, week_start_date)


# A single day by exact date, independent of which week is "current"/"next"
# -- backs HomePage's activity-calendar day-detail modal, which otherwise can
# only show block-by-block detail for a day inside the currently-loaded
# WeeklyPlan (see ScheduleService.get_day_plan_for_date's own docstring).
@router.get("/day-plan", response_model=DayPlanRead | None)
async def get_day_plan(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    date_: Annotated[date, Query(alias="date")],
    optional: OptionalFlag = False,
):
    return await or_none(ScheduleService(session).get_day_plan_for_date(current_user, date_), optional)


# A single day by id, from any week -- TrainingSessionPage/TrainingDiaryPage
# open a day by the id in their URL (DiaryPage links there for entries of any
# age), see ScheduleService.get_day_plan_by_id.
@router.get("/day-plans/{day_plan_id}", response_model=DayPlanRead)
async def get_day_plan_by_id(
    day_plan_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await ScheduleService(session).get_day_plan_by_id(current_user, day_plan_id)
