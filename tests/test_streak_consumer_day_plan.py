"""streak_consumer's use of has_missed_training_day: a planned rest day (or
a day with no DayPlan at all) between two activities must not break the
streak, while a planned on/off-ice day with no completed SessionBlock must.

Same real-DB-with-real-commits setup as test_block_completed_idempotency.py
(streak_consumer opens its own AsyncSessionLocal, so data has to be visible
on that separate connection, not just the test's own uncommitted one).
streak_consumer always compares against date.today(), so these tests seed
last_activity_date/DayPlan.date relative to today() rather than fixed dates.
"""
import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.db.session import engine as app_engine
from app.events.handlers.block_completed import streak_consumer
from app.models.exercise import TargetStat
from app.models.processed_event import ProcessedEvent
from app.models.progress import TrainingStreak
from app.models.schedule import DayPlan, DaySessionType, WeeklyPlan
from app.models.user import User

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
TWO_DAYS_AGO = TODAY - timedelta(days=2)


def _payload(user_id: uuid.UUID) -> dict:
    return {
        "user_id": str(user_id),
        "exercise_id": str(uuid.uuid4()),
        "target_stat": TargetStat.STRENGTH.value,
        "difficulty_level": 1,
    }


@pytest_asyncio.fixture(autouse=True)
async def _fresh_engine_pool_per_test():
    # See test_block_completed_idempotency.py -- avoids asyncpg connections
    # bound to a previous test's event loop.
    yield
    await app_engine.dispose()


async def _cleanup_processed_events(*event_ids: uuid.UUID) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(ProcessedEvent).where(ProcessedEvent.event_id.in_(event_ids)))
        await session.commit()


@pytest.fixture
async def real_user():
    unique = uuid.uuid4().hex[:8]
    user = User(
        id=uuid.uuid4(),
        username=f"streakdp_{unique}",
        email=f"streakdp_{unique}@example.com",
        password_hash="irrelevant",
    )
    async with AsyncSessionLocal() as session:
        session.add(user)
        await session.commit()
    try:
        yield user
    finally:
        async with AsyncSessionLocal() as session:
            # Cascades to WeeklyPlan/DayPlan/TrainingSession/SessionBlock/TrainingStreak.
            await session.execute(delete(User).where(User.id == user.id))
            await session.commit()


async def _seed_streak(
    user_id: uuid.UUID, *, current_streak: int, longest_streak: int, last_activity_date: date
) -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            TrainingStreak(
                id=uuid.uuid4(),
                user_id=user_id,
                current_streak=current_streak,
                longest_streak=longest_streak,
                last_activity_date=last_activity_date,
            )
        )
        await session.commit()


async def _seed_day_plan(
    user_id: uuid.UUID, *, day_date: date, session_type: DaySessionType
) -> None:
    async with AsyncSessionLocal() as session:
        weekly_plan = WeeklyPlan(id=uuid.uuid4(), user_id=user_id, week_start_date=day_date)
        session.add(weekly_plan)
        await session.flush()
        session.add(
            DayPlan(
                id=uuid.uuid4(), weekly_plan_id=weekly_plan.id, date=day_date, session_type=session_type
            )
        )
        await session.commit()


async def _current_streak(user_id: uuid.UUID) -> int:
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                select(TrainingStreak.current_streak).where(TrainingStreak.user_id == user_id)
            )
        ).scalar_one()


@pytest.mark.asyncio
async def test_consecutive_training_days_increment_streak(real_user) -> None:
    event_id = uuid.uuid4()
    await _seed_streak(
        real_user.id, current_streak=1, longest_streak=1, last_activity_date=YESTERDAY
    )
    try:
        await streak_consumer(_payload(real_user.id), event_id)
        assert await _current_streak(real_user.id) == 2
    finally:
        await _cleanup_processed_events(event_id)


@pytest.mark.asyncio
async def test_planned_rest_day_between_activities_does_not_break_streak(real_user) -> None:
    event_id = uuid.uuid4()
    await _seed_streak(
        real_user.id, current_streak=3, longest_streak=3, last_activity_date=TWO_DAYS_AGO
    )
    await _seed_day_plan(real_user.id, day_date=YESTERDAY, session_type=DaySessionType.REST)
    try:
        await streak_consumer(_payload(real_user.id), event_id)
        assert await _current_streak(real_user.id) == 4
    finally:
        await _cleanup_processed_events(event_id)


@pytest.mark.asyncio
async def test_missed_planned_training_day_breaks_streak(real_user) -> None:
    event_id = uuid.uuid4()
    await _seed_streak(
        real_user.id, current_streak=5, longest_streak=5, last_activity_date=TWO_DAYS_AGO
    )
    # Planned on-ice day yesterday, never completed.
    await _seed_day_plan(real_user.id, day_date=YESTERDAY, session_type=DaySessionType.ON_ICE)
    try:
        await streak_consumer(_payload(real_user.id), event_id)
        assert await _current_streak(real_user.id) == 1
    finally:
        await _cleanup_processed_events(event_id)


@pytest.mark.asyncio
async def test_day_with_no_day_plan_at_all_does_not_break_streak(real_user) -> None:
    event_id = uuid.uuid4()
    await _seed_streak(
        real_user.id, current_streak=2, longest_streak=2, last_activity_date=TWO_DAYS_AGO
    )
    # No DayPlan seeded for YESTERDAY at all.
    try:
        await streak_consumer(_payload(real_user.id), event_id)
        assert await _current_streak(real_user.id) == 3
    finally:
        await _cleanup_processed_events(event_id)


@pytest.mark.asyncio
async def test_first_ever_activity_starts_streak_at_one(real_user) -> None:
    event_id = uuid.uuid4()
    # No TrainingStreak row seeded at all -- streak_consumer creates one.
    try:
        await streak_consumer(_payload(real_user.id), event_id)
        assert await _current_streak(real_user.id) == 1
    finally:
        await _cleanup_processed_events(event_id)
