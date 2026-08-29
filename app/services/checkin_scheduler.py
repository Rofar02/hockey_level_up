"""Background loop that pushes a "your restriction expired -- how are you
feeling?" check-in once a UserTemporaryRestriction's expires_at has passed,
same while-True/asyncio.sleep pattern as app/services/reminder_scheduler.py
(and app/events/outbox_relay.py before it).

No AI involved (P3 #10, first pass, per the roadmap's own "the broadcast
itself needs no AI" note) -- purely templated text, personality-flavored via
coach_personality_phrases.get_checkin_body. Parsing the player's reply
("fine now" / "still hurts") to auto-lift the restriction is a later, AI-
backed layer, not built here.

Independent of ReminderPreference -- a user with reminders off entirely can
still get a check-in, since it isn't a training reminder. The only
prerequisite is having a live PushSubscription, same eligibility gate
reminder_scheduler uses.
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
from app.models.user import User
from app.models.user_temporary_restriction import UserTemporaryRestriction
from app.services.coach_personality_phrases import get_checkin_body
from app.services.push_service import send_push

logger = logging.getLogger(__name__)

TICK_INTERVAL_SECONDS = 300

# Not "IceLevel" -- see reminder_scheduler.REMINDER_TITLE's own comment on
# why (the OS/browser already shows the PWA's name; repeating it as the
# notification's own title just doubles it up).
CHECKIN_TITLE = "Проверка самочувствия"

# Same 5-minute morning window as reminder_scheduler's MORNING preference,
# checked independently -- not imported from there, since this job's
# trigger (a restriction's expiry) has nothing to do with the reminder
# system's own state.
_CHECKIN_WINDOW: tuple[time, time] = (time(9, 0), time(9, 5))


async def _eligible_users(session: AsyncSession) -> list[User]:
    has_subscription = (
        select(PushSubscription.id).where(PushSubscription.user_id == User.id).exists()
    )
    result = await session.execute(select(User).where(has_subscription))
    return list(result.scalars().all())


async def _due_restrictions(
    session: AsyncSession, user_id: object, local_today: date_
) -> list[UserTemporaryRestriction]:
    yesterday = local_today - timedelta(days=1)
    query = select(UserTemporaryRestriction).where(
        UserTemporaryRestriction.user_id == user_id,
        UserTemporaryRestriction.expires_at.in_((yesterday, local_today)),
        UserTemporaryRestriction.checkin_sent_at.is_(None),
    )
    result = await session.execute(query)
    return list(result.scalars().all())


async def _checkin_user(
    session: AsyncSession, user: User, restriction: UserTemporaryRestriction
) -> None:
    result = await session.execute(
        select(PushSubscription).where(PushSubscription.user_id == user.id)
    )
    subscriptions = list(result.scalars().all())
    body = get_checkin_body(user.coach_personality)
    for subscription in subscriptions:
        await send_push(session, subscription, CHECKIN_TITLE, body)
    # Set even on partial/total delivery failure -- same reasoning as
    # DayPlan.reminder_sent_at in reminder_scheduler: a dead endpoint must
    # not turn into a resend attempt on every tick for the rest of the
    # window.
    restriction.checkin_sent_at = datetime.now(timezone.utc)


async def _run_tick(session: AsyncSession, now_utc: datetime) -> None:
    users = await _eligible_users(session)
    for user in users:
        try:
            local_now = now_utc.astimezone(ZoneInfo(user.timezone))
        except Exception:
            logger.exception(
                "Skipping check-in for user_id=%s: invalid timezone %r",
                user.id,
                user.timezone,
            )
            continue

        window_start, window_end = _CHECKIN_WINDOW
        if not (window_start <= local_now.time() < window_end):
            continue

        restrictions = await _due_restrictions(session, user.id, local_now.date())
        for restriction in restrictions:
            await _checkin_user(session, user, restriction)


async def _checkin_tick() -> None:
    now_utc = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await _run_tick(session, now_utc)


async def run_checkin_scheduler() -> None:
    while True:
        try:
            await _checkin_tick()
        except Exception:
            logger.exception("Check-in scheduler tick failed")
        await asyncio.sleep(TICK_INTERVAL_SECONDS)
