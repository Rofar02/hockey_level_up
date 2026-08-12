"""xp_consumer's level_up publication -- same real-DB-with-real-commits
setup as test_block_completed_idempotency.py (xp_consumer opens its own
AsyncSessionLocal(), so seeded data has to be visible on that separate
connection, not just the test's own uncommitted one).
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.db.session import engine as app_engine
from app.events.handlers.block_completed import LEVEL_UP_EVENT, xp_to_next_level, xp_consumer
from app.models.exercise import TargetStat
from app.models.outbox import OutboxEvent
from app.models.processed_event import ProcessedEvent
from app.models.user import User


def _payload(user_id: uuid.UUID, *, difficulty_level: int) -> dict:
    return {
        "user_id": str(user_id),
        "exercise_id": str(uuid.uuid4()),
        "target_stat": TargetStat.STRENGTH.value,
        "difficulty_level": difficulty_level,
    }


@pytest_asyncio.fixture(autouse=True)
async def _fresh_engine_pool_per_test():
    # See test_block_completed_idempotency.py for why this is needed: each
    # pytest-asyncio test gets its own event loop, and asyncpg connections
    # are bound to the loop they were created on.
    yield
    await app_engine.dispose()


async def _cleanup(*, event_ids: tuple[uuid.UUID, ...], user_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(ProcessedEvent).where(ProcessedEvent.event_id.in_(event_ids)))
        await session.execute(
            delete(OutboxEvent).where(
                OutboxEvent.event_type == LEVEL_UP_EVENT,
                OutboxEvent.payload["user_id"].astext == str(user_id),
            )
        )
        await session.commit()


@pytest.fixture
async def real_user():
    unique = uuid.uuid4().hex[:8]
    user = User(
        id=uuid.uuid4(),
        username=f"levelup_{unique}",
        email=f"levelup_{unique}@example.com",
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


async def _level_up_events_for(user_id: uuid.UUID) -> list[OutboxEvent]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(OutboxEvent).where(
                OutboxEvent.event_type == LEVEL_UP_EVENT,
                OutboxEvent.payload["user_id"].astext == str(user_id),
            )
        )
        return list(result.scalars().all())


@pytest.mark.asyncio
async def test_level_up_publishes_event_with_old_and_new_level(real_user) -> None:
    event_id = uuid.uuid4()
    # xp_to_next_level(1) == 100 -- a single difficulty_level=10 event
    # (gain = 10*10 = 100) crosses the threshold in one call.
    threshold = xp_to_next_level(1)
    assert threshold == 100
    payload = _payload(real_user.id, difficulty_level=10)
    try:
        await xp_consumer(payload, event_id)

        events = await _level_up_events_for(real_user.id)
        assert len(events) == 1
        assert events[0].payload == {"user_id": str(real_user.id), "old_level": 1, "new_level": 2}
    finally:
        await _cleanup(event_ids=(event_id,), user_id=real_user.id)


@pytest.mark.asyncio
async def test_no_level_up_event_when_threshold_not_reached(real_user) -> None:
    event_id = uuid.uuid4()
    payload = _payload(real_user.id, difficulty_level=1)  # gain = 10, well under 100
    try:
        await xp_consumer(payload, event_id)

        assert await _level_up_events_for(real_user.id) == []
    finally:
        await _cleanup(event_ids=(event_id,), user_id=real_user.id)


@pytest.mark.asyncio
async def test_redelivered_event_does_not_publish_level_up_twice(real_user) -> None:
    event_id = uuid.uuid4()
    payload = _payload(real_user.id, difficulty_level=10)
    try:
        await xp_consumer(payload, event_id)
        await xp_consumer(payload, event_id)  # simulated redelivery, same event_id

        events = await _level_up_events_for(real_user.id)
        assert len(events) == 1
    finally:
        await _cleanup(event_ids=(event_id,), user_id=real_user.id)
