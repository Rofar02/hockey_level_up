"""Background loop that pushes "you have training today/tomorrow" reminders,
same while-True/asyncio.sleep pattern as app/events/outbox_relay.py.

Known limitation: User.timezone is a manually-set IANA zone name (there's no
server-side way to verify it matches where the user actually is), and the
5-minute tick / 5-minute window pairing means a slow tick could in theory
miss a window on a long-uptime process -- acceptable for a best-effort
reminder, not a guarantee.
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
from app.models.schedule import DayPlan, DaySessionType, WeeklyPlan
from app.models.user import ReminderPreference, User
from app.services.push_service import send_push

logger = logging.getLogger(__name__)

TICK_INTERVAL_SECONDS = 300

REMINDER_TITLE = "IceLevel"

_REMINDER_WINDOWS: dict[ReminderPreference, tuple[time, time]] = {
    ReminderPreference.MORNING: (time(9, 0), time(9, 5)),
    ReminderPreference.EVENING: (time(19, 0), time(19, 5)),
}

_SESSION_TYPE_TEXT: dict[DaySessionType, str] = {
    DaySessionType.ON_ICE: "на льду",
    DaySessionType.OFF_ICE: "в зале",
}


def _target_date(preference: ReminderPreference, local_today: date_) -> date_:
    if preference == ReminderPreference.MORNING:
        return local_today
    return local_today + timedelta(days=1)


def _reminder_body(preference: ReminderPreference, session_type: DaySessionType) -> str:
    day_word = "Сегодня" if preference == ReminderPreference.MORNING else "Завтра"
    if session_type == DaySessionType.GAME:
        # Not in _SESSION_TYPE_TEXT (that dict feeds "тренировка X", which
        # reads wrong for a game) and _due_day_plan's query already includes
        # every non-REST day, GAME included, so this needs its own phrasing
        # rather than a KeyError.
        return f"{day_word} игра — не забудьте про разминку и настрой"
    return f"{day_word} тренировка {_SESSION_TYPE_TEXT[session_type]}"


async def _eligible_users(session: AsyncSession) -> list[User]:
    has_subscription = (
        select(PushSubscription.id).where(PushSubscription.user_id == User.id).exists()
    )
    query = select(User).where(
        User.reminder_preference != ReminderPreference.NONE, has_subscription
    )
    result = await session.execute(query)
    return list(result.scalars().all())


async def _due_day_plan(
    session: AsyncSession, user_id: object, target_date: date_
) -> DayPlan | None:
    query = (
        select(DayPlan)
        .join(WeeklyPlan, DayPlan.weekly_plan_id == WeeklyPlan.id)
        .where(
            WeeklyPlan.user_id == user_id,
            DayPlan.date == target_date,
            DayPlan.session_type != DaySessionType.REST,
            DayPlan.reminder_sent_at.is_(None),
        )
    )
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def _remind_user(session: AsyncSession, user: User, day_plan: DayPlan) -> None:
    result = await session.execute(
        select(PushSubscription).where(PushSubscription.user_id == user.id)
    )
    subscriptions = list(result.scalars().all())
    body = _reminder_body(user.reminder_preference, day_plan.session_type)
    for subscription in subscriptions:
        await send_push(session, subscription, REMINDER_TITLE, body)
    # Set even on partial/total delivery failure -- a dead endpoint or a
    # down push service must not turn into a resend attempt on every tick
    # for the rest of the window (push delivery is already best-effort
    # elsewhere in this app, see PushSubscriptionService.send_test_notification).
    day_plan.reminder_sent_at = datetime.now(timezone.utc)


async def _run_tick(session: AsyncSession, now_utc: datetime) -> None:
    users = await _eligible_users(session)
    for user in users:
        try:
            local_now = now_utc.astimezone(ZoneInfo(user.timezone))
        except Exception:
            logger.exception(
                "Skipping reminder check for user_id=%s: invalid timezone %r",
                user.id,
                user.timezone,
            )
            continue

        window_start, window_end = _REMINDER_WINDOWS[user.reminder_preference]
        if not (window_start <= local_now.time() < window_end):
            continue

        target_date = _target_date(user.reminder_preference, local_now.date())
        day_plan = await _due_day_plan(session, user.id, target_date)
        if day_plan is None:
            continue

        await _remind_user(session, user, day_plan)


async def _reminder_tick() -> None:
    now_utc = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await _run_tick(session, now_utc)


async def run_reminder_scheduler() -> None:
    while True:
        try:
            await _reminder_tick()
        except Exception:
            logger.exception("Reminder scheduler tick failed")
        await asyncio.sleep(TICK_INTERVAL_SECONDS)
