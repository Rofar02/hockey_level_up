"""Ice and game days over without a report (2026-10-10)."""
import uuid
from datetime import datetime, time, timedelta, timezone

import pytest

from app.models.schedule import DayPlan, DaySessionType, TrainingSession, WeeklyPlan
from app.models.training_diary import TrainingDiaryEntry
from app.models.user import User
from app.services.pending_report_service import pending_reports
from tests.dates import utc_today


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(id=uuid.uuid4(), username=f"pr_{unique}", email=f"pr_{unique}@example.com", password_hash="x", timezone="UTC")


@pytest.mark.asyncio
async def test_lists_over_unreported_ice_and_games_only(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    today = utc_today()
    days = {}
    for index, (name, offset, kind) in enumerate([
        ("yesterday_ice", -1, DaySessionType.ON_ICE),
        ("reported_game", -2, DaySessionType.GAME),
        ("gym", -1, DaySessionType.OFF_ICE),
        ("tomorrow_ice", 1, DaySessionType.ON_ICE),
        ("old_ice", -5, DaySessionType.ON_ICE),
    ]):
        session = TrainingSession(id=uuid.uuid4(), blocks=[])
        day = DayPlan(id=uuid.uuid4(), date=today + timedelta(days=offset), session_type=kind, training_session=session)
        # A week of its own per day -- week_start_date is unique per player.
        week_start = today - timedelta(days=70 + 7 * index)
        db_session.add(WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=week_start, day_plans=[day]))
        days[name] = day
    await db_session.flush()
    db_session.add(
        TrainingDiaryEntry(
            user_id=user.id, training_session_id=days["reported_game"].training_session.id,
            reported_at=datetime.now(timezone.utc),
        )
    )
    await db_session.flush()

    pending = await pending_reports(db_session, user)

    assert [p.day_plan_id for p in pending] == [days["yesterday_ice"].id]


@pytest.mark.asyncio
async def test_todays_ice_counts_only_once_it_is_over(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    today = utc_today()
    session = TrainingSession(id=uuid.uuid4(), blocks=[])
    day = DayPlan(id=uuid.uuid4(), date=today, session_type=DaySessionType.ON_ICE, training_session=session)
    db_session.add(WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=today, day_plans=[day]))
    await db_session.flush()

    # An own ice day is assumed over at 19:00 local (asked about at 21:00).
    before = datetime.combine(today, time(18, 0), tzinfo=timezone.utc)
    after = datetime.combine(today, time(19, 30), tzinfo=timezone.utc)
    assert await pending_reports(db_session, user, before) == []
    assert [p.day_plan_id for p in await pending_reports(db_session, user, after)] == [day.id]
