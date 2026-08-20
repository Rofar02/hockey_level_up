import uuid
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.exercise import EquipmentItem, TargetStat
from app.models.user import User
from app.routers.deps import get_current_user, require_premium
from app.schemas.analytics import AnalyticsSummaryRead
from app.schemas.coach_chat import CoachChatMessageCreate, CoachChatMessageRead, CoachChatReplyRead
from app.schemas.exercise import EquipmentItemsReplace
from app.schemas.progress import (
    ActivityCalendarDayRead,
    MuscleLoadRead,
    StatHistoryPointRead,
    StatHistoryRead,
    TrainingStreakRead,
    UserStatRead,
)
from app.schemas.push_subscription import (
    PushSubscriptionCreate,
    PushSubscriptionDelete,
    PushSubscriptionRead,
    PushTestResultRead,
)
from app.schemas.skill import UserSkillPreferenceRead, UserSkillPreferencesReplace
from app.schemas.user import UserDeleteRequest, UserPublicRead, UserRead, UserUpdate
from app.services.analytics_service import AnalyticsService
from app.services.coach_chat_service import CoachChatService
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


@router.post("/me/onboarding-tour-seen", response_model=UserRead)
async def mark_onboarding_tour_seen(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await UserService(session).mark_onboarding_tour_seen(current_user)


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


@router.get("/me/muscle-loads", response_model=list[MuscleLoadRead])
async def get_my_muscle_loads(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Body-muscles map (2026-08-20 planning session). Only muscle groups
    with at least one UserMuscleLoad row are returned, same "absent means
    baseline, not an explicit zero row" convention as GET /me/stats --
    the frontend body-map component defaults any of the 8 MuscleGroup
    values missing from this list to intensity 0."""
    return await ProgressService(session).list_muscle_loads(current_user.id)


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


@router.post("/me/coach-chat", response_model=CoachChatReplyRead)
async def send_coach_chat_message(
    body: CoachChatMessageCreate,
    current_user: Annotated[User, Depends(require_premium)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Premium gates *access*; a 503 here means access is fine but the
    feature isn't technically switched on yet (no Anthropic API key
    configured -- see Settings.anthropic_api_key), which is a different
    state from the 403 require_premium raises."""
    reply = await CoachChatService(session).send_message(current_user, body.message)
    return CoachChatReplyRead(reply=reply)


@router.get("/me/coach-chat/history", response_model=list[CoachChatMessageRead])
async def get_coach_chat_history(
    current_user: Annotated[User, Depends(require_premium)],
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=200),
):
    return await CoachChatService(session).list_history(current_user.id, limit)


@router.get("/me/streak", response_model=TrainingStreakRead)
async def get_my_streak(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await ProgressService(session).get_streak(current_user.id)


def _month_bounds(month: date) -> tuple[date, date]:
    """(first day, last day) of the calendar month `month` falls in --
    factored out from get_my_activity_calendar so the December-wraparound
    edge (next month is January of the *next* year) has its own test
    instead of only being exercised indirectly through the endpoint."""
    from_date = month.replace(day=1)
    to_date = (
        date(month.year, month.month + 1, 1) if month.month < 12 else date(month.year + 1, 1, 1)
    ) - timedelta(days=1)
    return from_date, to_date


@router.get("/me/activity-calendar", response_model=list[ActivityCalendarDayRead])
async def get_my_activity_calendar(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    month: date = Query(..., description="Any date within the target month"),
):
    """Real completion history for a calendar month -- replaces the
    frontend's old fallback of "current week's WeeklyPlan + a single
    TrainingStreak.last_activity_date marker" (see HomePage.tsx's own
    comment on why that was a stand-in, not the real thing).
    """
    from_date, to_date = _month_bounds(month)
    return await ProgressService(session).get_activity_calendar(
        current_user.id, from_date=from_date, to_date=to_date
    )


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


@router.get("/me/equipment-items", response_model=list[EquipmentItem])
async def get_my_equipment_items(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await UserService(session).list_owned_equipment(current_user.id)


@router.put("/me/equipment-items", response_model=list[EquipmentItem])
async def replace_my_equipment_items(
    body: EquipmentItemsReplace,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await UserService(session).replace_owned_equipment(current_user.id, body.equipment_items)


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


@router.get("/{user_id}/profile", response_model=UserPublicRead)
async def get_user_public_profile(
    user_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """403s unless user_id is a friend or a teammate of current_user (see
    UserService.get_public_profile) -- no open profile browsing, matching
    the "no open name search for regular users" call in the diagnosis. No
    other /{user_id}-shaped route exists on this router yet, so there's no
    "/me"-style ordering landmine to worry about here today.
    """
    return await UserService(session).get_public_profile(current_user, user_id)
