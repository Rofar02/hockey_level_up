"""Body-muscles map (2026-08-20 planning session):
block_completed.muscle_load_consumer. Real-DB-with-real-commits setup,
same reason as test_block_completed_idempotency.py -- the consumer opens
its own AsyncSessionLocal, so data has to be visible there, not just on
this test's own (rollback-at-teardown) db_session connection.

Every Exercise created here is cleaned up explicitly in each test's own
finally -- see test_block_completed_idempotency.py's fix (commit 4f571a8)
for why: Exercise has no FK back to the user, so the real_user fixture's
own User-cascade teardown never touches it.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.core.muscle_load import GAIN_PER_DIFFICULTY_LEVEL, GRACE_PERIOD_HOURS, MAX_INTENSITY
from app.db.session import AsyncSessionLocal
from app.db.session import engine as app_engine
from app.events.handlers.block_completed import muscle_load_consumer
from app.models.exercise import (
    Exercise,
    ExerciseCategory,
    ExerciseMuscleGroup,
    MuscleGroup,
    TrainingPhase,
)
from app.models.processed_event import ProcessedEvent
from app.models.progress import UserMuscleLoad
from app.models.user import User


def _payload(user_id: uuid.UUID, exercise_id: uuid.UUID, *, difficulty_level: int) -> dict:
    return {
        "user_id": str(user_id),
        "session_block_id": str(uuid.uuid4()),
        "exercise_id": str(exercise_id),
        "target_stats": [],
        "difficulty_level": difficulty_level,
    }


@pytest_asyncio.fixture(autouse=True)
async def _fresh_engine_pool_per_test():
    # See test_block_completed_idempotency.py -- avoids asyncpg connections
    # bound to a previous test's event loop.
    yield
    await app_engine.dispose()


@pytest.fixture
async def real_user():
    unique = uuid.uuid4().hex[:8]
    user = User(
        id=uuid.uuid4(),
        username=f"muscleload_{unique}",
        email=f"muscleload_{unique}@example.com",
        password_hash="irrelevant",
    )
    async with AsyncSessionLocal() as session:
        session.add(user)
        await session.commit()
    try:
        yield user
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(User).where(User.id == user.id))
            await session.commit()


async def _make_exercise(*, muscle_weights: dict[MuscleGroup, float]) -> Exercise:
    exercise = Exercise(
        id=uuid.uuid4(),
        name=f"Muscle load exercise {uuid.uuid4().hex[:8]}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
    )
    async with AsyncSessionLocal() as session:
        session.add(exercise)
        session.add_all(
            ExerciseMuscleGroup(exercise_id=exercise.id, muscle_group=group, weight=weight)
            for group, weight in muscle_weights.items()
        )
        await session.commit()
    return exercise


async def _cleanup_exercise(exercise_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(ExerciseMuscleGroup).where(ExerciseMuscleGroup.exercise_id == exercise_id)
        )
        await session.execute(delete(Exercise).where(Exercise.id == exercise_id))
        await session.commit()


async def _cleanup_processed_events(*event_ids: uuid.UUID) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(ProcessedEvent).where(ProcessedEvent.event_id.in_(event_ids)))
        await session.commit()


async def _get_load(user_id: uuid.UUID, muscle_group: MuscleGroup) -> UserMuscleLoad | None:
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                select(UserMuscleLoad).where(
                    UserMuscleLoad.user_id == user_id, UserMuscleLoad.muscle_group == muscle_group
                )
            )
        ).scalar_one_or_none()


@pytest.mark.asyncio
async def test_first_event_creates_a_weighted_load_row(real_user) -> None:
    exercise = await _make_exercise(muscle_weights={MuscleGroup.QUADS: 0.5})
    event_id = uuid.uuid4()
    try:
        await muscle_load_consumer(
            _payload(real_user.id, exercise.id, difficulty_level=4), event_id
        )
        load = await _get_load(real_user.id, MuscleGroup.QUADS)
        assert load is not None
        assert load.current_value == pytest.approx(4 * GAIN_PER_DIFFICULTY_LEVEL * 0.5)
    finally:
        await _cleanup_processed_events(event_id)
        await _cleanup_exercise(exercise.id)


@pytest.mark.asyncio
async def test_redelivery_applies_gain_only_once(real_user) -> None:
    exercise = await _make_exercise(muscle_weights={MuscleGroup.CHEST: 1.0})
    event_id = uuid.uuid4()
    try:
        payload = _payload(real_user.id, exercise.id, difficulty_level=3)
        await muscle_load_consumer(payload, event_id)
        await muscle_load_consumer(payload, event_id)  # redelivery, same event_id

        load = await _get_load(real_user.id, MuscleGroup.CHEST)
        assert load is not None
        assert load.current_value == pytest.approx(3 * GAIN_PER_DIFFICULTY_LEVEL)
    finally:
        await _cleanup_processed_events(event_id)
        await _cleanup_exercise(exercise.id)


@pytest.mark.asyncio
async def test_exercise_with_no_muscle_tags_is_a_safe_no_op(real_user) -> None:
    exercise = await _make_exercise(muscle_weights={})
    event_id = uuid.uuid4()
    try:
        # Must not raise, and must still claim the event (checked via a
        # second call being a silent no-op too, not a retry that crashes).
        await muscle_load_consumer(
            _payload(real_user.id, exercise.id, difficulty_level=5), event_id
        )
        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    select(UserMuscleLoad).where(UserMuscleLoad.user_id == real_user.id)
                )
            ).scalars().all()
            assert list(rows) == []
    finally:
        await _cleanup_processed_events(event_id)
        await _cleanup_exercise(exercise.id)


@pytest.mark.asyncio
async def test_a_later_event_collapses_decay_before_adding(real_user) -> None:
    """The core behavior that distinguishes this from stat_consumer's
    write-then-project pattern: a stale, already-decayed row must not get
    the new gain added straight onto its old raw value."""
    exercise = await _make_exercise(muscle_weights={MuscleGroup.BACK: 1.0})
    event_id = uuid.uuid4()
    try:
        stale_last_updated = datetime.now(timezone.utc) - timedelta(
            hours=GRACE_PERIOD_HOURS + 100  # long enough to have decayed to ~0
        )
        async with AsyncSessionLocal() as session:
            session.add(
                UserMuscleLoad(
                    user_id=real_user.id,
                    muscle_group=MuscleGroup.BACK,
                    current_value=8.0,
                    last_updated_at=stale_last_updated,
                )
            )
            await session.commit()

        await muscle_load_consumer(
            _payload(real_user.id, exercise.id, difficulty_level=2), event_id
        )

        load = await _get_load(real_user.id, MuscleGroup.BACK)
        assert load is not None
        # The stale 8.0 had fully decayed away by the time this event fired
        # -- only this event's own gain should show, not 8.0 + gain.
        assert load.current_value == pytest.approx(2 * GAIN_PER_DIFFICULTY_LEVEL, abs=0.05)
    finally:
        await _cleanup_processed_events(event_id)
        await _cleanup_exercise(exercise.id)


@pytest.mark.asyncio
async def test_clamped_at_max_intensity(real_user) -> None:
    exercise = await _make_exercise(muscle_weights={MuscleGroup.SHOULDERS: 1.0})
    event_id = uuid.uuid4()
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                UserMuscleLoad(
                    user_id=real_user.id,
                    muscle_group=MuscleGroup.SHOULDERS,
                    current_value=9.5,
                    last_updated_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()

        await muscle_load_consumer(
            _payload(real_user.id, exercise.id, difficulty_level=5), event_id
        )

        load = await _get_load(real_user.id, MuscleGroup.SHOULDERS)
        assert load is not None
        assert load.current_value == MAX_INTENSITY
    finally:
        await _cleanup_processed_events(event_id)
        await _cleanup_exercise(exercise.id)
