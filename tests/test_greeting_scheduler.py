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
async def test_birthday_greeting_once_from_ten_local(db_session, monkeypatch) -> None:
    sent = _capture(monkeypatch)
    user = await _user(db_session, birth_date=date(2000, 3, 10), timezone="Asia/Vladivostok")  # UTC+10

    await _tick(db_session, _at(23, 0, date(2026, 3, 9)))  # 09:00 local on the 10th
    assert sent == []
    await _tick(db_session, _at(0, 5))  # 10:05 local
    await _tick(db_session, _at(1, 0))
    assert [p["title"] for p in sent] == ["С днём рождения, Лёша! 🎂"]
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
