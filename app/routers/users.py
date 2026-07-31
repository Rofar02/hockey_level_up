from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.exercise import TargetStat
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.progress import StatHistoryRead, TrainingStreakRead, UserStatRead
from app.schemas.skill import UserSkillPreferenceRead, UserSkillPreferencesReplace
from app.schemas.user import UserRead, UserUpdate
from app.services.progress_service import ProgressService
from app.services.skill_service import SkillService
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.patch("/me", response_model=UserRead)
async def update_current_user(
    body: UserUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await UserService(session).update_equipment_access(current_user, body.equipment_access)


@router.get("/me/stats", response_model=list[UserStatRead])
async def get_my_stats(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await ProgressService(session).list_user_stats(current_user.id)


@router.get("/me/stats/{stat_type}/history", response_model=list[StatHistoryRead])
async def get_my_stat_history(
    stat_type: TargetStat,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await ProgressService(session).list_stat_history(current_user.id, stat_type)


@router.get("/me/streak", response_model=TrainingStreakRead)
async def get_my_streak(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await ProgressService(session).get_streak(current_user.id)


@router.get("/me/skill-preferences", response_model=list[UserSkillPreferenceRead])
async def get_my_skill_preferences(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await SkillService(session).list_user_preferences(current_user.id)


@router.put("/me/skill-preferences", response_model=list[UserSkillPreferenceRead])
async def replace_my_skill_preferences(
    body: UserSkillPreferencesReplace,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await SkillService(session).replace_user_preferences(current_user.id, body.skill_ids)
