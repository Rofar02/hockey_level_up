"""Ice and game days that are over but still have no report (2026-10-10).

Since the ice reaches the muscle map only through its report (no default
any more), a forgotten one leaves the next gym day planning blind -- Home
shows these, and a gym day asks for them before it starts.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schedule import DayPlan, DaySessionType, TrainingSession, WeeklyPlan
from app.models.team_event import TeamEvent
from app.models.training_diary import TrainingDiaryEntry
from app.models.user import User
from app.schemas.schedule import PendingReportRead
from app.services.report_reminder_scheduler import REPORT_DELAY, report_due_at

LOOKBACK_DAYS = 3


async def pending_reports(session: AsyncSession, user: User, now: datetime | None = None) -> list[PendingReportRead]:
    now = now or datetime.now(timezone.utc)
    try:
        tz = ZoneInfo(user.timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    today = now.astimezone(tz).date()
    reported = (
        select(TrainingDiaryEntry.id)
        .where(
            TrainingDiaryEntry.training_session_id == TrainingSession.id,
            TrainingDiaryEntry.reported_at.is_not(None),
        )
        .exists()
    )
    rows = (
        await session.execute(
            select(DayPlan, TrainingSession.id)
            .join(WeeklyPlan, WeeklyPlan.id == DayPlan.weekly_plan_id)
            .join(TrainingSession, TrainingSession.day_plan_id == DayPlan.id)
            .where(
                WeeklyPlan.user_id == user.id,
                DayPlan.date.between(today - timedelta(days=LOOKBACK_DAYS), today),
                DayPlan.session_type.in_((DaySessionType.ON_ICE, DaySessionType.GAME)),
                ~reported,
            )
            .order_by(DayPlan.date.desc())
        )
    ).all()
    pending = []
    for day_plan, _ in rows:
        event = await session.get(TeamEvent, day_plan.team_event_id) if day_plan.team_event_id else None
        # Over = the report reminder's own clock, minus its delay.
        if report_due_at(day_plan, event, tz) - REPORT_DELAY > now:
            continue
        pending.append(
            PendingReportRead(
                day_plan_id=day_plan.id, date=day_plan.date, session_type=day_plan.session_type,
                team_event_id=day_plan.team_event_id,
            )
        )
    return pending
