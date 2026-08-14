"""TrainingPartyService.suggest_exercises/confirm_exercises: the "everyone
trains the same exercises" flow. Covers materialization into every joined
member's own DayPlan/TrainingSession/SessionBlock (both the rest-day and
no-plan-for-date starting points), the join-blocked-by-completed-training
guard, and late joiners picking up an already-finalized set.
"""
import uuid
from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from app.models.exercise import EquipmentType, Exercise, ExerciseCategory, TrainingPhase
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.user import User
from app.schemas.training_party import TrainingPartyCreate
from app.services.friend_service import FriendService
from app.services.training_party_service import TrainingPartyService

TODAY = date.today()
TOMORROW = TODAY + timedelta(days=1)


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"partyx_{unique}",
        email=f"partyx_{unique}@example.com",
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


def _make_exercise(**overrides) -> Exercise:
    # target_stat isn't a real Exercise field anymore (see ExerciseTargetStat)
    # and nothing in this file's tests reads it -- confirm_exercises works
    # off explicit exercise_ids, not stat-based selection -- so any caller
    # still passing it as an override is just silently dropped.
    overrides.pop("target_stat", None)
    defaults = dict(
        id=uuid.uuid4(),
        name=f"Exercise {uuid.uuid4().hex[:8]}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
        equipment_type=EquipmentType.BODYWEIGHT,
    )
    defaults.update(overrides)
    return Exercise(**defaults)


async def _add_day_plan(
    db_session, user_id: uuid.UUID, *, day_date: date, session_type: DaySessionType
) -> DayPlan:
    weekly_plan = WeeklyPlan(id=uuid.uuid4(), user_id=user_id, week_start_date=day_date)
    db_session.add(weekly_plan)
    await db_session.flush()
    day_plan = DayPlan(
        id=uuid.uuid4(), weekly_plan_id=weekly_plan.id, date=day_date, session_type=session_type
    )
    db_session.add(day_plan)
    await db_session.flush()
    return day_plan


async def _add_completed_block(db_session, day_plan: DayPlan, exercise: Exercise) -> None:
    from datetime import datetime, timezone

    block = SessionBlock(
        id=uuid.uuid4(),
        phase=TrainingPhase.MAIN,
        exercise_id=exercise.id,
        order=0,
        completed_at=datetime.now(timezone.utc),
    )
    training_session = TrainingSession(id=uuid.uuid4(), day_plan_id=day_plan.id, blocks=[block])
    db_session.add(training_session)
    await db_session.flush()


async def _make_party(db_session, creator: User, *friends: User) -> "TrainingPartyDetailRead":  # noqa: F821
    for friend in friends:
        await _befriend(db_session, creator, friend)
    service = TrainingPartyService(db_session)
    party = await service.create_party(
        creator, TrainingPartyCreate(target_date=TOMORROW, friend_ids=[f.id for f in friends])
    )
    for friend in friends:
        await service.respond_to_invite(friend, party.id, accept=True)
    return party


# -- confirm materializes the same exercises for everyone --


@pytest.mark.asyncio
async def test_confirm_materializes_same_exercise_ids_for_every_joined_member(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    exercise_a = _make_exercise()
    exercise_b = _make_exercise()
    db_session.add_all([alice, bob, exercise_a, exercise_b])
    await db_session.flush()
    party = await _make_party(db_session, alice, bob)

    service = TrainingPartyService(db_session)
    detail = await service.confirm_exercises(alice, party.id, [exercise_a.id, exercise_b.id])

    assert detail.exercises_finalized_at is not None
    assert [e.id for e in detail.exercises] == [exercise_a.id, exercise_b.id]

    for user in (alice, bob):
        day_plan = await service._schedule.get_day_plan_for_date(user.id, TOMORROW)
        assert day_plan is not None
        assert day_plan.session_type == DaySessionType.OFF_ICE
        exercise_ids = [b.exercise_id for b in day_plan.training_session.blocks]
        assert exercise_ids == [exercise_a.id, exercise_b.id]


@pytest.mark.asyncio
async def test_confirm_replaces_a_rest_day(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    exercise = _make_exercise()
    db_session.add_all([alice, bob, exercise])
    await db_session.flush()
    await _add_day_plan(db_session, bob.id, day_date=TOMORROW, session_type=DaySessionType.REST)
    party = await _make_party(db_session, alice, bob)

    service = TrainingPartyService(db_session)
    await service.confirm_exercises(alice, party.id, [exercise.id])

    day_plan = await service._schedule.get_day_plan_for_date(bob.id, TOMORROW)
    assert day_plan.session_type == DaySessionType.OFF_ICE
    assert [b.exercise_id for b in day_plan.training_session.blocks] == [exercise.id]


@pytest.mark.asyncio
async def test_confirm_builds_a_plan_from_scratch_when_member_has_none(db_session) -> None:
    """bob has no WeeklyPlan at all covering TOMORROW -- confirm must create
    one (a full 7-day week, see ScheduleService.ensure_day_plan_for_date)
    rather than erroring or leaving him without a plan."""
    alice = _make_user()
    bob = _make_user()
    exercise = _make_exercise()
    db_session.add_all([alice, bob, exercise])
    await db_session.flush()
    party = await _make_party(db_session, alice, bob)

    service = TrainingPartyService(db_session)
    await service.confirm_exercises(alice, party.id, [exercise.id])

    day_plan = await service._schedule.get_day_plan_for_date(bob.id, TOMORROW)
    assert day_plan is not None
    assert day_plan.session_type == DaySessionType.OFF_ICE
    assert [b.exercise_id for b in day_plan.training_session.blocks] == [exercise.id]


# -- join blocked by an already-completed training that day --


@pytest.mark.asyncio
async def test_cannot_join_party_with_a_completed_block_that_day(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    exercise = _make_exercise()
    db_session.add_all([alice, bob, exercise])
    await db_session.flush()
    await _befriend(db_session, alice, bob)
    bob_day_plan = await _add_day_plan(
        db_session, bob.id, day_date=TOMORROW, session_type=DaySessionType.OFF_ICE
    )
    await _add_completed_block(db_session, bob_day_plan, exercise)

    service = TrainingPartyService(db_session)
    party = await service.create_party(alice, TrainingPartyCreate(target_date=TOMORROW, friend_ids=[bob.id]))

    with pytest.raises(HTTPException) as exc_info:
        await service.respond_to_invite(bob, party.id, accept=True)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_cannot_create_party_with_a_completed_block_that_day(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    exercise = _make_exercise()
    db_session.add_all([alice, bob, exercise])
    await db_session.flush()
    await _befriend(db_session, alice, bob)
    alice_day_plan = await _add_day_plan(
        db_session, alice.id, day_date=TOMORROW, session_type=DaySessionType.OFF_ICE
    )
    await _add_completed_block(db_session, alice_day_plan, exercise)

    service = TrainingPartyService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.create_party(alice, TrainingPartyCreate(target_date=TOMORROW, friend_ids=[bob.id]))
    assert exc_info.value.status_code == 409


# -- late joiners --


@pytest.mark.asyncio
async def test_member_joining_after_finalization_gets_the_same_set(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    carol = _make_user()
    exercise = _make_exercise()
    db_session.add_all([alice, bob, carol, exercise])
    await db_session.flush()
    await _befriend(db_session, alice, bob)
    await _befriend(db_session, alice, carol)

    service = TrainingPartyService(db_session)
    party = await service.create_party(
        alice, TrainingPartyCreate(target_date=TOMORROW, friend_ids=[bob.id, carol.id])
    )
    await service.respond_to_invite(bob, party.id, accept=True)
    await service.confirm_exercises(alice, party.id, [exercise.id])
    # carol joins only now, after the set is already finalized.
    await service.respond_to_invite(carol, party.id, accept=True)

    carol_day_plan = await service._schedule.get_day_plan_for_date(carol.id, TOMORROW)
    assert carol_day_plan is not None
    assert [b.exercise_id for b in carol_day_plan.training_session.blocks] == [exercise.id]


# -- suggest/confirm authorization --


@pytest.mark.asyncio
async def test_only_creator_can_suggest_or_confirm(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    exercise = _make_exercise()
    db_session.add_all([alice, bob, exercise])
    await db_session.flush()
    party = await _make_party(db_session, alice, bob)

    service = TrainingPartyService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.suggest_exercises(bob, party.id)
    assert exc_info.value.status_code == 403

    with pytest.raises(HTTPException) as exc_info:
        await service.confirm_exercises(bob, party.id, [exercise.id])
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_confirm_rejects_unknown_exercise_id(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    db_session.add_all([alice, bob])
    await db_session.flush()
    party = await _make_party(db_session, alice, bob)

    service = TrainingPartyService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.confirm_exercises(alice, party.id, [uuid.uuid4()])
    assert exc_info.value.status_code == 400
