"""Friendly pushes (2026-10-12, owner's request), same loop shape and
opt-out as report_reminder_scheduler: a player with reminders off
(ReminderPreference.NONE) gets none of these pushes either.

- Birthday (review 12.10, 4-5): from BIRTHDAY_LOCAL_TIME on the player's
  birthday in their own time zone (29 Feb on 28 Feb in a common year):
  - the gift, once a year (users.birthday_gift_year) and for everyone, push
    or not: +BIRTHDAY_XP and the coach's congratulation with the year in
    numbers as the newest message of the coach chat; and «🎂 Сегодня день
    рождения у …» to the teammates -- both sides with team_birthdays on;
  - the greeting push, once a year (users.last_birthday_greeted_year).
- The day closed: from DAY_DONE_LOCAL_TIME until local midnight, once every
  training of the day is done -- a gym session with every exercise done or
  skipped (at least one done), an ice day or a game with its report sent
  (not "не был") -- a word of praise and the link to «Как прошёл день».
  Once a day (users.day_done_pushed_on); a game day has its own words.

Review 12.10, 1: every player is handled on their own -- a failure rolls
back that player only and the loop goes on. The "sent" mark is committed
before the push goes out, so a crash afterwards never sends it twice.
"""
import asyncio
import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.coach_chat import CoachChatMessage, CoachChatRole
from app.models.exercise import TargetStat
from app.models.push_subscription import PushSubscription
from app.models.schedule import DayPlan, DaySessionType, TrainingSession, WeeklyPlan
from app.models.team import TeamMembership
from app.models.training_diary import TrainingDiaryEntry
from app.models.user import ReminderPreference, User, birthday_in
from app.services.day_report_service import DayReportService
from app.services.push_service import send_push
from app.services.stat_award import award_xp

logger = logging.getLogger(__name__)

TICK_INTERVAL_SECONDS = 300
BIRTHDAY_LOCAL_TIME = time(9, 0)
BIRTHDAY_XP = 200
DAY_DONE_LOCAL_TIME = time(21, 30)
ICE_TYPES = (DaySessionType.ON_ICE, DaySessionType.GAME)

BIRTHDAY_COACH_INSTRUCTIONS = (
    "Сегодня у игрока день рождения. Напиши ему поздравление от себя как от "
    "тренера: тепло, по-хоккейному, на \"ты\", по-русски, до 80 слов, без "
    "заголовков и списков. Подведи итог его года в приложении 1-2 цифрами из "
    "данных ниже (не перечисляй всё подряд) и закончи одним пожеланием на "
    "новый год жизни. Скажи, что в подарок от IceLevel ему начислено "
    f"+{BIRTHDAY_XP} XP. Используй только факты из данных, ничего не "
    "выдумывай, не упоминай \"данные\" или \"приложение\" как систему."
)

# Kept for the tests and older imports.
birthday_this_year = birthday_in


def _plural(count: int, forms: tuple[str, str, str]) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return forms[0]
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return forms[1]
    return forms[2]


def _is_birthday(user: User, now_local: datetime) -> bool:
    return (
        user.birth_date is not None
        and now_local.date() == birthday_in(user.birth_date, now_local.year)
        and now_local.time() >= BIRTHDAY_LOCAL_TIME
    )


def _local_now(user_timezone: str | None, now_utc: datetime) -> datetime | None:
    try:
        return now_utc.astimezone(ZoneInfo(user_timezone or "UTC"))
    except Exception:
        return None


async def _push(session: AsyncSession, user_id: uuid.UUID, title: str, body: str, url: str) -> None:
    subscriptions = (
        await session.execute(select(PushSubscription).where(PushSubscription.user_id == user_id))
    ).scalars().all()
    for subscription in subscriptions:
        await send_push(session, subscription, title, body, url=url)


# --- The birthday gift ------------------------------------------------------


async def _year_facts(session: AsyncSession, user: User) -> list[str]:
    """The year since the last birthday, in a few numbers. Best-effort."""
    from app.services.analytics_overview_service import AnalyticsOverviewService
    from app.services.coach_chat_service import STAT_LABELS

    overview = await AnalyticsOverviewService(session).get_overview(user, 365)
    regularity = overview.regularity
    facts = [f"Тренировок выполнено за год: {regularity.completed_sessions}."]
    if overview.records:
        best = ", ".join(r.exercise_name for r in overview.records[:3])
        facts.append(f"Личных рекордов: {len(overview.records)} (например: {best}).")
    gains = sorted((s for s in overview.stats if s.delta > 0), key=lambda s: s.delta, reverse=True)
    if gains:
        top = ", ".join(
            f"{STAT_LABELS.get(TargetStat(s.stat), s.stat)} +{s.delta:.0f}" for s in gains[:2]
        )
        facts.append(f"Больше всего выросло: {top}.")
    facts.append(f"Уровень сейчас: {user.level}.")
    return facts


def _template_congratulation(user: User, facts: list[str]) -> str:
    name = user.first_name.strip()
    year = " ".join(facts[:2])
    return (
        f"С днём рождения{', ' + name if name else ''}! 🎂\n\n"
        + (f"Оглянись на свой год: {year[0].lower() + year[1:]}\n\n" if year else "")
        + f"В подарок от IceLevel — +{BIRTHDAY_XP} XP. Пусть новый год жизни принесёт быстрые ноги, "
        "точные броски и много побед. Вперёд!"
    )


async def _coach_congratulation(session: AsyncSession, user: User) -> CoachChatMessage:
    """The coach's own words when the model answers, else a template --
    the gift never waits on the model."""
    try:
        facts = await _year_facts(session, user)
    except Exception:
        logger.exception("Birthday: year facts failed for user_id=%s", user.id)
        facts = []
    settings = get_settings()
    if settings.zai_api_key:
        try:
            from app.services import coach_chat_service
            from app.services.coach_personality_prompts import PERSONALITY_SYSTEM_PROMPTS
            from app.services.coach_philosophy import COACH_VOICE

            age = f"Исполняется лет: {user.age}.\n" if user.age is not None else ""
            reply = await coach_chat_service.call_zai_clean(
                settings.zai_api_key,
                settings.zai_base_url,
                settings.coach_chat_model,
                f"{PERSONALITY_SYSTEM_PROMPTS[user.coach_personality]}\n\n{COACH_VOICE}\n\n{BIRTHDAY_COACH_INSTRUCTIONS}",
                [{"role": "user", "content": f"Имя: {user.first_name}.\n{age}" + "\n".join(facts)}],
            )
            text = reply.text.strip()
            if text:
                return CoachChatMessage(
                    user_id=user.id,
                    role=CoachChatRole.ASSISTANT,
                    content=text,
                    llm_model=settings.coach_chat_model,
                    prompt_tokens=reply.usage.prompt_tokens,
                    cached_tokens=reply.usage.cached_tokens,
                    completion_tokens=reply.usage.completion_tokens,
                    reasoning_tokens=reply.usage.reasoning_tokens,
                )
        except Exception:
            logger.exception("Birthday: coach model failed for user_id=%s, using the template", user.id)
    return CoachChatMessage(user_id=user.id, role=CoachChatRole.ASSISTANT, content=_template_congratulation(user, facts))


async def _teammates_to_tell(session: AsyncSession, user: User) -> list[uuid.UUID]:
    my_teams = select(TeamMembership.team_id).where(TeamMembership.user_id == user.id)
    has_subscription = select(PushSubscription.id).where(PushSubscription.user_id == User.id).exists()
    return list(
        (
            await session.scalars(
                select(User.id)
                .join(TeamMembership, TeamMembership.user_id == User.id)
                .where(
                    TeamMembership.team_id.in_(my_teams),
                    User.id != user.id,
                    User.team_birthdays.is_(True),
                    User.reminder_preference != ReminderPreference.NONE,
                    has_subscription,
                )
                .distinct()
            )
        ).all()
    )


async def _give_birthday_gift(session: AsyncSession, user: User, now_local: datetime) -> None:
    if not _is_birthday(user, now_local) or user.birthday_gift_year == now_local.year:
        return
    message = await _coach_congratulation(session, user)
    # One transaction: the mark, the XP and the message -- never twice.
    user.birthday_gift_year = now_local.year
    session.add(message)
    await award_xp(session, user.id, BIRTHDAY_XP)
    await session.commit()

    if not user.team_birthdays:
        return
    name = " ".join(part for part in (user.first_name.strip(), user.last_name.strip()) if part)
    for teammate_id in await _teammates_to_tell(session, user):
        await _push(
            session,
            teammate_id,
            f"🎂 Сегодня день рождения у {name or 'тиммейта'}",
            "Не забудьте поздравить — в команде это ценят!",
            f"/profile/{user.id}",
        )
    await session.commit()


def _gift_candidates(now_utc: datetime):
    """Birthdays on yesterday's, today's or tomorrow's UTC date -- every
    time zone's "today" is among them; the exact check is per player."""
    days = [(now_utc + timedelta(days=shift)).date() for shift in (-1, 0, 1)]
    month_days = {d.strftime("%m-%d") for d in days}
    if "02-28" in month_days:
        month_days.add("02-29")
    return select(User.id, User.timezone).where(
        User.birth_date.is_not(None), func.to_char(User.birth_date, "MM-DD").in_(month_days)
    )


# --- The pushes -------------------------------------------------------------


async def _greet_birthday(session: AsyncSession, user: User, now_local: datetime) -> None:
    if not _is_birthday(user, now_local) or user.last_birthday_greeted_year == now_local.year:
        return
    name = user.first_name.strip()
    gift = user.birthday_gift_year == now_local.year
    title = f"С днём рождения{', ' + name if name else ''}! 🎂"
    body = (
        f"Команда IceLevel поздравляет! В подарок +{BIRTHDAY_XP} XP, а тренер оставил тебе пару слов в чате."
        if gift
        else "Команда IceLevel поздравляет! Пусть этот год принесёт быстрые ноги, точные броски и много побед."
    )
    # Marked and committed first: a crash after the send never repeats it.
    user.last_birthday_greeted_year = now_local.year
    await session.commit()
    await _push(session, user.id, title, body, "/coach" if gift else "/")
    await session.commit()


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
    """Every training of the day closed -- the same rule as Home's «Все
    тренировки дня сделаны» (an ice report counts even as «не был», a gym
    session once each exercise is done or skipped) -- and at least one of
    them really trained."""
    trainings = [p for p in plans if p.session_type != DaySessionType.REST and p.training_session is not None]
    trained = False
    for plan in trainings:
        if plan.session_type in ICE_TYPES:
            entry = await session.scalar(
                select(TrainingDiaryEntry).where(TrainingDiaryEntry.training_session_id == plan.training_session.id)
            )
            if entry is None or entry.reported_at is None:
                return False
            trained = trained or not entry.skipped
        else:
            blocks = plan.training_session.blocks
            if not blocks or any(b.completed_at is None and b.skipped_at is None for b in blocks):
                return False
            trained = trained or any(b.completed_at is not None for b in blocks)
    return trained


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
        parts.append(f"{round(report.tonnage_kg):,} кг".replace(",", " "))
    ice_minutes = sum((t.ice.duration_minutes or 0) for t in report.trainings if t.ice is not None)
    if ice_minutes:
        parts.append(f"{ice_minutes} мин на льду")
    trained = [
        t for t in report.trainings
        if (t.ice is not None and not t.ice.skipped) or (t.ice is None and t.exercises_done > 0)
    ]
    summary = f"{', '.join(parts)}. " if parts else ""
    if any(t.session_type == DaySessionType.GAME and t.ice is not None for t in trained):
        # Review 12.10, 9: after a game it's the rest that matters.
        title = "Игра сыграна — теперь восстановление 🏒"
        body = f"{summary}Сон, вода и лёгкая растяжка — завтра ноги скажут спасибо. Отчёт дня готов."
    else:
        title = "Двойной день закрыт — мощно! 💪" if len(trained) > 1 else "Тренировка сделана — отличная работа! 💪"
        body = f"{summary}Отчёт дня готов: какие мышцы нагрузили и что выросло."
    user.day_done_pushed_on = today
    await session.commit()
    await _push(session, user.id, title, body, f"/day-report/{today.isoformat()}")
    await session.commit()


# --- The loop ---------------------------------------------------------------


async def _for_each_user(session: AsyncSession, rows, now_utc: datetime, handle, what: str) -> None:
    for user_id, user_timezone in rows:
        now_local = _local_now(user_timezone, now_utc)
        if now_local is None:
            logger.error("Skipping %s for user_id=%s: invalid timezone %r", what, user_id, user_timezone)
            continue
        try:
            user = await session.get(User, user_id)
            if user is not None:
                await handle(session, user, now_local)
        except Exception:
            # This player only -- the rest of the tick goes on.
            await session.rollback()
            logger.exception("%s failed for user_id=%s", what, user_id)


async def _greet_and_praise(session: AsyncSession, user: User, now_local: datetime) -> None:
    await _greet_birthday(session, user, now_local)
    await _praise_the_day(session, user, now_local)


async def _run_tick(session: AsyncSession, now_utc: datetime) -> None:
    gift_rows = (await session.execute(_gift_candidates(now_utc))).all()
    await _for_each_user(session, gift_rows, now_utc, _give_birthday_gift, "Birthday gift")

    has_subscription = select(PushSubscription.id).where(PushSubscription.user_id == User.id).exists()
    push_rows = (
        await session.execute(
            select(User.id, User.timezone).where(
                User.reminder_preference != ReminderPreference.NONE, has_subscription
            )
        )
    ).all()
    await _for_each_user(session, push_rows, now_utc, _greet_and_praise, "Greetings")


async def _greeting_tick() -> None:
    now_utc = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        await _run_tick(session, now_utc)
        await session.commit()


async def run_greeting_scheduler() -> None:
    while True:
        try:
            await _greeting_tick()
        except Exception:
            logger.exception("Greeting scheduler tick failed")
        await asyncio.sleep(TICK_INTERVAL_SECONDS)
