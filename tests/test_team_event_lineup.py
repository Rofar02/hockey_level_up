"""TeamEventService lineup slice: free-form groups (TeamEventLineupGroup),
player placement (TeamEventLineupSlot), draft/publish visibility, and the
GAME-has-no-color guard. Same _make_team_with_player shape as
test_team_event_attendance.py.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.team_event import TeamEventType
from app.models.user import User
from app.services.team_event_service import TeamEventService
from app.services.team_service import TeamService


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"lineup_{unique}",
        email=f"lineup_{unique}@example.com",
        password_hash="irrelevant",
    )
    defaults.update(overrides)
    return User(**defaults)


def _future(hours: int = 48) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


async def _make_team_with_player(db_session):
    captain = _make_user()
    player = _make_user()
    db_session.add_all([captain, player])
    await db_session.flush()

    teams = TeamService(db_session)
    team = await teams.create_team(captain, "Sharks")
    request = await teams.join_by_code(player, team.invite_code)
    await teams.approve_request(captain, request.id)
    return captain, player, team


@pytest.mark.asyncio
async def test_lineup_draft_hides_groups_from_non_captain(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _future(), None)

    group = await events.create_lineup_group(captain, team.id, event.id, "White", "#ffffff")
    await events.assign_player(captain, team.id, event.id, player.id, group.id)

    as_player = await events.get_lineup(player, team.id, event.id)
    assert as_player.lineup_status == "draft"
    assert as_player.groups is None
    assert as_player.unassigned is None

    as_captain = await events.get_lineup(captain, team.id, event.id)
    assert as_captain.groups is not None
    assert len(as_captain.groups) == 1
    assert [p.user_id for p in as_captain.groups[0].players] == [player.id]
    assert [p.user_id for p in as_captain.unassigned] == [captain.id]

    published = await events.publish_lineup(captain, team.id, event.id)
    assert published.lineup_status == "published"

    as_player_after = await events.get_lineup(player, team.id, event.id)
    assert as_player_after.groups is not None
    assert as_player_after.groups[0].name == "White"


@pytest.mark.asyncio
async def test_color_rejected_for_game_group(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    event = await events.create_event(
        captain, team.id, TeamEventType.GAME, _future(), "Rival HC"
    )

    with pytest.raises(HTTPException) as exc_info:
        await events.create_lineup_group(captain, team.id, event.id, "Line 1", "#ff0000")
    assert exc_info.value.status_code == 400

    # No color is fine for a game.
    group = await events.create_lineup_group(captain, team.id, event.id, "Line 1", None)
    assert group.color is None


@pytest.mark.asyncio
async def test_assigning_player_twice_moves_them_between_groups(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _future(), None)

    group_a = await events.create_lineup_group(captain, team.id, event.id, "A", None)
    group_b = await events.create_lineup_group(captain, team.id, event.id, "B", None)

    await events.assign_player(captain, team.id, event.id, player.id, group_a.id)
    await events.assign_player(captain, team.id, event.id, player.id, group_b.id)

    lineup = await events.get_lineup(captain, team.id, event.id)
    by_id = {g.id: g for g in lineup.groups}
    assert by_id[group_a.id].players == []
    assert [p.user_id for p in by_id[group_b.id].players] == [player.id]


@pytest.mark.asyncio
async def test_unassign_player_returns_them_to_unassigned(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _future(), None)
    group = await events.create_lineup_group(captain, team.id, event.id, "A", None)
    await events.assign_player(captain, team.id, event.id, player.id, group.id)

    await events.unassign_player(captain, team.id, event.id, player.id)

    lineup = await events.get_lineup(captain, team.id, event.id)
    assert lineup.groups[0].players == []
    assert player.id in {p.user_id for p in lineup.unassigned}


@pytest.mark.asyncio
async def test_delete_group_frees_its_players_and_keeps_order_dense(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _future(), None)
    group_a = await events.create_lineup_group(captain, team.id, event.id, "A", None)
    group_b = await events.create_lineup_group(captain, team.id, event.id, "B", None)
    await events.assign_player(captain, team.id, event.id, player.id, group_a.id)

    await events.delete_lineup_group(captain, team.id, event.id, group_a.id)

    lineup = await events.get_lineup(captain, team.id, event.id)
    assert [g.id for g in lineup.groups] == [group_b.id]
    assert player.id in {p.user_id for p in lineup.unassigned}


@pytest.mark.asyncio
async def test_lineup_group_requires_captain(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _future(), None)

    with pytest.raises(HTTPException) as exc_info:
        await events.create_lineup_group(player, team.id, event.id, "A", None)
    assert exc_info.value.status_code == 403


# -- slots and the current lineup (2026-10-09) --


@pytest.mark.asyncio
async def test_slot_marks_group_kind_and_takes_spot_from_previous_holder(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    event = await events.create_event(captain, team.id, TeamEventType.GAME, _future(), "Rivals")
    line = await events.create_lineup_group(captain, team.id, event.id, "1 звено", None)

    await events.assign_player(captain, team.id, event.id, player.id, line.id, "C")
    read = await events.assign_player(captain, team.id, event.id, captain.id, line.id, "LW")
    assert read.kind == "forwards"
    assert [p.slot for p in read.players] == ["LW", "C"]

    # The captain takes the centre: the player stays in the line, without a spot.
    read = await events.assign_player(captain, team.id, event.id, captain.id, line.id, "C")
    slots = {p.user_id: p.slot for p in read.players}
    assert slots == {captain.id: "C", player.id: None}

    with pytest.raises(HTTPException) as exc_info:
        await events.assign_player(captain, team.id, event.id, player.id, line.id, "XX")
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_defense_pair_kind(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    event = await events.create_event(captain, team.id, TeamEventType.GAME, _future(), "Rivals")
    pair = await events.create_lineup_group(captain, team.id, event.id, "1 пара", None)
    await events.assign_player(captain, team.id, event.id, player.id, pair.id, "LD")
    read = await events.assign_player(captain, team.id, event.id, captain.id, pair.id, "RD")
    assert read.kind == "defense"


@pytest.mark.asyncio
async def test_current_lineup_is_next_game_and_hidden_until_published(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    assert (await events.get_current_lineup(player, team.id)).event is None

    later = await events.create_event(captain, team.id, TeamEventType.GAME, _future(96), "Later")
    sooner = await events.create_event(captain, team.id, TeamEventType.GAME, _future(24), "Sooner")
    group = await events.create_lineup_group(captain, team.id, sooner.id, "1 звено", None)
    await events.assign_player(captain, team.id, sooner.id, player.id, group.id, "RW")

    as_player = await events.get_current_lineup(player, team.id)
    assert as_player.event.id == sooner.id
    assert as_player.lineup.groups is None

    await events.publish_lineup(captain, team.id, sooner.id)
    as_player = await events.get_current_lineup(player, team.id)
    assert as_player.lineup.groups[0].players[0].slot == "RW"
    assert later.id != sooner.id


@pytest.mark.asyncio
async def test_current_lineup_requires_membership(db_session) -> None:
    captain, _, team = await _make_team_with_player(db_session)
    stranger = _make_user()
    db_session.add(stranger)
    await db_session.flush()
    with pytest.raises(HTTPException) as exc_info:
        await TeamEventService(db_session).get_current_lineup(stranger, team.id)
    assert exc_info.value.status_code == 403
