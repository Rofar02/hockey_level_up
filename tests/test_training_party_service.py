"""TrainingPartyService: create/invite/respond/leave/cancel, and per-member
training-status resolution (no_plan_for_date/resting/game_day/not_started/
in_progress/completed). Auto-completion via SessionBlockService is covered
separately in test_training_party_auto_completion.py.
"""
import uuid
from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from app.models.exercise import EquipmentType, Exercise, ExerciseCategory, TargetStat, TrainingPhase
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.user import User
from app.schemas.training_party import TrainingPartyCreate
from app.services.friend_service import FriendService
from app.services.training_party_service import TrainingPartyService

TODAY = date.today()
TOMORROW = TODAY + timedelta(days=1)
YESTERDAY = TODAY - timedelta(days=1)


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"party_{unique}",
        email=f"party_{unique}@example.com",
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
        target_stat=TargetStat.STRENGTH,
        difficulty_level=3,
        equipment_type=EquipmentType.GYM,
    )


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


async def _add_blocks(db_session, day_plan: DayPlan, exercise: Exercise, *, count: int) -> list[SessionBlock]:
    blocks = [
        SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=i)
        for i in range(count)
    ]
    training_session = TrainingSession(id=uuid.uuid4(), day_plan_id=day_plan.id, blocks=blocks)
    db_session.add(training_session)
    await db_session.flush()
    return blocks


# -- create_party --


@pytest.mark.asyncio
async def test_create_party_joins_creator_and_invites_friends(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    db_session.add_all([alice, bob])
    await db_session.flush()
    await _befriend(db_session, alice, bob)

    party = await TrainingPartyService(db_session).create_party(
        alice, TrainingPartyCreate(target_date=TOMORROW, friend_ids=[bob.id])
    )

    by_id = {m.user_id: m for m in party.members}
    assert by_id[alice.id].membership_status == "joined"
    assert by_id[bob.id].membership_status == "invited"
    assert party.status == "pending"


@pytest.mark.asyncio
async def test_create_party_rejects_non_friend(db_session) -> None:
    alice = _make_user()
    stranger = _make_user()
    db_session.add_all([alice, stranger])
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await TrainingPartyService(db_session).create_party(
            alice, TrainingPartyCreate(target_date=TOMORROW, friend_ids=[stranger.id])
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_create_party_rejects_past_date(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    db_session.add_all([alice, bob])
    await db_session.flush()
    await _befriend(db_session, alice, bob)

    with pytest.raises(HTTPException) as exc_info:
        await TrainingPartyService(db_session).create_party(
            alice, TrainingPartyCreate(target_date=YESTERDAY, friend_ids=[bob.id])
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_create_party_with_only_self_in_friend_ids_rejected(db_session) -> None:
    alice = _make_user()
    db_session.add(alice)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await TrainingPartyService(db_session).create_party(
            alice, TrainingPartyCreate(target_date=TOMORROW, friend_ids=[alice.id])
        )
    assert exc_info.value.status_code == 400


# -- invites / respond --


@pytest.mark.asyncio
async def test_accept_invite_moves_to_joined(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    db_session.add_all([alice, bob])
    await db_session.flush()
    await _befriend(db_session, alice, bob)

    service = TrainingPartyService(db_session)
    party = await service.create_party(alice, TrainingPartyCreate(target_date=TOMORROW, friend_ids=[bob.id]))

    invites = await service.list_incoming_invites(bob)
    assert {i.party_id for i in invites} == {party.id}

    updated = await service.respond_to_invite(bob, party.id, accept=True)
    bob_member = next(m for m in updated.members if m.user_id == bob.id)
    assert bob_member.membership_status == "joined"
    assert await service.list_incoming_invites(bob) == []


@pytest.mark.asyncio
async def test_decline_invite_leaves_declined(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    db_session.add_all([alice, bob])
    await db_session.flush()
    await _befriend(db_session, alice, bob)

    service = TrainingPartyService(db_session)
    party = await service.create_party(alice, TrainingPartyCreate(target_date=TOMORROW, friend_ids=[bob.id]))
    updated = await service.respond_to_invite(bob, party.id, accept=False)

    bob_member = next(m for m in updated.members if m.user_id == bob.id)
    assert bob_member.membership_status == "declined"


@pytest.mark.asyncio
async def test_respond_requires_being_a_member(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    outsider = _make_user()
    db_session.add_all([alice, bob, outsider])
    await db_session.flush()
    await _befriend(db_session, alice, bob)

    service = TrainingPartyService(db_session)
    party = await service.create_party(alice, TrainingPartyCreate(target_date=TOMORROW, friend_ids=[bob.id]))

    with pytest.raises(HTTPException) as exc_info:
        await service.respond_to_invite(outsider, party.id, accept=True)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_respond_twice_conflicts(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    db_session.add_all([alice, bob])
    await db_session.flush()
    await _befriend(db_session, alice, bob)

    service = TrainingPartyService(db_session)
    party = await service.create_party(alice, TrainingPartyCreate(target_date=TOMORROW, friend_ids=[bob.id]))
    await service.respond_to_invite(bob, party.id, accept=True)

    with pytest.raises(HTTPException) as exc_info:
        await service.respond_to_invite(bob, party.id, accept=False)
    assert exc_info.value.status_code == 409


# -- leave / cancel --


@pytest.mark.asyncio
async def test_member_can_leave(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    db_session.add_all([alice, bob])
    await db_session.flush()
    await _befriend(db_session, alice, bob)

    service = TrainingPartyService(db_session)
    party = await service.create_party(alice, TrainingPartyCreate(target_date=TOMORROW, friend_ids=[bob.id]))
    await service.respond_to_invite(bob, party.id, accept=True)
    await service.leave_party(bob, party.id)

    detail = await service.get_party(alice, party.id)
    # leave deletes the membership row entirely -- bob shouldn't appear at all.
    assert bob.id not in {m.user_id for m in detail.members}


@pytest.mark.asyncio
async def test_creator_cannot_leave_must_cancel(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    db_session.add_all([alice, bob])
    await db_session.flush()
    await _befriend(db_session, alice, bob)

    service = TrainingPartyService(db_session)
    party = await service.create_party(alice, TrainingPartyCreate(target_date=TOMORROW, friend_ids=[bob.id]))

    with pytest.raises(HTTPException) as exc_info:
        await service.leave_party(alice, party.id)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_cancel_requires_creator(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    db_session.add_all([alice, bob])
    await db_session.flush()
    await _befriend(db_session, alice, bob)

    service = TrainingPartyService(db_session)
    party = await service.create_party(alice, TrainingPartyCreate(target_date=TOMORROW, friend_ids=[bob.id]))
    await service.respond_to_invite(bob, party.id, accept=True)

    with pytest.raises(HTTPException) as exc_info:
        await service.cancel_party(bob, party.id)
    assert exc_info.value.status_code == 403

    await service.cancel_party(alice, party.id)
    detail = await service.get_party(alice, party.id)
    assert detail.status == "cancelled"


@pytest.mark.asyncio
async def test_get_party_requires_membership(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    outsider = _make_user()
    db_session.add_all([alice, bob, outsider])
    await db_session.flush()
    await _befriend(db_session, alice, bob)

    service = TrainingPartyService(db_session)
    party = await service.create_party(alice, TrainingPartyCreate(target_date=TOMORROW, friend_ids=[bob.id]))

    with pytest.raises(HTTPException) as exc_info:
        await service.get_party(outsider, party.id)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_list_my_parties_only_includes_joined(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    carol = _make_user()
    db_session.add_all([alice, bob, carol])
    await db_session.flush()
    await _befriend(db_session, alice, bob)
    await _befriend(db_session, alice, carol)

    service = TrainingPartyService(db_session)
    party = await service.create_party(
        alice, TrainingPartyCreate(target_date=TOMORROW, friend_ids=[bob.id, carol.id])
    )
    await service.respond_to_invite(bob, party.id, accept=True)
    # carol never responds -- stays invited, not joined.

    alice_parties = await service.list_my_parties(alice)
    bob_parties = await service.list_my_parties(bob)
    carol_parties = await service.list_my_parties(carol)
    assert {p.id for p in alice_parties} == {party.id}
    assert {p.id for p in bob_parties} == {party.id}
    assert carol_parties == []
    assert alice_parties[0].is_creator is True
    assert bob_parties[0].is_creator is False
    assert alice_parties[0].member_count == 3


# -- training status resolution --


@pytest.mark.asyncio
async def test_member_with_no_plan_shows_no_plan_for_date(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    db_session.add_all([alice, bob])
    await db_session.flush()
    await _befriend(db_session, alice, bob)
    # bob has no WeeklyPlan at all covering TOMORROW.

    service = TrainingPartyService(db_session)
    party = await service.create_party(alice, TrainingPartyCreate(target_date=TOMORROW, friend_ids=[bob.id]))
    await service.respond_to_invite(bob, party.id, accept=True)

    detail = await service.get_party(alice, party.id)
    bob_member = next(m for m in detail.members if m.user_id == bob.id)
    assert bob_member.training_status == "no_plan_for_date"


@pytest.mark.asyncio
async def test_member_resting_shows_resting(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    db_session.add_all([alice, bob])
    await db_session.flush()
    await _befriend(db_session, alice, bob)
    await _add_day_plan(db_session, bob.id, day_date=TOMORROW, session_type=DaySessionType.REST)

    service = TrainingPartyService(db_session)
    party = await service.create_party(alice, TrainingPartyCreate(target_date=TOMORROW, friend_ids=[bob.id]))
    await service.respond_to_invite(bob, party.id, accept=True)

    detail = await service.get_party(alice, party.id)
    bob_member = next(m for m in detail.members if m.user_id == bob.id)
    assert bob_member.training_status == "resting"


@pytest.mark.asyncio
async def test_member_game_day_shows_game_day(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    db_session.add_all([alice, bob])
    await db_session.flush()
    await _befriend(db_session, alice, bob)
    await _add_day_plan(db_session, bob.id, day_date=TOMORROW, session_type=DaySessionType.GAME)

    service = TrainingPartyService(db_session)
    party = await service.create_party(alice, TrainingPartyCreate(target_date=TOMORROW, friend_ids=[bob.id]))
    await service.respond_to_invite(bob, party.id, accept=True)

    detail = await service.get_party(alice, party.id)
    bob_member = next(m for m in detail.members if m.user_id == bob.id)
    assert bob_member.training_status == "game_day"


@pytest.mark.asyncio
async def test_member_training_progress_not_started_in_progress_completed(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    exercise = _make_exercise()
    db_session.add_all([alice, bob, exercise])
    await db_session.flush()
    await _befriend(db_session, alice, bob)
    day_plan = await _add_day_plan(db_session, bob.id, day_date=TOMORROW, session_type=DaySessionType.OFF_ICE)
    blocks = await _add_blocks(db_session, day_plan, exercise, count=3)

    service = TrainingPartyService(db_session)
    party = await service.create_party(alice, TrainingPartyCreate(target_date=TOMORROW, friend_ids=[bob.id]))
    await service.respond_to_invite(bob, party.id, accept=True)

    def bob_row(detail):
        return next(m for m in detail.members if m.user_id == bob.id)

    detail = await service.get_party(alice, party.id)
    row = bob_row(detail)
    assert row.training_status == "not_started"
    assert (row.completed_blocks, row.total_blocks) == (0, 3)

    from datetime import datetime, timezone

    blocks[0].completed_at = datetime.now(timezone.utc)
    await db_session.flush()
    detail = await service.get_party(alice, party.id)
    row = bob_row(detail)
    assert row.training_status == "in_progress"
    assert (row.completed_blocks, row.total_blocks) == (1, 3)

    for block in blocks[1:]:
        block.completed_at = datetime.now(timezone.utc)
    await db_session.flush()
    detail = await service.get_party(alice, party.id)
    row = bob_row(detail)
    assert row.training_status == "completed"
    assert (row.completed_blocks, row.total_blocks) == (3, 3)


@pytest.mark.asyncio
async def test_invited_and_declined_members_have_no_training_status(db_session) -> None:
    alice = _make_user()
    bob = _make_user()
    carol = _make_user()
    db_session.add_all([alice, bob, carol])
    await db_session.flush()
    await _befriend(db_session, alice, bob)
    await _befriend(db_session, alice, carol)

    service = TrainingPartyService(db_session)
    party = await service.create_party(
        alice, TrainingPartyCreate(target_date=TOMORROW, friend_ids=[bob.id, carol.id])
    )
    await service.respond_to_invite(carol, party.id, accept=False)
    # bob never responds -- stays invited.

    detail = await service.get_party(alice, party.id)
    bob_member = next(m for m in detail.members if m.user_id == bob.id)
    carol_member = next(m for m in detail.members if m.user_id == carol.id)
    assert bob_member.training_status is None
    assert carol_member.training_status is None
