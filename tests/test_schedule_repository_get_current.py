"""ScheduleRepository.get_current loads only the current week.

It used to eager-load every past week of the player (days, sessions,
blocks, exercises) and keep the first -- the home screen got 10x slower
over a year of history (163 ms vs 16 ms, found 2026-09-28).
"""
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import event

from app.models.schedule import DayPlan, DaySessionType, WeeklyPlan
from app.models.user import User
from app.repositories.schedule_repository import ScheduleRepository
from tests.dates import utc_today


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"current_{unique}",
        email=f"current_{unique}@example.com",
        password_hash="irrelevant",
    )


def _week(user: User, monday) -> WeeklyPlan:
    return WeeklyPlan(
        id=uuid.uuid4(),
        user_id=user.id,
        week_start_date=monday,
        day_plans=[
            DayPlan(id=uuid.uuid4(), date=monday + timedelta(days=i), session_type=DaySessionType.REST)
            for i in range(7)
        ],
    )


async def _add_weeks(db_session, user: User, count: int):
    """`count` consecutive weeks ending with the current one."""
    today = utc_today()
    this_monday = today - timedelta(days=today.weekday())
    weeks = [_week(user, this_monday - timedelta(weeks=offset)) for offset in range(count)]
    db_session.add(user)
    await db_session.flush()  # no ORM relationship orders user before its weeks
    db_session.add_all(weeks)
    await db_session.flush()
    db_session.expunge_all()  # start from an empty identity map
    return today, this_monday


@pytest.mark.asyncio
async def test_get_current_returns_this_week_and_loads_only_it(db_session) -> None:
    user = _make_user()
    today, this_monday = await _add_weeks(db_session, user, count=4)

    # Counted as they're loaded -- the identity map is weak-referencing, so
    # unused past weeks would already be garbage-collected by the time the
    # assertions below could look for them there.
    loaded: list = []

    def _on_load(session, instance) -> None:
        loaded.append(instance)

    event.listen(db_session.sync_session, "loaded_as_persistent", _on_load)
    try:
        current = await ScheduleRepository(db_session).get_current(user.id, today)
    finally:
        event.remove(db_session.sync_session, "loaded_as_persistent", _on_load)

    assert current is not None
    assert current.week_start_date == this_monday
    assert len(current.day_plans) == 7
    assert [obj.id for obj in loaded if isinstance(obj, WeeklyPlan)] == [current.id]
    assert sum(isinstance(obj, DayPlan) for obj in loaded) == 7


@pytest.mark.asyncio
async def test_get_current_is_none_once_the_newest_week_is_over(db_session) -> None:
    user = _make_user()
    _, this_monday = await _add_weeks(db_session, user, count=3)

    # A week later nothing covers "today" -- the newest plan is last week's.
    assert await ScheduleRepository(db_session).get_current(user.id, this_monday + timedelta(days=7)) is None
