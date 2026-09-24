"""TeamEventService: TeamEvent creation and the board (TeamEventDrill) --
draft/publish visibility, captain-only writes, reorder, and the
game-has-no-board guard. Same `_make_user` shape as test_team_service.py.
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
        username=f"team_event_{unique}",
        email=f"team_event_{unique}@example.com",
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
async def test_create_training_event_requires_captain(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)

    with pytest.raises(HTTPException) as exc_info:
        await events.create_event(player, team.id, TeamEventType.TRAINING, _future(), None)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_game_requires_opponent_name_training_rejects_it(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)

    with pytest.raises(HTTPException) as exc_info:
        await events.create_event(captain, team.id, TeamEventType.GAME, _future(), None)
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException) as exc_info:
        await events.create_event(
            captain, team.id, TeamEventType.TRAINING, _future(), "Rival HC"
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_board_draft_hides_drills_from_non_captain(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)

    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _future(), None)
    await events.add_drill(captain, team.id, event.id, "Edge work", "Inside/outside edges")

    as_player = await events.get_event(player, team.id, event.id)
    assert as_player.board_status == "draft"
    assert as_player.drills is None

    as_captain = await events.get_event(captain, team.id, event.id)
    assert as_captain.drills is not None
    assert len(as_captain.drills) == 1

    published = await events.publish_board(captain, team.id, event.id)
    assert published.board_status == "published"

    as_player_after = await events.get_event(player, team.id, event.id)
    assert as_player_after.drills is not None
    assert as_player_after.drills[0].title == "Edge work"


@pytest.mark.asyncio
async def test_game_event_has_no_board(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)

    event = await events.create_event(
        captain, team.id, TeamEventType.GAME, _future(), "Rival HC"
    )
    assert event.board_status is None
    assert event.drills is None

    with pytest.raises(HTTPException) as exc_info:
        await events.add_drill(captain, team.id, event.id, "Warmup", None)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_reorder_and_delete_drill_keep_order_dense(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)

    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _future(), None)
    first = await events.add_drill(captain, team.id, event.id, "Drill 1", None)
    second = await events.add_drill(captain, team.id, event.id, "Drill 2", None)
    third = await events.add_drill(captain, team.id, event.id, "Drill 3", None)
    assert [d.order for d in (first, second, third)] == [0, 1, 2]

    reordered = await events.reorder_drills(
        captain, team.id, event.id, [third.id, first.id, second.id]
    )
    assert [d.id for d in reordered] == [third.id, first.id, second.id]
    assert [d.order for d in reordered] == [0, 1, 2]

    await events.delete_drill(captain, team.id, event.id, first.id)
    remaining = (await events.get_event(captain, team.id, event.id)).drills
    assert [d.id for d in remaining] == [third.id, second.id]
    assert [d.order for d in remaining] == [0, 1]


@pytest.mark.asyncio
async def test_reorder_rejects_mismatched_drill_ids(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)

    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _future(), None)
    await events.add_drill(captain, team.id, event.id, "Drill 1", None)

    with pytest.raises(HTTPException) as exc_info:
        await events.reorder_drills(captain, team.id, event.id, [uuid.uuid4()])
    assert exc_info.value.status_code == 400
