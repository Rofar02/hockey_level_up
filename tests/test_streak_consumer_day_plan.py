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
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.db.session import engine as app_engine
from app.events.handlers.block_completed import streak_consumer
from app.models.exercise import EquipmentType, Exercise, ExerciseCategory, TargetStat, TrainingPhase
from app.models.processed_event import ProcessedEvent
from app.models.progress import TrainingStreak
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.user import User

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
TWO_DAYS_AGO = TODAY - timedelta(days=2)


def _payload(user_id: uuid.UUID, *, session_block_id: uuid.UUID) -> dict:
    return {
        "user_id": str(user_id),
        "session_block_id": str(session_block_id),
        "exercise_id": str(uuid.uuid4()),
        "target_stat": TargetStat.STRENGTH.value,
        "difficulty_level": 1,
    }


async def _seed_fully_completed_session(
    user_id: uuid.UUID, *, day_date: date = TODAY
) -> uuid.UUID:
    """A TrainingSession scheduled for day_date with a single block, already
    completed -- streak_consumer's 2026-08-19 fix requires the *whole*
    session done (see is_session_fully_completed) before it'll credit that
    day at all, not just that the event's own exercise_id exists. Returns
    the completed block's id, for _payload's session_block_id."""
    async with AsyncSessionLocal() as session:
        weekly_plan = WeeklyPlan(id=uuid.uuid4(), user_id=user_id, week_start_date=day_date)
        session.add(weekly_plan)
        await session.flush()
        day_plan = DayPlan(
            id=uuid.uuid4(),
            weekly_plan_id=weekly_plan.id,
            date=day_date,
            session_type=DaySessionType.OFF_ICE,
        )
        session.add(day_plan)
        exercise = Exercise(
            id=uuid.uuid4(),
            name=f"Exercise {uuid.uuid4().hex[:8]}",
            category=ExerciseCategory.OFF_ICE,
            phase=TrainingPhase.MAIN,
            difficulty_level=1,
            equipment_type=EquipmentType.BODYWEIGHT,
        )
        session.add(exercise)
        await session.flush()
        block = SessionBlock(
            id=uuid.uuid4(),
            phase=TrainingPhase.MAIN,
            exercise_id=exercise.id,
            order=0,
            completed_at=datetime.now(timezone.utc),
        )
        training_session = TrainingSession(id=uuid.uuid4(), day_plan_id=day_plan.id, blocks=[block])
        session.add(training_session)
        await session.commit()
        return block.id


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
    block_id = await _seed_fully_completed_session(real_user.id)
    try:
        await streak_consumer(_payload(real_user.id, session_block_id=block_id), event_id)
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
    block_id = await _seed_fully_completed_session(real_user.id)
    try:
        await streak_consumer(_payload(real_user.id, session_block_id=block_id), event_id)
        assert await _current_streak(real_user.id) == 4
    finally:
        await _cleanup_processed_events(event_id)


@pytest.mark.asyncio
async def test_planned_game_day_between_activities_does_not_break_streak(real_user) -> None:
    event_id = uuid.uuid4()
    await _seed_streak(
        real_user.id, current_streak=3, longest_streak=3, last_activity_date=TWO_DAYS_AGO
    )
    await _seed_day_plan(real_user.id, day_date=YESTERDAY, session_type=DaySessionType.GAME)
    block_id = await _seed_fully_completed_session(real_user.id)
    try:
        await streak_consumer(_payload(real_user.id, session_block_id=block_id), event_id)
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
    block_id = await _seed_fully_completed_session(real_user.id)
    try:
        await streak_consumer(_payload(real_user.id, session_block_id=block_id), event_id)
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
    block_id = await _seed_fully_completed_session(real_user.id)
    try:
        await streak_consumer(_payload(real_user.id, session_block_id=block_id), event_id)
        assert await _current_streak(real_user.id) == 3
    finally:
        await _cleanup_processed_events(event_id)


@pytest.mark.asyncio
async def test_first_ever_activity_starts_streak_at_one(real_user) -> None:
    event_id = uuid.uuid4()
    # No TrainingStreak row seeded at all -- streak_consumer creates one.
    block_id = await _seed_fully_completed_session(real_user.id)
    try:
        await streak_consumer(_payload(real_user.id, session_block_id=block_id), event_id)
        assert await _current_streak(real_user.id) == 1
    finally:
        await _cleanup_processed_events(event_id)


@pytest.mark.asyncio
async def test_completing_only_some_blocks_does_not_credit_the_day(real_user) -> None:
    """2026-08-19 fix, the write-side of it: firing streak_consumer for a
    block that completed but left siblings in the same session incomplete
    (e.g. warmup done, MAIN/cooldown still pending) must not touch the
    streak at all yet -- found live on a real account where 3/12 blocks
    (warmup only) had already been credited a full day."""
    event_id = uuid.uuid4()
    await _seed_streak(
        real_user.id, current_streak=3, longest_streak=3, last_activity_date=YESTERDAY
    )

    async with AsyncSessionLocal() as session:
        weekly_plan = WeeklyPlan(id=uuid.uuid4(), user_id=real_user.id, week_start_date=TODAY)
        session.add(weekly_plan)
        await session.flush()
        day_plan = DayPlan(
            id=uuid.uuid4(),
            weekly_plan_id=weekly_plan.id,
            date=TODAY,
            session_type=DaySessionType.OFF_ICE,
        )
        session.add(day_plan)
        exercise = Exercise(
            id=uuid.uuid4(),
            name=f"Exercise {uuid.uuid4().hex[:8]}",
            category=ExerciseCategory.OFF_ICE,
            phase=TrainingPhase.WARMUP,
            difficulty_level=1,
            equipment_type=EquipmentType.BODYWEIGHT,
        )
        session.add(exercise)
        await session.flush()
        completed_block = SessionBlock(
            id=uuid.uuid4(),
            phase=TrainingPhase.WARMUP,
            exercise_id=exercise.id,
            order=0,
            completed_at=datetime.now(timezone.utc),
        )
        incomplete_block = SessionBlock(
            id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=1
        )  # completed_at left None -- rest of the session still pending
        training_session = TrainingSession(
            id=uuid.uuid4(), day_plan_id=day_plan.id, blocks=[completed_block, incomplete_block]
        )
        session.add(training_session)
        await session.commit()
        completed_block_id = completed_block.id

    try:
        await streak_consumer(_payload(real_user.id, session_block_id=completed_block_id), event_id)
        # Unchanged -- the session isn't fully done, so today isn't credited.
        assert await _current_streak(real_user.id) == 3
    finally:
        await _cleanup_processed_events(event_id)
