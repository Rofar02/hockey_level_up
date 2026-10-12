"""Friendly pushes (2026-10-12): the birthday greeting once a year on the
player's own date, and the evening praise once every training of the day
is done -- with the link to «Как прошёл день». webpush is monkeypatched."""
import json
import uuid
from datetime import date, datetime, timezone

import pytest

from app.models.exercise import Exercise, ExerciseCategory, TrainingPhase
from app.models.push_subscription import PushSubscription
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.training_diary import TrainingDiaryEntry
from app.models.user import ReminderPreference, User
from app.services import push_service
from app.services.greeting_scheduler import _run_tick, birthday_this_year

TODAY = date(2026, 3, 10)


def _at(hour: int, minute: int = 0, day: date = TODAY) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)


async def _user(db_session, **overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    fields = dict(
        id=uuid.uuid4(), username=f"gr_{unique}", email=f"gr_{unique}@example.com", password_hash="x",
        reminder_preference=ReminderPreference.EVENING, timezone="UTC", first_name="Лёша",
    )
    fields.update(overrides)
    user = User(**fields)
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        PushSubscription(
            id=uuid.uuid4(), user_id=user.id, endpoint=f"https://push.example.com/{uuid.uuid4().hex}",
            p256dh_key="k", auth_key="a", user_agent="pytest",
        )
    )
    await db_session.flush()
    return user


def _capture(monkeypatch) -> list[dict]:
    sent: list[dict] = []

    async def _fake(*_args, **kwargs):
        sent.append(json.loads(kwargs["data"]))
        return "ok"

    monkeypatch.setattr(push_service, "webpush_async", _fake)
    return sent


async def _tick(db_session, now: datetime) -> None:
    await _run_tick(db_session, now)
    await db_session.commit()


def test_29_february_is_greeted_on_the_28th_in_a_common_year() -> None:
    assert birthday_this_year(date(2008, 2, 29), 2026) == date(2026, 2, 28)
    assert birthday_this_year(date(2008, 2, 29), 2028) == date(2028, 2, 29)


@pytest.mark.asyncio
async def test_birthday_greeting_once_from_nine_local(db_session, monkeypatch) -> None:
    sent = _capture(monkeypatch)
    user = await _user(db_session, birth_date=date(2000, 3, 10), timezone="Asia/Vladivostok")  # UTC+10

    await _tick(db_session, _at(22, 55, date(2026, 3, 9)))  # 08:55 local on the 10th
    assert sent == []
    await _tick(db_session, _at(23, 5, date(2026, 3, 9)))  # 09:05 local
    await _tick(db_session, _at(1, 0))
    assert [p["title"] for p in sent] == ["С днём рождения, Лёша! 🎂"]
    assert "+200 XP" in sent[0]["body"] and sent[0]["url"] == "/coach"
    await db_session.refresh(user)
    assert user.last_birthday_greeted_year == 2026


@pytest.mark.asyncio
async def test_no_greeting_on_another_day_or_with_reminders_off(db_session, monkeypatch) -> None:
    sent = _capture(monkeypatch)
    await _user(db_session, birth_date=date(2000, 3, 11))
    await _user(db_session, birth_date=date(2000, 3, 10), reminder_preference=ReminderPreference.NONE)

    await _tick(db_session, _at(12, 0))

    assert sent == []


async def _gym_day(db_session, user: User, *, done: bool) -> DayPlan:
    exercise = Exercise(
        id=uuid.uuid4(), name=f"gr ex {uuid.uuid4().hex[:6]}", category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN, difficulty_level=3,
    )
    db_session.add(exercise)
    await db_session.flush()
    now = datetime.now(timezone.utc)
    blocks = [
        SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=0, completed_at=now),
        SessionBlock(
            id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=1,
            completed_at=now if done else None,
        ),
    ]
    day = DayPlan(
        id=uuid.uuid4(), date=TODAY, session_type=DaySessionType.OFF_ICE,
        training_session=TrainingSession(id=uuid.uuid4(), blocks=blocks),
    )
    db_session.add(WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=TODAY, day_plans=[day]))
    await db_session.flush()
    return day


@pytest.mark.asyncio
async def test_a_done_day_is_praised_once_in_the_evening(db_session, monkeypatch) -> None:
    sent = _capture(monkeypatch)
    user = await _user(db_session)
    await _gym_day(db_session, user, done=True)

    await _tick(db_session, _at(21, 0))
    assert sent == []
    await _tick(db_session, _at(21, 32))
    await _tick(db_session, _at(22, 0))

    assert len(sent) == 1
    assert sent[0]["title"].startswith("Тренировка сделана")
    assert "Отчёт дня готов" in sent[0]["body"]
    assert sent[0]["url"] == f"/day-report/{TODAY.isoformat()}"


@pytest.mark.asyncio
async def test_an_unfinished_day_is_not_praised(db_session, monkeypatch) -> None:
    sent = _capture(monkeypatch)
    user = await _user(db_session)
    await _gym_day(db_session, user, done=False)

    await _tick(db_session, _at(22, 0))

    assert sent == []


@pytest.mark.asyncio
async def test_ice_counts_only_with_a_sent_report_not_skipped(db_session, monkeypatch) -> None:
    sent = _capture(monkeypatch)
    user = await _user(db_session)
    ice = TrainingSession(id=uuid.uuid4(), blocks=[])
    day = DayPlan(id=uuid.uuid4(), date=TODAY, session_type=DaySessionType.ON_ICE, training_session=ice)
    db_session.add(WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=TODAY, day_plans=[day]))
    await db_session.flush()
    entry = TrainingDiaryEntry(user_id=user.id, training_session_id=ice.id, skipped=True, reported_at=_at(20, 0))
    db_session.add(entry)
    await db_session.flush()

    await _tick(db_session, _at(21, 40))
    assert sent == []

    entry.skipped = False
    entry.duration_minutes = 60
    await _tick(db_session, _at(21, 50))
    assert len(sent) == 1 and "60 мин на льду" in sent[0]["body"]


@pytest.mark.asyncio
async def test_skipped_ice_plus_done_gym_is_praised(db_session, monkeypatch) -> None:
    """«Не был» on the ice closes it, same as on Home -- the gym trained."""
    sent = _capture(monkeypatch)
    user = await _user(db_session)
    gym_day = await _gym_day(db_session, user, done=True)
    gym_day.is_extra = True
    gym_day.time_of_day = "morning"
    ice = TrainingSession(id=uuid.uuid4(), blocks=[])
    plan = await db_session.get(WeeklyPlan, gym_day.weekly_plan_id)
    plan.day_plans.append(
        DayPlan(id=uuid.uuid4(), date=TODAY, session_type=DaySessionType.ON_ICE, time_of_day="evening", training_session=ice)
    )
    await db_session.flush()
    db_session.add(TrainingDiaryEntry(user_id=user.id, training_session_id=ice.id, skipped=True, reported_at=_at(20, 0)))
    await db_session.flush()

    await _tick(db_session, _at(21, 40))

    assert len(sent) == 1 and sent[0]["title"].startswith("Тренировка сделана")


@pytest.mark.asyncio
async def test_a_failing_player_never_stops_or_repeats_the_others(db_session, monkeypatch) -> None:
    """Review 12.10, 1: an error on the 2nd player rolls back only theirs;
    the 1st and the 3rd get the push once, the next tick sends nothing."""
    from app.services import greeting_scheduler

    sent = _capture(monkeypatch)
    users = [await _user(db_session) for _ in range(3)]
    for user in users:
        await _gym_day(db_session, user, done=True)
    await db_session.commit()
    order = {user.id: index for index, user in enumerate(users)}
    real_report = greeting_scheduler.DayReportService.report

    async def _report(self, user, day):
        if order.get(user.id) == 1:
            raise RuntimeError("boom")
        return await real_report(self, user, day)

    monkeypatch.setattr(greeting_scheduler.DayReportService, "report", _report)
    # Only our three, in a fixed order.
    real_rows = greeting_scheduler._for_each_user

    async def _ours(session, rows, now_utc, handle, what):
        mine = sorted((r for r in rows if r[0] in order), key=lambda r: order[r[0]])
        await real_rows(session, mine, now_utc, handle, what)

    monkeypatch.setattr(greeting_scheduler, "_for_each_user", _ours)

    await _tick(db_session, _at(21, 40))
    assert len(sent) == 2
    await _tick(db_session, _at(21, 50))
    assert len(sent) == 2
    for index, user in enumerate(users):
        await db_session.refresh(user)
        assert (user.day_done_pushed_on == TODAY) == (index != 1)


@pytest.mark.asyncio
async def test_any_push_error_is_caught(db_session, monkeypatch) -> None:
    async def _broken(*_args, **_kwargs):
        raise ConnectionError("network down")

    monkeypatch.setattr(push_service, "webpush_async", _broken)
    user = await _user(db_session)
    await _gym_day(db_session, user, done=True)

    await _tick(db_session, _at(21, 40))

    await db_session.refresh(user)
    assert user.day_done_pushed_on == TODAY  # marked, never retried


@pytest.mark.asyncio
async def test_birthday_gift_once_with_xp_coach_word_and_the_team(db_session, monkeypatch) -> None:
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.models.coach_chat import CoachChatMessage
    from app.models.team import Team, TeamMembership

    monkeypatch.setattr(get_settings(), "zai_api_key", "")  # the template, no model call
    sent = _capture(monkeypatch)
    hero = await _user(db_session, birth_date=date(2000, 3, 10), first_name="Иван", last_name="Петров",
                       reminder_preference=ReminderPreference.NONE, level=1, xp=0)
    mate = await _user(db_session)
    quiet = await _user(db_session, team_birthdays=False)
    outsider = await _user(db_session)
    team = Team(id=uuid.uuid4(), name="gr team", owner_id=hero.id, invite_code=uuid.uuid4().hex[:12])
    db_session.add(team)
    await db_session.flush()
    for member in (hero, mate, quiet):
        db_session.add(TeamMembership(id=uuid.uuid4(), team_id=team.id, user_id=member.id))
    await db_session.flush()
    assert outsider.id is not None

    await _tick(db_session, _at(8, 55))
    assert sent == []
    await _tick(db_session, _at(9, 5))
    await _tick(db_session, _at(12, 0))

    assert [p["title"] for p in sent] == ["🎂 Сегодня день рождения у Иван Петров"]
    assert sent[0]["url"] == f"/profile/{hero.id}"
    await db_session.refresh(hero)
    from app.events.handlers.block_completed import xp_to_next_level

    assert hero.birthday_gift_year == 2026
    assert (hero.level, hero.xp) == (2, 200 - xp_to_next_level(1))
    messages = (await db_session.scalars(select(CoachChatMessage).where(CoachChatMessage.user_id == hero.id))).all()
    assert len(messages) == 1 and "С днём рождения, Иван" in messages[0].content and "+200 XP" in messages[0].content


@pytest.mark.asyncio
async def test_a_game_day_has_its_own_evening_words(db_session, monkeypatch) -> None:
    sent = _capture(monkeypatch)
    user = await _user(db_session)
    game = TrainingSession(id=uuid.uuid4(), blocks=[])
    day = DayPlan(id=uuid.uuid4(), date=TODAY, session_type=DaySessionType.GAME, training_session=game)
    db_session.add(WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=TODAY, day_plans=[day]))
    await db_session.flush()
    db_session.add(
        TrainingDiaryEntry(user_id=user.id, training_session_id=game.id, skipped=False, reported_at=_at(20, 0),
                           game_result="win", self_rating=4)
    )
    await db_session.flush()

    await _tick(db_session, _at(21, 40))

    assert len(sent) == 1 and sent[0]["title"].startswith("Игра сыграна")
