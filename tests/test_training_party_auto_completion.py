"""SessionBlockService.complete_block's hook into
TrainingPartyService.try_complete_parties_for: a party auto-completes (and
publishes one party_completed outbox event per trainer) exactly when every
*actually training* joined member finishes -- resting/no-plan spectators
never block it, and it stays pending while anyone's still mid-session.
"""
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.exercise import EquipmentType, Exercise, ExerciseCategory, TrainingPhase
from app.models.outbox import OutboxEvent
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.user import User
from app.schemas.training_party import TrainingPartyCreate
from app.services.friend_activity_service import FriendActivityService
from app.services.friend_service import FriendService
from app.services.session_block_service import SessionBlockService
from app.services.training_party_service import PARTY_COMPLETED_EVENT, TrainingPartyService

TOMORROW = date.today() + timedelta(days=1)


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"partyc_{unique}",
        email=f"partyc_{unique}@example.com",
        password_hash="irrelevant",
        equipment_access=EquipmentType.BODYWEIGHT,
        friend_code=unique.upper(),
    )
    defaults.update(overrides)
    return User(**defaults)


async def _befriend(db_session, a: User, b: User) -> None:
    service = FriendService(db_session)
    sent = await service.send_request_by_code(a, b.friend_code)
    await service.respond_to_request(b, sent.id, accept=True)


def _make_exercise() -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=f"Exercise {uuid.uuid4().hex[:8]}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=3,
        equipment_type=EquipmentType.GYM,
    )


async def _training_day(
    db_session, user_id: uuid.UUID, exercise: Exercise, *, num_blocks: int
) -> list[SessionBlock]:
    weekly_plan = WeeklyPlan(id=uuid.uuid4(), user_id=user_id, week_start_date=TOMORROW)
    db_session.add(weekly_plan)
    await db_session.flush()
    day_plan = DayPlan(
        id=uuid.uuid4(),
        weekly_plan_id=weekly_plan.id,
        date=TOMORROW,
        session_type=DaySessionType.OFF_ICE,
    )
    db_session.add(day_plan)
    await db_session.flush()
    blocks = [
        SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=i)
        for i in range(num_blocks)
    ]
    training_session = TrainingSession(id=uuid.uuid4(), day_plan_id=day_plan.id, blocks=blocks)
    db_session.add(training_session)
    await db_session.flush()
    return blocks


async def _rest_day(db_session, user_id: uuid.UUID) -> None:
    weekly_plan = WeeklyPlan(id=uuid.uuid4(), user_id=user_id, week_start_date=TOMORROW)
    db_session.add(weekly_plan)
    await db_session.flush()
    db_session.add(
        DayPlan(
            id=uuid.uuid4(),
            weekly_plan_id=weekly_plan.id,
            date=TOMORROW,
            session_type=DaySessionType.REST,
        )
    )
    await db_session.flush()


async def _party_completed_events_for(db_session, user_id: uuid.UUID) -> list[OutboxEvent]:
    result = await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.event_type == PARTY_COMPLETED_EVENT)
    )
    return [e for e in result.scalars().all() if e.payload.get("user_id") == str(user_id)]


@pytest.mark.asyncio
async def test_party_stays_pending_while_one_member_still_training(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    exercise = _make_exercise()
    db_session.add_all([alice, bob, exercise])
    await db_session.flush()
    await _befriend(db_session, alice, bob)
    alice_blocks = await _training_day(db_session, alice.id, exercise, num_blocks=2)
    await _training_day(db_session, bob.id, exercise, num_blocks=2)

    parties = TrainingPartyService(db_session)
    party = await parties.create_party(alice, TrainingPartyCreate(target_date=TOMORROW, friend_ids=[bob.id]))
    await parties.respond_to_invite(bob, party.id, accept=True)

    blocks = SessionBlockService(db_session)
    for block in alice_blocks:
        await blocks.complete_block(block.id, alice)

    detail = await parties.get_party(alice, party.id)
    assert detail.status == "pending"
    assert await _party_completed_events_for(db_session, alice.id) == []


@pytest.mark.asyncio
async def test_party_completes_when_all_trainers_finish(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    exercise = _make_exercise()
    db_session.add_all([alice, bob, exercise])
    await db_session.flush()
    await _befriend(db_session, alice, bob)
    alice_blocks = await _training_day(db_session, alice.id, exercise, num_blocks=1)
    bob_blocks = await _training_day(db_session, bob.id, exercise, num_blocks=1)

    parties = TrainingPartyService(db_session)
    party = await parties.create_party(alice, TrainingPartyCreate(target_date=TOMORROW, friend_ids=[bob.id]))
    await parties.respond_to_invite(bob, party.id, accept=True)

    blocks = SessionBlockService(db_session)
    await blocks.complete_block(alice_blocks[0].id, alice)
    await blocks.complete_block(bob_blocks[0].id, bob)

    detail = await parties.get_party(alice, party.id)
    assert detail.status == "completed"

    alice_events = await _party_completed_events_for(db_session, alice.id)
    bob_events = await _party_completed_events_for(db_session, bob.id)
    assert len(alice_events) == 1
    assert len(bob_events) == 1
    assert alice_events[0].payload["party_id"] == str(party.id)
    assert alice_events[0].payload["party_size"] == 2
    assert bob_events[0].payload["party_size"] == 2


@pytest.mark.asyncio
async def test_resting_member_does_not_block_completion(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    carol = _make_user()
    exercise = _make_exercise()
    db_session.add_all([alice, bob, carol, exercise])
    await db_session.flush()
    await _befriend(db_session, alice, bob)
    await _befriend(db_session, alice, carol)
    alice_blocks = await _training_day(db_session, alice.id, exercise, num_blocks=1)
    bob_blocks = await _training_day(db_session, bob.id, exercise, num_blocks=1)
    await _rest_day(db_session, carol.id)  # carol is resting -- spectator only

    parties = TrainingPartyService(db_session)
    party = await parties.create_party(
        alice, TrainingPartyCreate(target_date=TOMORROW, friend_ids=[bob.id, carol.id])
    )
    await parties.respond_to_invite(bob, party.id, accept=True)
    await parties.respond_to_invite(carol, party.id, accept=True)

    blocks = SessionBlockService(db_session)
    await blocks.complete_block(alice_blocks[0].id, alice)
    await blocks.complete_block(bob_blocks[0].id, bob)

    detail = await parties.get_party(alice, party.id)
    assert detail.status == "completed"
    # Only the two actual trainers get a party_completed credit -- carol was
    # only spectating, never trained, gets none.
    assert await _party_completed_events_for(db_session, carol.id) == []
    assert len(await _party_completed_events_for(db_session, alice.id)) == 1


@pytest.mark.asyncio
async def test_completing_own_training_outside_any_party_does_not_error(db_session) -> None:
    # No party at all -- try_complete_parties_for must be a safe no-op.
    alice = _make_user()
    exercise = _make_exercise()
    db_session.add_all([alice, exercise])
    await db_session.flush()
    alice_blocks = await _training_day(db_session, alice.id, exercise, num_blocks=1)

    await SessionBlockService(db_session).complete_block(alice_blocks[0].id, alice)
    # No exception raised -- that's the whole assertion.


@pytest.mark.asyncio
async def test_party_completed_event_appears_in_friend_feed(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    exercise = _make_exercise()
    db_session.add_all([alice, bob, exercise])
    await db_session.flush()
    await _befriend(db_session, alice, bob)
    alice_blocks = await _training_day(db_session, alice.id, exercise, num_blocks=1)
    bob_blocks = await _training_day(db_session, bob.id, exercise, num_blocks=1)

    parties = TrainingPartyService(db_session)
    party = await parties.create_party(alice, TrainingPartyCreate(target_date=TOMORROW, friend_ids=[bob.id]))
    await parties.respond_to_invite(bob, party.id, accept=True)

    blocks = SessionBlockService(db_session)
    await blocks.complete_block(alice_blocks[0].id, alice)
    await blocks.complete_block(bob_blocks[0].id, bob)

    feed = await FriendActivityService(db_session).get_feed(alice.id, limit=50, offset=0)
    party_entries = [entry for entry in feed if entry.event_type == "party_completed"]
    assert len(party_entries) == 1
    assert party_entries[0].user_id == bob.id
    assert party_entries[0].party_size == 2
