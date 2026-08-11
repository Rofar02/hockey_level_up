"""TeamService: multi-team membership, invite-code join flow, captain
approval, leave/disband, and the team-scoped leaderboard filter.

Same `_make_user` shape as test_pick_main_periodization.py -- first_name/
last_name are left unset (server_default="" populates them on flush), only
what each scenario actually needs is set explicitly.
"""
import uuid

import pytest
from fastapi import HTTPException

from app.models.user import User
from app.models.exercise import EquipmentType
from app.services.leaderboard_service import LeaderboardService
from app.services.team_service import TeamService


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"team_{unique}",
        email=f"team_{unique}@example.com",
        password_hash="irrelevant",
        equipment_access=EquipmentType.BODYWEIGHT,
    )
    defaults.update(overrides)
    return User(**defaults)


@pytest.mark.asyncio
async def test_create_team_makes_creator_captain_and_member(db_session) -> None:
    captain = _make_user()
    db_session.add(captain)
    await db_session.flush()

    service = TeamService(db_session)
    team = await service.create_team(captain, "Sharks")

    assert team.name == "Sharks"
    assert team.owner_id == captain.id
    assert team.is_captain is True
    assert len(team.invite_code) > 0
    assert [m.id for m in team.members] == [captain.id]
    assert team.members[0].is_captain is True


@pytest.mark.asyncio
async def test_user_can_belong_to_several_teams_simultaneously(db_session) -> None:
    captain_a = _make_user()
    captain_b = _make_user()
    player = _make_user()
    db_session.add_all([captain_a, captain_b, player])
    await db_session.flush()

    service = TeamService(db_session)
    team_a = await service.create_team(captain_a, "Team A")
    team_b = await service.create_team(captain_b, "Team B")

    request_a = await service.join_by_code(player, team_a.invite_code)
    request_b = await service.join_by_code(player, team_b.invite_code)
    await service.approve_request(captain_a, request_a.id)
    await service.approve_request(captain_b, request_b.id)

    my_teams = await service.list_my_teams(player)
    assert {t.id for t in my_teams} == {team_a.id, team_b.id}
    assert all(t.is_captain is False for t in my_teams)


@pytest.mark.asyncio
async def test_join_by_code_rejects_unknown_code(db_session) -> None:
    player = _make_user()
    db_session.add(player)
    await db_session.flush()

    service = TeamService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.join_by_code(player, "NOSUCHCODE")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_join_by_code_conflicts_if_already_a_member(db_session) -> None:
    captain = _make_user()
    player = _make_user()
    db_session.add_all([captain, player])
    await db_session.flush()

    service = TeamService(db_session)
    team = await service.create_team(captain, "Sharks")
    request = await service.join_by_code(player, team.invite_code)
    await service.approve_request(captain, request.id)

    with pytest.raises(HTTPException) as exc_info:
        await service.join_by_code(player, team.invite_code)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_join_by_code_conflicts_on_duplicate_pending_request(db_session) -> None:
    captain = _make_user()
    player = _make_user()
    db_session.add_all([captain, player])
    await db_session.flush()

    service = TeamService(db_session)
    team = await service.create_team(captain, "Sharks")
    await service.join_by_code(player, team.invite_code)

    with pytest.raises(HTTPException) as exc_info:
        await service.join_by_code(player, team.invite_code)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_pending_request_to_one_team_does_not_block_another(db_session) -> None:
    captain_a = _make_user()
    captain_b = _make_user()
    player = _make_user()
    db_session.add_all([captain_a, captain_b, player])
    await db_session.flush()

    service = TeamService(db_session)
    team_a = await service.create_team(captain_a, "Team A")
    team_b = await service.create_team(captain_b, "Team B")

    await service.join_by_code(player, team_a.invite_code)
    # Same player, a *different* team -- must not conflict with the
    # pending request against team_a.
    request_b = await service.join_by_code(player, team_b.invite_code)
    assert request_b.team_id == team_b.id

    pending = await service.list_my_pending_requests(player)
    assert {r.team_id for r in pending} == {team_a.id, team_b.id}


@pytest.mark.asyncio
async def test_approve_requires_captain(db_session) -> None:
    captain = _make_user()
    player = _make_user()
    outsider = _make_user()
    db_session.add_all([captain, player, outsider])
    await db_session.flush()

    service = TeamService(db_session)
    team = await service.create_team(captain, "Sharks")
    request = await service.join_by_code(player, team.invite_code)

    with pytest.raises(HTTPException) as exc_info:
        await service.approve_request(outsider, request.id)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_reject_leaves_requester_unjoined(db_session) -> None:
    captain = _make_user()
    player = _make_user()
    db_session.add_all([captain, player])
    await db_session.flush()

    service = TeamService(db_session)
    team = await service.create_team(captain, "Sharks")
    request = await service.join_by_code(player, team.invite_code)
    rejected = await service.reject_request(captain, request.id)

    assert rejected.status.value == "rejected"
    my_teams = await service.list_my_teams(player)
    assert my_teams == []


@pytest.mark.asyncio
async def test_leave_team_removes_membership(db_session) -> None:
    captain = _make_user()
    player = _make_user()
    db_session.add_all([captain, player])
    await db_session.flush()

    service = TeamService(db_session)
    team = await service.create_team(captain, "Sharks")
    request = await service.join_by_code(player, team.invite_code)
    await service.approve_request(captain, request.id)

    await service.leave_team(player, team.id)
    assert await service.list_my_teams(player) == []


@pytest.mark.asyncio
async def test_captain_cannot_leave_must_disband(db_session) -> None:
    captain = _make_user()
    db_session.add(captain)
    await db_session.flush()

    service = TeamService(db_session)
    team = await service.create_team(captain, "Sharks")

    with pytest.raises(HTTPException) as exc_info:
        await service.leave_team(captain, team.id)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_disband_removes_team_and_memberships(db_session) -> None:
    captain = _make_user()
    player = _make_user()
    db_session.add_all([captain, player])
    await db_session.flush()

    service = TeamService(db_session)
    team = await service.create_team(captain, "Sharks")
    request = await service.join_by_code(player, team.invite_code)
    await service.approve_request(captain, request.id)

    await service.disband_team(captain, team.id)

    assert await service.list_my_teams(player) == []
    with pytest.raises(HTTPException) as exc_info:
        await service.get_team(captain, team.id)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_disband_requires_captain(db_session) -> None:
    captain = _make_user()
    player = _make_user()
    db_session.add_all([captain, player])
    await db_session.flush()

    service = TeamService(db_session)
    team = await service.create_team(captain, "Sharks")
    request = await service.join_by_code(player, team.invite_code)
    await service.approve_request(captain, request.id)

    with pytest.raises(HTTPException) as exc_info:
        await service.disband_team(player, team.id)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_get_team_requires_membership(db_session) -> None:
    captain = _make_user()
    outsider = _make_user()
    db_session.add_all([captain, outsider])
    await db_session.flush()

    service = TeamService(db_session)
    team = await service.create_team(captain, "Sharks")

    with pytest.raises(HTTPException) as exc_info:
        await service.get_team(outsider, team.id)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_invite_code_generation_exhaustion_raises_500(db_session, monkeypatch) -> None:
    captain = _make_user()
    db_session.add(captain)
    await db_session.flush()

    service = TeamService(db_session)
    monkeypatch.setattr(service._teams, "invite_code_exists", lambda code: _always_true())

    with pytest.raises(HTTPException) as exc_info:
        await service.create_team(captain, "Sharks")
    assert exc_info.value.status_code == 500


async def _always_true() -> bool:
    return True


@pytest.mark.asyncio
async def test_team_leaderboard_filters_to_members_only(db_session) -> None:
    captain = _make_user(age=20)
    member = _make_user(age=22)
    outsider = _make_user(age=25)
    db_session.add_all([captain, member, outsider])
    await db_session.flush()

    service = TeamService(db_session)
    team = await service.create_team(captain, "Sharks")
    request = await service.join_by_code(member, team.invite_code)
    await service.approve_request(captain, request.id)

    entries = await LeaderboardService(db_session).get_team_leaderboard(team.id)
    assert {e.id for e in entries} == {captain.id, member.id}
