"""(event_id, handler_name) idempotency for block_completed's subscribers.

stat_consumer/streak_consumer/xp_consumer each open their own
AsyncSessionLocal() (see app/db/session.py) rather than accepting an
injected session -- that's what lets them run standalone off a RabbitMQ
message. Because of that, unlike the rest of this suite these tests talk to
the real database with real commits instead of the rollback-at-teardown
db_session fixture: a handler's own connection would never see data set up
on the test's separate, uncommitted connection. Each test cleans up the
rows it creates (User delete cascades to UserStat/StatHistory/
TrainingStreak; processed_events has no FK to clean up explicitly).

Coverage: the same event_id redelivered applies its side-effect once, not
twice (the bug this table exists to close -- at-least-once RabbitMQ
delivery or an outbox-relay commit race could otherwise double-apply);
two genuinely different events both apply in full; and two different
handlers claiming the same event_id don't block each other.
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.db.session import engine as app_engine
from app.events.handlers.block_completed import (
    STAT_CONSUMER_HANDLER_NAME,
    XP_CONSUMER_HANDLER_NAME,
    stat_consumer,
    streak_consumer,
    xp_consumer,
)
from app.models.exercise import TargetStat
from app.models.processed_event import ProcessedEvent
from app.models.progress import StatHistory, TrainingStreak, UserStat
from app.models.user import User


def _payload(
    user_id: uuid.UUID, *, difficulty_level: int, stats: list[TargetStat] | None = None
) -> dict:
    return {
        "user_id": str(user_id),
        "exercise_id": str(uuid.uuid4()),
        "target_stats": [s.value for s in (stats or [TargetStat.STRENGTH])],
        "difficulty_level": difficulty_level,
    }


@pytest_asyncio.fixture(autouse=True)
async def _fresh_engine_pool_per_test():
    # app.db.session.engine is a process-wide singleton (correct for the
    # real app/consumer, which lives on one long-running event loop) but
    # pytest-asyncio gives each test function its own fresh event loop by
    # default, and asyncpg connections are bound to the loop they were
    # created on. Without disposing here, a connection pooled during one
    # test gets handed to the next test's (different) loop and asyncpg
    # raises "another operation is in progress". Disposing after each test
    # forces the next one to lazily open a connection on its own loop.
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
        username=f"idem_{unique}",
        email=f"idem_{unique}@example.com",
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


async def _stat_value(
    user_id: uuid.UUID, stat: TargetStat = TargetStat.STRENGTH
) -> float | None:
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                select(UserStat.current_value).where(
                    UserStat.user_id == user_id, UserStat.stat_type == stat
                )
            )
        ).scalar_one_or_none()


async def _stat_history_count(user_id: uuid.UUID) -> int:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(select(StatHistory).where(StatHistory.user_id == user_id))
        ).scalars().all()
        return len(rows)


async def _xp_level(user_id: uuid.UUID) -> tuple[int, int]:
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(select(User.xp, User.level).where(User.id == user_id))
        ).one()
        return row.xp, row.level


@pytest.mark.asyncio
async def test_stat_consumer_redelivery_applies_gain_only_once(real_user) -> None:
    event_id = uuid.uuid4()
    payload = _payload(real_user.id, difficulty_level=4)
    try:
        await stat_consumer(payload, event_id)
        value_after_first = await _stat_value(real_user.id)
        assert value_after_first is not None and value_after_first > 0

        await stat_consumer(payload, event_id)  # simulated redelivery, same event_id
        value_after_second = await _stat_value(real_user.id)

        assert value_after_second == value_after_first
        assert await _stat_history_count(real_user.id) == 1
    finally:
        await _cleanup_processed_events(event_id)


@pytest.mark.asyncio
async def test_stat_consumer_two_different_events_both_apply(real_user) -> None:
    event_id_1, event_id_2 = uuid.uuid4(), uuid.uuid4()
    payload = _payload(real_user.id, difficulty_level=2)
    try:
        await stat_consumer(payload, event_id_1)
        value_after_first = await _stat_value(real_user.id)

        await stat_consumer(payload, event_id_2)  # different event_id -- genuinely new event
        value_after_second = await _stat_value(real_user.id)

        assert value_after_second > value_after_first
        assert await _stat_history_count(real_user.id) == 2
    finally:
        await _cleanup_processed_events(event_id_1, event_id_2)


@pytest.mark.asyncio
async def test_stat_consumer_splits_base_gain_evenly_across_multiple_stats(real_user) -> None:
    """A fresh user (no diminishing returns yet) and an untagged exercise (no
    SkillTag relevance boost) isolates the split itself: the pre-modifier
    base (difficulty_level * 0.5) is divided by len(stats) before each
    stat's own diminishing_factor/relevance_multiplier apply -- with both at
    their neutral 1.0 here, a 2-stat exercise should award each stat exactly
    half of what a 1-stat exercise at the same difficulty would award its
    single stat, and the two halves should sum back to that single-stat
    total (see stat_consumer's base_gain computation)."""
    single_event_id = uuid.uuid4()
    multi_event_id = uuid.uuid4()
    try:
        single_payload = _payload(real_user.id, difficulty_level=4, stats=[TargetStat.STRENGTH])
        await stat_consumer(single_payload, single_event_id)
        single_stat_gain = await _stat_value(real_user.id, TargetStat.STRENGTH)
        assert single_stat_gain == 2.0  # difficulty_level(4) * 0.5 / 1 stat

        multi_payload = _payload(
            real_user.id, difficulty_level=4, stats=[TargetStat.AGILITY, TargetStat.ENDURANCE]
        )
        await stat_consumer(multi_payload, multi_event_id)
        agility_gain = await _stat_value(real_user.id, TargetStat.AGILITY)
        endurance_gain = await _stat_value(real_user.id, TargetStat.ENDURANCE)

        assert agility_gain == 1.0  # difficulty_level(4) * 0.5 / 2 stats
        assert endurance_gain == 1.0
        assert agility_gain + endurance_gain == single_stat_gain
    finally:
        await _cleanup_processed_events(single_event_id, multi_event_id)


@pytest.mark.asyncio
async def test_xp_consumer_redelivery_applies_gain_only_once(real_user) -> None:
    event_id = uuid.uuid4()
    payload = _payload(real_user.id, difficulty_level=3)
    try:
        await xp_consumer(payload, event_id)
        xp_after_first, _ = await _xp_level(real_user.id)
        assert xp_after_first == 30  # difficulty_level(3) * 10

        await xp_consumer(payload, event_id)  # redelivery
        xp_after_second, _ = await _xp_level(real_user.id)

        assert xp_after_second == xp_after_first
    finally:
        await _cleanup_processed_events(event_id)


@pytest.mark.asyncio
async def test_stat_and_xp_handlers_claim_independently_for_the_same_event(real_user) -> None:
    event_id = uuid.uuid4()
    payload = _payload(real_user.id, difficulty_level=2)
    try:
        await stat_consumer(payload, event_id)
        await xp_consumer(payload, event_id)

        stat_value = await _stat_value(real_user.id)
        xp_value, _ = await _xp_level(real_user.id)
        assert stat_value is not None and stat_value > 0
        assert xp_value == 20  # difficulty_level(2) * 10

        async with AsyncSessionLocal() as session:
            claims = (
                await session.execute(
                    select(ProcessedEvent.handler_name).where(ProcessedEvent.event_id == event_id)
                )
            ).scalars().all()
        # Both handlers claimed the same event_id independently -- neither
        # was blocked by, nor blocks, the other's claim row.
        assert set(claims) == {STAT_CONSUMER_HANDLER_NAME, XP_CONSUMER_HANDLER_NAME}
    finally:
        await _cleanup_processed_events(event_id)


@pytest.mark.asyncio
async def test_streak_consumer_redelivery_claims_once(real_user) -> None:
    event_id = uuid.uuid4()
    payload = _payload(real_user.id, difficulty_level=1)
    try:
        await streak_consumer(payload, event_id)
        await streak_consumer(payload, event_id)  # redelivery

        async with AsyncSessionLocal() as session:
            streak = (
                await session.execute(
                    select(TrainingStreak).where(TrainingStreak.user_id == real_user.id)
                )
            ).scalar_one()
            claim_count = len(
                (
                    await session.execute(
                        select(ProcessedEvent).where(ProcessedEvent.event_id == event_id)
                    )
                )
                .scalars()
                .all()
            )

        assert streak.current_streak == 1
        # Exactly one claim row -- the second call's try_claim found the
        # first one and short-circuited before touching the streak at all.
        assert claim_count == 1
    finally:
        await _cleanup_processed_events(event_id)
