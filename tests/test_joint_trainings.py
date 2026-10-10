"""Joint trainings with another team (2026-10-09, release plan step 3.5):
the invite/accept flow, who sees what (a stranger never does), the shared
attendance and lineup, leaving, the same-day trap, and slots.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.team_event import TeamEventAttendanceStatus, TeamEventType, TeamIceScheduleTemplate
from app.models.team_event_guest import GuestTeamStatus
from app.models.user import User
from app.services.joint_training_service import JointTrainingService, can_see_event, event_team_ids
from app.services.team_event_service import TeamEventService
from app.services.team_service import TeamService


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(id=uuid.uuid4(), username=f"jt_{unique}", email=f"jt_{unique}@example.com", password_hash="x", timezone="UTC")
    defaults.update(overrides)
    return User(**defaults)


async def _team(db_session, name: str):
    captain, player = _make_user(), _make_user()
    db_session.add_all([captain, player])
    await db_session.flush()
    teams = TeamService(db_session)
    team = await teams.create_team(captain, name)
    request = await teams.join_by_code(player, team.invite_code)
    await teams.approve_request(captain, request.id)
    return captain, player, team


def _future(days: int = 2) -> datetime:
    return datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0) + timedelta(days=days)


async def _joint(db_session):
    host_captain, host_player, host = await _team(db_session, "Медведи Мечта")
    guest_captain, guest_player, guest = await _team(db_session, "Медведи Надежда")
    events = TeamEventService(db_session)
    event = await events.create_event(host_captain, host.id, TeamEventType.TRAINING, _future(), None)
    joint = JointTrainingService(db_session)
    await joint.invite_to_event(host_captain, host.id, event.id, guest.id)
    invitation = (await joint.list_incoming(guest_captain, guest.id))[0]
    await joint.answer(guest_captain, guest.id, invitation.id, accept=True)
    return host_captain, host_player, host, guest_captain, guest_player, guest, event


@pytest.mark.asyncio
async def test_guest_team_sees_and_marks_after_accepting(db_session) -> None:
    host_captain, host_player, host, guest_captain, guest_player, guest, event = await _joint(db_session)
    events = TeamEventService(db_session)

    listed = await events.list_events(guest_player, guest.id)
    assert [e.id for e in listed] == [event.id]
    assert listed[0].host_team_name == "Медведи Мечта"
    await events.set_my_attendance(guest_player, guest.id, event.id, TeamEventAttendanceStatus.GOING, None, None)
    await events.set_my_attendance(host_player, host.id, event.id, TeamEventAttendanceStatus.GOING, None, None)

    roster = await events.get_attendance_roster(host_captain, host.id, event.id)
    assert {m.user_id for m in roster.going} == {guest_player.id, host_player.id}


@pytest.mark.asyncio
async def test_stranger_team_never_sees_a_joint_event(db_session) -> None:
    _, _, _, _, _, _, event = await _joint(db_session)
    stranger_captain, stranger, stranger_team = await _team(db_session, "Чужие")
    events = TeamEventService(db_session)

    assert await can_see_event(db_session, stranger_team.id, await events._events.get_event(event.id)) is False
    with pytest.raises(HTTPException) as exc:
        await events.get_event(stranger, stranger_team.id, event.id)
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException):
        await events.set_my_attendance(stranger, stranger_team.id, event.id, TeamEventAttendanceStatus.GOING, None, None)
    assert await events.list_events(stranger, stranger_team.id) == []


@pytest.mark.asyncio
async def test_invited_but_not_accepted_sees_nothing(db_session) -> None:
    host_captain, _, host = await _team(db_session, "Хозяева")
    guest_captain, guest_player, guest = await _team(db_session, "Гости")
    events = TeamEventService(db_session)
    event = await events.create_event(host_captain, host.id, TeamEventType.TRAINING, _future(), None)
    await JointTrainingService(db_session).invite_to_event(host_captain, host.id, event.id, guest.id)

    assert await events.list_events(guest_player, guest.id) == []


@pytest.mark.asyncio
async def test_only_host_captain_edits_and_lineup_mixes_both_teams(db_session) -> None:
    host_captain, host_player, host, guest_captain, guest_player, guest, event = await _joint(db_session)
    events = TeamEventService(db_session)

    with pytest.raises(HTTPException):
        await events.cancel_event(guest_captain, guest.id, event.id)
    guest_view = await events.get_event(guest_captain, guest.id, event.id)
    assert guest_view.sections is None or guest_view.board_status is not None

    group = await events.create_lineup_group(host_captain, host.id, event.id, "Белые", "#ffffff")
    read = await events.assign_player(host_captain, host.id, event.id, guest_player.id, group.id)
    assert [p.user_id for p in read.players] == [guest_player.id]


@pytest.mark.asyncio
async def test_leaving_removes_the_guests_marks(db_session) -> None:
    host_captain, host_player, host, guest_captain, guest_player, guest, event = await _joint(db_session)
    events = TeamEventService(db_session)
    await events.set_my_attendance(guest_player, guest.id, event.id, TeamEventAttendanceStatus.GOING, None, None)

    await JointTrainingService(db_session).leave(guest_captain, guest.id, event.id)

    roster = await events.get_attendance_roster(host_captain, host.id, event.id)
    assert guest_player.id not in {m.user_id for m in roster.going}
    assert await events.list_events(guest_player, guest.id) == []
    assert await event_team_ids(db_session, await events._events.get_event(event.id)) == [host.id]


@pytest.mark.asyncio
async def test_same_day_own_training_needs_replace(db_session) -> None:
    host_captain, _, host = await _team(db_session, "Хозяева")
    guest_captain, _, guest = await _team(db_session, "Гости")
    events = TeamEventService(db_session)
    joint_event = await events.create_event(host_captain, host.id, TeamEventType.TRAINING, _future(3), None)
    own = await events.create_event(guest_captain, guest.id, TeamEventType.TRAINING, _future(3) + timedelta(hours=2), None)
    joint = JointTrainingService(db_session)
    await joint.invite_to_event(host_captain, host.id, joint_event.id, guest.id)
    invitation = (await joint.list_incoming(guest_captain, guest.id))[0]
    assert invitation.conflict is True

    with pytest.raises(HTTPException) as exc:
        await joint.answer(guest_captain, guest.id, invitation.id, accept=True)
    assert exc.value.status_code == 409

    result = await joint.answer(guest_captain, guest.id, invitation.id, accept=True, replace_own=True)
    assert result.status == GuestTeamStatus.ACCEPTED
    own_after = await events._events.get_event(own.id)
    assert own_after.status.value == "cancelled"


@pytest.mark.asyncio
async def test_slot_invitation_makes_stamped_trainings_joint(db_session) -> None:
    host_captain, _, host = await _team(db_session, "Хозяева")
    guest_captain, guest_player, guest = await _team(db_session, "Гости")
    template = TeamIceScheduleTemplate(team_id=host.id, weekday=_future(4).weekday(), start_time=_future(4).time())
    db_session.add(template)
    await db_session.flush()
    joint = JointTrainingService(db_session)
    await joint.invite_to_template(host_captain, host.id, template.id, guest.id)
    invitation = next(i for i in await joint.list_incoming(guest_captain, guest.id) if i.kind == "slot")
    await joint.answer(guest_captain, guest.id, invitation.id, accept=True)

    from app.services.team_event_scheduler import _stamp_template

    await _stamp_template(db_session, template, datetime.now(timezone.utc))
    await db_session.flush()

    listed = await TeamEventService(db_session).list_events(guest_player, guest.id)
    assert listed and all(e.host_team_name == "Хозяева" for e in listed)


@pytest.mark.asyncio
async def test_search_excludes_own_team(db_session) -> None:
    captain, _, team = await _team(db_session, "Поисковые Медведи")
    await _team(db_session, "Другие Медведи")
    hits = await JointTrainingService(db_session).search_teams(captain, team.id, "Медведи")
    assert team.id not in {h.id for h in hits}
    assert any(h.name == "Другие Медведи" for h in hits)
