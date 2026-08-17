"""Proves a party-materialized training block credits the same personal
TrainingStreak a normal training session would. SessionBlockService's
BLOCK_COMPLETED_EVENT payload doesn't know or care whether the SessionBlock
it's describing came from TrainingPartyService.confirm_exercises or from
personal-plan assembly -- but that's exactly the kind of "surely it just
works because it flows through the same tables" claim the task calls out
explicitly, so this checks it end to end: create a party, confirm a shared
exercise set, complete one member's materialized block through the real
SessionBlockService, and feed the exact block_completed payload it wrote
into streak_consumer (same real-DB-with-real-commits setup as
test_streak_consumer_day_plan.py, since streak_consumer opens its own
AsyncSessionLocal and needs to see committed data).
"""
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.db.session import engine as app_engine
from app.events.handlers.block_completed import streak_consumer
from app.models.exercise import EquipmentType, Exercise, ExerciseCategory, TrainingPhase
from app.models.outbox import OutboxEvent
from app.models.processed_event import ProcessedEvent
from app.models.progress import TrainingStreak
from app.models.user import User
from app.repositories.schedule_repository import ScheduleRepository
from app.schemas.training_party import TrainingPartyCreate
from app.services.friend_service import FriendService
from app.services.session_block_service import BLOCK_COMPLETED_EVENT, SessionBlockService
from app.services.training_party_service import TrainingPartyService

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)


@pytest.fixture(autouse=True)
async def _fresh_engine_pool_per_test():
    # See test_block_completed_idempotency.py / test_streak_consumer_day_plan.py
    # -- avoids asyncpg connections bound to a previous test's event loop.
    yield
    await app_engine.dispose()


@pytest.fixture
async def real_party_users():
    unique = uuid.uuid4().hex[:8]
    alice = User(
        id=uuid.uuid4(),
        username=f"streakp_a_{unique}",
        email=f"streakp_a_{unique}@example.com",
        password_hash="irrelevant",
        equipment_access=EquipmentType.BODYWEIGHT,
        friend_code=f"A{unique.upper()}",
    )
    bob = User(
        id=uuid.uuid4(),
        username=f"streakp_b_{unique}",
        email=f"streakp_b_{unique}@example.com",
        password_hash="irrelevant",
        equipment_access=EquipmentType.BODYWEIGHT,
        friend_code=f"B{unique.upper()}",
    )
    async with AsyncSessionLocal() as session:
        session.add_all([alice, bob])
        await session.commit()
    try:
        yield alice, bob
    finally:
        async with AsyncSessionLocal() as session:
            # Cascades to WeeklyPlan/DayPlan/TrainingSession/SessionBlock/
            # TrainingStreak/TrainingParty/TrainingPartyMember/Friendship.
            await session.execute(delete(User).where(User.id.in_([alice.id, bob.id])))
            await session.commit()


async def _cleanup(event_id: uuid.UUID, exercise_id: uuid.UUID, user_ids: list[uuid.UUID]) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(ProcessedEvent).where(ProcessedEvent.event_id == event_id))
        # Users first -- cascades away the SessionBlock rows referencing
        # exercise_id (WeeklyPlan -> DayPlan -> TrainingSession ->
        # SessionBlock), otherwise deleting the exercise 409s on the FK.
        # The real_party_users fixture's own teardown deletes these same
        # users again afterward, which is then just a harmless no-op.
        await session.execute(delete(User).where(User.id.in_(user_ids)))
        await session.execute(delete(Exercise).where(Exercise.id == exercise_id))
        await session.commit()


@pytest.mark.asyncio
async def test_completing_a_party_training_block_advances_personal_streak(real_party_users) -> None:
    alice, bob = real_party_users
    exercise = Exercise(
        id=uuid.uuid4(),
        name=f"Party exercise {uuid.uuid4().hex[:8]}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=2,
        equipment_type=EquipmentType.BODYWEIGHT,
    )
    async with AsyncSessionLocal() as session:
        session.add(exercise)
        # Bob already has a 3-day streak as of yesterday -- completing his
        # *party* training today should extend it to 4, exactly like a
        # normal personal training day would.
        session.add(
            TrainingStreak(
                id=uuid.uuid4(),
                user_id=bob.id,
                current_streak=3,
                longest_streak=3,
                last_activity_date=YESTERDAY,
            )
        )
        await session.commit()

    async with AsyncSessionLocal() as session:
        friends = FriendService(session)
        sent = await friends.send_request_by_code(alice, bob.friend_code)
        await friends.respond_to_request(bob, sent.id, accept=True)

        parties = TrainingPartyService(session)
        party = await parties.create_party(
            alice, TrainingPartyCreate(target_date=TODAY, friend_ids=[bob.id])
        )
        await parties.respond_to_invite(bob, party.id, accept=True)
        await parties.confirm_exercises(alice, party.id, [exercise.id])

        bob_day_plan = await ScheduleRepository(session).get_day_plan_for_date(bob.id, TODAY)
        assert bob_day_plan is not None and bob_day_plan.training_session is not None
        # blocks[0] would be a warmup now that replace_day_plan_content also
        # picks one (see backlog item #2) -- the confirmed MAIN exercise is
        # what this test actually means to complete.
        bob_block = next(
            b for b in bob_day_plan.training_session.blocks if b.phase == TrainingPhase.MAIN
        )

        await SessionBlockService(session).complete_block(bob_block.id, bob)

        outbox_row = (
            await session.execute(
                select(OutboxEvent).where(
                    OutboxEvent.event_type == BLOCK_COMPLETED_EVENT,
                    OutboxEvent.payload["session_block_id"].astext == str(bob_block.id),
                )
            )
        ).scalar_one()
        event_id = outbox_row.id
        payload = outbox_row.payload

    try:
        # This is the actual assertion: feeding the real block_completed
        # payload from a party-materialized block through the real streak
        # consumer moves TrainingStreak, not just "the API call succeeded".
        await streak_consumer(payload, event_id)

        async with AsyncSessionLocal() as session:
            streak = (
                await session.execute(
                    select(TrainingStreak).where(TrainingStreak.user_id == bob.id)
                )
            ).scalar_one()
            assert streak.current_streak == 4
            assert streak.longest_streak == 4
            assert streak.last_activity_date == TODAY
    finally:
        await _cleanup(event_id, exercise.id, [alice.id, bob.id])
