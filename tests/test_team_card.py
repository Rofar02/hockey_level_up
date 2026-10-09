"""Team card (2026-10-09): the captain's game score, and the card built
from it -- games, results, goals, streak, attendance, leaders -- plus the
team on another player's public card.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.team_event import TeamEvent, TeamEventAttendance, TeamEventAttendanceStatus, TeamEventType
from app.models.user import User
from app.schemas.team import TeamLeagueFields
from app.services.team_card_service import TeamCardService, _streak
from app.services.team_event_service import TeamEventService
from app.services.team_service import TeamService


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"card_{unique}",
        email=f"card_{unique}@example.com",
        password_hash="irrelevant",
    )
    defaults.update(overrides)
    return User(**defaults)


async def _team(db_session):
    captain = _make_user(last_name="Капитанов", level=9)
    player = _make_user(last_name="Игроков", level=4)
    db_session.add_all([captain, player])
    await db_session.flush()
    teams = TeamService(db_session)
    team = await teams.create_team(captain, "Медведи", TeamLeagueFields(city="Казань", league_code="nhl", division_code="hope"))
    request = await teams.join_by_code(player, team.invite_code)
    await teams.approve_request(captain, request.id)
    return captain, player, team


async def _played(db_session, captain, team_id, event_type=TeamEventType.GAME, days_ago=1) -> uuid.UUID:
    future = datetime.now(timezone.utc) + timedelta(days=2)
    opponent = "Волки" if event_type == TeamEventType.GAME else None
    event = await TeamEventService(db_session).create_event(captain, team_id, event_type, future, opponent)
    row = await db_session.get(TeamEvent, event.id)
    row.starts_at = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=1)
    await db_session.flush()
    return event.id


def test_streak_counts_the_latest_run() -> None:
    assert _streak([]) is None
    assert _streak(["В", "П", "В", "В"]) == "В2"
    assert _streak(["П"]) == "П1"


@pytest.mark.asyncio
async def test_only_captain_sets_score_of_a_played_game(db_session) -> None:
    captain, player, team = await _team(db_session)
    events = TeamEventService(db_session)
    game_id = await _played(db_session, captain, team.id)

    with pytest.raises(HTTPException) as exc:
        await events.set_score(player, team.id, game_id, 3, 1)
    assert exc.value.status_code == 403

    read = await events.set_score(captain, team.id, game_id, 3, 1)
    assert (read.our_score, read.opponent_score) == (3, 1)

    with pytest.raises(HTTPException) as exc:
        await events.set_score(captain, team.id, game_id, 3, None)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_score_rejected_for_training_and_future_game(db_session) -> None:
    captain, _, team = await _team(db_session)
    events = TeamEventService(db_session)
    training_id = await _played(db_session, captain, team.id, TeamEventType.TRAINING)
    with pytest.raises(HTTPException) as exc:
        await events.set_score(captain, team.id, training_id, 1, 0)
    assert exc.value.status_code == 422

    future = await events.create_event(
        captain, team.id, TeamEventType.GAME, datetime.now(timezone.utc) + timedelta(days=3), "Рыси"
    )
    with pytest.raises(HTTPException) as exc:
        await events.set_score(captain, team.id, future.id, 1, 0)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_card_counts_scored_games_attendance_and_leaders(db_session) -> None:
    captain, player, team = await _team(db_session)
    events = TeamEventService(db_session)
    win = await _played(db_session, captain, team.id, days_ago=3)
    loss = await _played(db_session, captain, team.id, days_ago=2)
    await _played(db_session, captain, team.id, days_ago=1)  # no score -- not counted
    await events.set_score(captain, team.id, win, 5, 2)
    await events.set_score(captain, team.id, loss, 1, 3)
    training_id = await _played(db_session, captain, team.id, TeamEventType.TRAINING)
    db_session.add(
        TeamEventAttendance(team_event_id=training_id, user_id=player.id, status=TeamEventAttendanceStatus.GOING)
    )
    await db_session.flush()

    stranger = _make_user()
    db_session.add(stranger)
    await db_session.flush()
    card = await TeamCardService(db_session).get_card(stranger, team.id)

    assert card.name == "Медведи"
    assert card.league_name == "Ночная хоккейная лига"
    assert card.division_name == "Лига Надежды"
    assert (card.games, card.wins, card.losses, card.draws) == (2, 1, 1, 0)
    assert (card.goals_for, card.goals_against) == (6, 5)
    assert card.streak == "П1"
    assert card.attendance_percent == 50
    assert card.is_member is False
    level_leader = next(leader for leader in card.leaders if leader.title == "Уровень")
    assert level_leader.name == "Капитанов"


@pytest.mark.asyncio
async def test_public_badge_shows_players_team(db_session) -> None:
    captain, player, team = await _team(db_session)
    badge = await TeamService(db_session).get_player_team_badge(player.id)
    assert badge is not None
    assert (badge.id, badge.name, badge.city) == (team.id, "Медведи", "Казань")

    loner = _make_user()
    db_session.add(loner)
    await db_session.flush()
    assert await TeamService(db_session).get_player_team_badge(loner.id) is None
