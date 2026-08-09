import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.exercise import TargetStat
from app.models.user import User
from app.routers.deps import get_current_user, require_premium
from app.schemas.analytics import AnalyticsSummaryRead
from app.schemas.progress import StatHistoryPointRead, StatHistoryRead, TrainingStreakRead, UserStatRead
from app.schemas.push_subscription import (
    PushSubscriptionCreate,
    PushSubscriptionDelete,
    PushSubscriptionRead,
    PushTestResultRead,
)
from app.schemas.skill import UserSkillPreferenceRead, UserSkillPreferencesReplace
from app.schemas.user import UserDeleteRequest, UserRead, UserUpdate
from app.services.analytics_service import AnalyticsService
from app.services.progress_service import ProgressService
from app.services.push_subscription_service import PushSubscriptionService
from app.services.skill_service import SkillService
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.patch("/me", response_model=UserRead)
async def update_current_user(
    body: UserUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await UserService(session).update_profile(current_user, body)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_current_user(
    body: UserDeleteRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    await UserService(session).delete_account(current_user, body.password)


@router.post("/me/avatar", response_model=UserRead)
async def upload_avatar(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File()],
):
    return await UserService(session).update_avatar(current_user, file)


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


@router.get(
    "/me/analytics/stats-history",
    response_model=list[StatHistoryPointRead] | dict[TargetStat, list[StatHistoryPointRead]],
)
async def get_my_stats_history(
    current_user: Annotated[User, Depends(require_premium)],
    session: Annotated[AsyncSession, Depends(get_db)],
    stat_type: TargetStat | None = Query(default=None),
    days: int = Query(default=90, ge=1, le=3650),
):
    """{date, value} points for the last `days` days. With stat_type, a flat
    array for just that stat; without it, every stat's points in one
    response grouped by type (see ProgressService.get_stats_history) -- kept
    distinct from GET /me/stats/{stat_type}/history above, which returns the
    *entire* unfiltered history for one stat plus a synthetic live-decay
    point, for the existing per-stat detail view.
    """
    return await ProgressService(session).get_stats_history(current_user.id, stat_type, days)


@router.get(
    "/me/analytics/skills-history",
    response_model=list[StatHistoryPointRead] | dict[uuid.UUID, list[StatHistoryPointRead]],
)
async def get_my_skills_history(
    current_user: Annotated[User, Depends(require_premium)],
    session: Annotated[AsyncSession, Depends(get_db)],
    skill_id: uuid.UUID | None = Query(default=None),
    days: int = Query(default=90, ge=1, le=3650),
):
    """On-the-fly {date, value} skill-value time series -- skill value is
    never persisted (see SkillService.get_skill_value), so this replays
    Σ weight * get_effective_value against each weighted stat's historical
    StatHistory points instead of reading a stored series back (an
    approximation: today's SkillStatWeight config applied to historical stat
    values -- see SkillService._compute_skill_history for the exact
    reasoning). With skill_id, a flat array for just that skill; without it,
    every skill's points grouped by skill id.
    """
    service = SkillService(session)
    if skill_id is not None:
        return await service.get_skill_history(skill_id, current_user.id, days)
    return await service.get_all_skills_history(current_user.id, days)


@router.get("/me/analytics/summary", response_model=AnalyticsSummaryRead)
async def get_my_analytics_summary(
    current_user: Annotated[User, Depends(require_premium)],
    session: Annotated[AsyncSession, Depends(get_db)],
    days: int = Query(default=90, ge=1, le=3650),
):
    """Structured data for a frontend-assembled text summary (not
    ready-made copy -- see AnalyticsService.get_summary): the single
    biggest gainer across every stat and skill over `days`, the single
    biggest decliner (if any actually declined), the skill closest to its
    next milestone, and an honest decline_reason drawn from real decay
    state -- never a fabricated one.
    """
    return await AnalyticsService(session).get_summary(current_user, days)


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
    return await SkillService(session).replace_user_preferences(current_user, body.skill_ids)


@router.post("/me/push-subscription", response_model=PushSubscriptionRead)
async def save_push_subscription(
    body: PushSubscriptionCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    # FastAPI maps this to the "User-Agent" header (underscores -> hyphens
    # by default) -- server-observed metadata for "which device is this",
    # not something the client has to remember to send itself.
    user_agent: Annotated[str | None, Header()] = None,
):
    return await PushSubscriptionService(session).save(current_user.id, body, user_agent)


@router.delete("/me/push-subscription", status_code=status.HTTP_204_NO_CONTENT)
async def delete_push_subscription(
    body: PushSubscriptionDelete,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    await PushSubscriptionService(session).unsubscribe(current_user.id, body.endpoint)


@router.post("/me/push-subscription/test", response_model=PushTestResultRead)
async def send_test_push_notification(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    total, delivered = await PushSubscriptionService(session).send_test_notification(
        current_user.id
    )
    return PushTestResultRead(total_subscriptions=total, delivered=delivered)
