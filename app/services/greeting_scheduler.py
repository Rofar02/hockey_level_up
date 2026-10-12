"""Friendly pushes (2026-10-12, owner's request), same loop shape and
opt-out as report_reminder_scheduler: a player with reminders off
(ReminderPreference.NONE) gets none of these either.

- Birthday: at BIRTHDAY_LOCAL_TIME on the player's birthday in their own
  time zone (29 Feb on 28 Feb in a common year), once a year
  (users.last_birthday_greeted_year). A gift comes later.
- The day closed: from DAY_DONE_LOCAL_TIME until local midnight, once every
  training of the day is done -- a gym session with every exercise done or
  skipped (at least one done), an ice day or a game with its report sent
  (not "не был") -- a word of praise and the link to «Как прошёл день».
  Once a day (users.day_done_pushed_on).
"""
import asyncio
import calendar
import logging
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import AsyncSessionLocal
from app.models.push_subscription import PushSubscription
from app.models.schedule import DayPlan, DaySessionType, TrainingSession, WeeklyPlan
from app.models.training_diary import TrainingDiaryEntry
from app.models.user import ReminderPreference, User
from app.services.day_report_service import DayReportService
from app.services.push_service import send_push

logger = logging.getLogger(__name__)

TICK_INTERVAL_SECONDS = 300
BIRTHDAY_LOCAL_TIME = time(10, 0)
DAY_DONE_LOCAL_TIME = time(21, 30)
ICE_TYPES = (DaySessionType.ON_ICE, DaySessionType.GAME)


def _plural(count: int, forms: tuple[str, str, str]) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return forms[0]
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return forms[1]
    return forms[2]


def birthday_this_year(birth: date, year: int) -> date:
    if birth.month == 2 and birth.day == 29 and not calendar.isleap(year):
        return date(year, 2, 28)
    return date(year, birth.month, birth.day)


async def _push(session: AsyncSession, user: User, title: str, body: str, url: str) -> None:
    subscriptions = (
        await session.execute(select(PushSubscription).where(PushSubscription.user_id == user.id))
    ).scalars().all()
    for subscription in subscriptions:
        await send_push(session, subscription, title, body, url=url)


async def _greet_birthday(session: AsyncSession, user: User, now_local: datetime) -> None:
    if user.birth_date is None or user.last_birthday_greeted_year == now_local.year:
        return
    if now_local.date() != birthday_this_year(user.birth_date, now_local.year):
        return
    if now_local.time() < BIRTHDAY_LOCAL_TIME:
        return
    name = user.first_name.strip()
    await _push(
        session,
        user,
        f"С днём рождения{', ' + name if name else ''}! 🎂",
        "Команда IceLevel поздравляет! Пусть этот год принесёт быстрые ноги, точные броски и много побед.",
        "/",
    )
    # Set even on a failed delivery -- one try a year, never a repeat.
    user.last_birthday_greeted_year = now_local.year


async def _day_plans(session: AsyncSession, user: User, day: date) -> list[DayPlan]:
    return list(
        (
            await session.scalars(
                select(DayPlan)
                .join(WeeklyPlan, WeeklyPlan.id == DayPlan.weekly_plan_id)
                .where(WeeklyPlan.user_id == user.id, DayPlan.date == day)
                .options(selectinload(DayPlan.training_session).selectinload(TrainingSession.blocks))
            )
        ).all()
    )


async def day_is_done(session: AsyncSession, plans: list[DayPlan]) -> bool:
    """Every training of the day done, and at least one really trained."""
    trainings = [p for p in plans if p.session_type != DaySessionType.REST and p.training_session is not None]
    if not trainings:
        return False
    for plan in trainings:
        if plan.session_type in ICE_TYPES:
            entry = await session.scalar(
                select(TrainingDiaryEntry).where(TrainingDiaryEntry.training_session_id == plan.training_session.id)
            )
            if entry is None or entry.reported_at is None or entry.skipped:
                return False
        else:
            blocks = plan.training_session.blocks
            if (
                not blocks
                or any(b.completed_at is None and b.skipped_at is None for b in blocks)
                or all(b.completed_at is None for b in blocks)
            ):
                return False
    return True


async def _praise_the_day(session: AsyncSession, user: User, now_local: datetime) -> None:
    today = now_local.date()
    if user.day_done_pushed_on == today or now_local.time() < DAY_DONE_LOCAL_TIME:
        return
    plans = await _day_plans(session, user, today)
    if not await day_is_done(session, plans):
        return
    report = await DayReportService(session).report(user, today)
    parts = []
    if report.sets_total:
        parts.append(f"{report.sets_total} {_plural(report.sets_total, ('подход', 'подхода', 'подходов'))}")
    if report.tonnage_kg >= 1:
        parts.append(f"{round(report.tonnage_kg):,} кг".replace(",", " "))
    ice_minutes = sum((t.ice.duration_minutes or 0) for t in report.trainings if t.ice is not None)
    if ice_minutes:
        parts.append(f"{ice_minutes} мин на льду")
    double = sum(1 for t in report.trainings if t.session_type != DaySessionType.REST) > 1
    title = "Двойной день закрыт — мощно! 💪" if double else "Тренировка сделана — отличная работа! 💪"
    summary = f"{', '.join(parts)}. " if parts else ""
    await _push(
        session,
        user,
        title,
        f"{summary}Отчёт дня готов: какие мышцы нагрузили и что выросло.",
        f"/day-report/{today.isoformat()}",
    )
    user.day_done_pushed_on = today


async def _run_tick(session: AsyncSession, now_utc: datetime) -> None:
    has_subscription = select(PushSubscription.id).where(PushSubscription.user_id == User.id).exists()
    users = (
        await session.execute(
            select(User).where(User.reminder_preference != ReminderPreference.NONE, has_subscription)
        )
    ).scalars().all()
    for user in users:
        try:
            now_local = now_utc.astimezone(ZoneInfo(user.timezone))
        except Exception:
            logger.exception("Skipping greetings for user_id=%s: invalid timezone %r", user.id, user.timezone)
            continue
        await _greet_birthday(session, user, now_local)
        await _praise_the_day(session, user, now_local)


async def _greeting_tick() -> None:
    now_utc = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await _run_tick(session, now_utc)


async def run_greeting_scheduler() -> None:
    while True:
        try:
            await _greeting_tick()
        except Exception:
            logger.exception("Greeting scheduler tick failed")
        await asyncio.sleep(TICK_INTERVAL_SECONDS)
