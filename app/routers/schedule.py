from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.schedule import (
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


@router.get("/weekly/current", response_model=WeeklyPlanRead)
async def get_current_weekly_plan(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await ScheduleService(session).get_current_weekly_plan(current_user)


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
@router.get("/weekly", response_model=WeeklyPlanRead)
async def get_weekly_plan(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    week_start_date: Annotated[date | None, Query()] = None,
):
    return await ScheduleService(session).get_weekly_plan(current_user, week_start_date)


@router.patch("/weekly", response_model=WeeklyPlanPatchResult)
async def patch_weekly_plan(
    payload: WeeklyPlanPatch,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    week_start_date: Annotated[date | None, Query()] = None,
):
    return await ScheduleService(session).patch_weekly_plan(current_user, payload, week_start_date)
