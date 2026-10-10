"""Background loop that asks "how did the ice/game go?" a couple of hours
after an ON_ICE/GAME day (2026-10-08), so the report -- the only thing that
earns that day's stats -- actually gets filled in. Same while-True /
asyncio.sleep shape as reminder_scheduler.py, and the same opt-out: a player
with training reminders off (ReminderPreference.NONE) gets none of these
either.

When: REPORT_DELAY after the day is assumed over. A team event has a start
time but no length, so a typical one is assumed (TEAM_EVENT_LENGTH); a day
the player marked themselves has no time at all, so it's asked at
OWN_DAY_LOCAL_TIME. A reminder more than STALE_AFTER late (the worker was
down, say) is dropped rather than sent the next morning.

Still no report the next morning: one more ask at FOLLOWUP_LOCAL_TIME
(2026-10-10) -- since then the ice reaches the muscle map only through the
report, so a forgotten one leaves the next gym day planning blind.
"""
import asyncio
import logging
from datetime import date as date_
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.push_subscription import PushSubscription
from app.models.schedule import DayPlan, DaySessionType, TrainingSession, WeeklyPlan
from app.models.team_event import TeamEvent, TeamEventType
from app.models.training_diary import TrainingDiaryEntry
from app.models.user import ReminderPreference, User
from app.services.push_service import send_push

logger = logging.getLogger(__name__)

TICK_INTERVAL_SECONDS = 300

REPORT_DELAY = timedelta(hours=2)
TEAM_EVENT_LENGTH: dict[TeamEventType, timedelta] = {
    TeamEventType.TRAINING: timedelta(minutes=90),
    TeamEventType.GAME: timedelta(hours=2),
}
OWN_DAY_LOCAL_TIME = time(21, 0)
STALE_AFTER = timedelta(hours=12)
FOLLOWUP_LOCAL_TIME = time(9, 0)
FOLLOWUP_TITLES: dict[DaySessionType, str] = {
    DaySessionType.ON_ICE: "Отметьте вчерашний лёд",
    DaySessionType.GAME: "Отметьте вчерашнюю игру",
}
FOLLOWUP_BODY = "От этого зависит нагрузка на ноги в зале — без отчёта приложение не знает, что вы катались."

REPORT_TITLES: dict[DaySessionType, str] = {
    DaySessionType.ON_ICE: "Как прошёл лёд?",
    DaySessionType.GAME: "Как сыграли?",
}
REPORT_BODIES: dict[DaySessionType, str] = {
    DaySessionType.ON_ICE: "Пара тапов — и очки за день ваши.",
    DaySessionType.GAME: "Отметьте результат — очки за игру ваши, а тренер учтёт её в разборе недели.",
}


def report_due_at(day_plan: DayPlan, event: TeamEvent | None, tz: ZoneInfo) -> datetime:
    if event is not None:
        return event.starts_at + TEAM_EVENT_LENGTH[event.event_type] + REPORT_DELAY
    return datetime.combine(day_plan.date, OWN_DAY_LOCAL_TIME, tzinfo=tz)


async def _candidate_days(session: AsyncSession, user: User, local_today: date_) -> list[DayPlan]:
    """Today's and yesterday's ice/game days still without a sent report
    (a note saved while typing doesn't count, 2026-10-10) and not yet
    reminded."""
    query = (
        select(DayPlan)
        .join(WeeklyPlan, DayPlan.weekly_plan_id == WeeklyPlan.id)
        .where(
            WeeklyPlan.user_id == user.id,
            DayPlan.date.between(local_today - timedelta(days=1), local_today),
            DayPlan.session_type.in_((DaySessionType.ON_ICE, DaySessionType.GAME)),
            DayPlan.report_reminder_sent_at.is_(None),
            ~_reported(),
        )
    )
    return list((await session.execute(query)).scalars().all())


def _reported():
    return (
        select(TrainingDiaryEntry.id)
        .join(TrainingSession, TrainingSession.id == TrainingDiaryEntry.training_session_id)
        .where(TrainingSession.day_plan_id == DayPlan.id, TrainingDiaryEntry.reported_at.is_not(None))
        .exists()
    )


async def _followup_days(session: AsyncSession, user: User, local_today: date_) -> list[DayPlan]:
    """Yesterday's ice/game days still without a report, not yet asked a
    second time."""
    query = (
        select(DayPlan)
        .join(WeeklyPlan, DayPlan.weekly_plan_id == WeeklyPlan.id)
        .where(
            WeeklyPlan.user_id == user.id,
            DayPlan.date == local_today - timedelta(days=1),
            DayPlan.session_type.in_((DaySessionType.ON_ICE, DaySessionType.GAME)),
            DayPlan.report_followup_sent_at.is_(None),
            ~_reported(),
        )
    )
    return list((await session.execute(query)).scalars().all())


async def _follow_up(session: AsyncSession, user: User, day_plan: DayPlan) -> None:
    subscriptions = (
        await session.execute(select(PushSubscription).where(PushSubscription.user_id == user.id))
    ).scalars().all()
    for subscription in subscriptions:
        await send_push(
            session,
            subscription,
            FOLLOWUP_TITLES[day_plan.session_type],
            FOLLOWUP_BODY,
            url=f"/training/{day_plan.id}/diary",
        )
    day_plan.report_followup_sent_at = datetime.now(timezone.utc)


async def _remind(session: AsyncSession, user: User, day_plan: DayPlan) -> None:
    subscriptions = (
        await session.execute(select(PushSubscription).where(PushSubscription.user_id == user.id))
    ).scalars().all()
    for subscription in subscriptions:
        await send_push(
            session,
            subscription,
            REPORT_TITLES[day_plan.session_type],
            REPORT_BODIES[day_plan.session_type],
            url=f"/training/{day_plan.id}/diary",
        )
    # Set even on a failed delivery, same reasoning as reminder_scheduler.
    day_plan.report_reminder_sent_at = datetime.now(timezone.utc)


async def _run_tick(session: AsyncSession, now_utc: datetime) -> None:
    has_subscription = select(PushSubscription.id).where(PushSubscription.user_id == User.id).exists()
    users = (
        await session.execute(
            select(User).where(User.reminder_preference != ReminderPreference.NONE, has_subscription)
        )
    ).scalars().all()
    for user in users:
        try:
            tz = ZoneInfo(user.timezone)
        except Exception:
            logger.exception("Skipping report reminders for user_id=%s: invalid timezone %r", user.id, user.timezone)
            continue
        local_today = now_utc.astimezone(tz).date()
        for day_plan in await _candidate_days(session, user, local_today):
            event = await session.get(TeamEvent, day_plan.team_event_id) if day_plan.team_event_id else None
            due = report_due_at(day_plan, event, tz)
            if due <= now_utc < due + STALE_AFTER:
                await _remind(session, user, day_plan)
        for day_plan in await _followup_days(session, user, local_today):
            due = datetime.combine(local_today, FOLLOWUP_LOCAL_TIME, tzinfo=tz)
            if due <= now_utc < due + STALE_AFTER:
                await _follow_up(session, user, day_plan)


async def _report_reminder_tick() -> None:
    now_utc = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await _run_tick(session, now_utc)


async def run_report_reminder_scheduler() -> None:
    while True:
        try:
            await _report_reminder_tick()
        except Exception:
            logger.exception("Report reminder scheduler tick failed")
        await asyncio.sleep(TICK_INTERVAL_SECONDS)
