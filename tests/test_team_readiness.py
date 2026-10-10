"""Team readiness for the captain (2026-10-09, release plan step 9)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.exercise import MuscleGroup
from app.models.progress import UserMuscleLoad
from app.models.team_event import TeamEventAttendance, TeamEventAttendanceStatus, TeamEventType
from app.models.user import User
from app.services.team_event_service import TeamEventService
from app.services.team_readiness_service import TeamReadinessService, readiness_line
from app.services.team_service import TeamService


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(id=uuid.uuid4(), username=f"rd_{unique}", email=f"rd_{unique}@example.com", password_hash="x")
    defaults.update(overrides)
    return User(**defaults)


async def _team_with_players(db_session, count: int):
    captain = _make_user(last_name="Капитан")
    players = [_make_user(last_name=f"Игрок{i}") for i in range(count)]
    db_session.add_all([captain, *players])
    await db_session.flush()
    teams = TeamService(db_session)
    team = await teams.create_team(captain, "Готовые")
    for player in players:
        request = await teams.join_by_code(player, team.invite_code)
        await teams.approve_request(captain, request.id)
    event = await TeamEventService(db_session).create_event(
        captain, team.id, TeamEventType.TRAINING, datetime.now(timezone.utc) + timedelta(days=2), None
    )
    for player in players:
        db_session.add(TeamEventAttendance(team_event_id=event.id, user_id=player.id, status=TeamEventAttendanceStatus.GOING))
    await db_session.flush()
    return captain, players, team, event


def _load(user: User, muscle: MuscleGroup, value: float) -> UserMuscleLoad:
    return UserMuscleLoad(user_id=user.id, muscle_group=muscle, current_value=value, last_updated_at=datetime.now(timezone.utc))


@pytest.mark.asyncio
async def test_captain_sees_each_going_player_by_name(db_session) -> None:
    captain, players, team, event = await _team_with_players(db_session, 4)
    fresh, tired, overloaded, silent = players
    db_session.add_all(
        [
            _load(fresh, MuscleGroup.QUADS, 1.0),
            _load(tired, MuscleGroup.GLUTES, 6.0),
            _load(overloaded, MuscleGroup.QUADS, 9.5),
        ]
    )
    await db_session.flush()

    readiness = await TeamReadinessService(db_session).for_event(captain, team.id, event.id)

    statuses = {p.user_id: p.status for p in readiness.players}
    assert statuses == {fresh.id: "fresh", tired.id: "tired", overloaded.id: "overloaded", silent.id: "no_data"}
    assert (readiness.going, readiness.fresh, readiness.tired, readiness.overloaded, readiness.no_data) == (4, 1, 1, 1, 1)
    assert readiness.players[0].status == "overloaded"
    assert readiness_line(readiness) == "Готовность: 1 свежие, 1 устали, 1 перегружены, 1 без данных"


@pytest.mark.asyncio
async def test_only_captain_sees_readiness(db_session) -> None:
    captain, players, team, event = await _team_with_players(db_session, 1)
    with pytest.raises(HTTPException) as exc:
        await TeamReadinessService(db_session).for_event(players[0], team.id, event.id)
    assert exc.value.status_code == 403
