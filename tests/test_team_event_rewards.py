"""TeamEventService diary/rewards slice: saving a TeamEventDiaryEntry for a
TRAINING event grants INTELLECT/PUCK_HANDLING/ON_ICE_SKATING + 50 XP once,
on first save; editing the note afterward never re-grants; a GAME event
rejects the entry entirely. Same _make_team_with_player shape as the other
team_event test modules.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.exercise import TargetStat
from app.models.progress import StatHistory, UserStat
from app.models.team_event import TeamEventType
from app.models.user import User
from app.services.team_event_service import TEAM_TRAINING_XP_BONUS, TeamEventService
from app.services.team_service import TeamService


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"reward_{unique}",
        email=f"reward_{unique}@example.com",
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


async def _stat_value(db_session, user_id: uuid.UUID, stat_type: TargetStat) -> float:
    result = await db_session.execute(
        select(UserStat.current_value).where(
            UserStat.user_id == user_id, UserStat.stat_type == stat_type
        )
    )
    return result.scalar_one_or_none() or 0.0


@pytest.mark.asyncio
async def test_first_save_grants_stats_and_xp_second_save_does_not(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _future(), None)

    await events.save_diary_entry(player, team.id, event.id, "Хорошая тренировка")

    await db_session.refresh(player)
    assert player.xp == TEAM_TRAINING_XP_BONUS
    for stat_type in (TargetStat.INTELLECT, TargetStat.PUCK_HANDLING, TargetStat.ON_ICE_SKATING):
        assert await _stat_value(db_session, player.id, stat_type) > 0

    history_count = (
        await db_session.execute(
            select(StatHistory).where(StatHistory.user_id == player.id)
        )
    ).scalars().all()
    assert len(history_count) == 3

    # Editing the note afterward must not re-grant.
    await events.save_diary_entry(player, team.id, event.id, "Отредактированная заметка")
    await db_session.refresh(player)
    assert player.xp == TEAM_TRAINING_XP_BONUS


@pytest.mark.asyncio
async def test_explicit_skip_still_grants_rewards(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _future(), None)

    entry = await events.save_diary_entry(player, team.id, event.id, None)
    assert entry.note is None

    await db_session.refresh(player)
    assert player.xp == TEAM_TRAINING_XP_BONUS


@pytest.mark.asyncio
async def test_game_event_rejects_diary_entry(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    event = await events.create_event(
        captain, team.id, TeamEventType.GAME, _future(), "Rival HC"
    )

    with pytest.raises(HTTPException) as exc_info:
        await events.save_diary_entry(player, team.id, event.id, "Игра прошла хорошо")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_reward_independent_of_attendance_status(db_session) -> None:
    """A player who marked not_going but showed up and filled the diary
    anyway still gets credited -- the diary is the only signal, per the
    v2 plan (section 8)."""
    from app.models.team_event import TeamEventAbsenceReason, TeamEventAttendanceStatus

    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _future(), None)
    await events.set_my_attendance(
        player,
        team.id,
        event.id,
        TeamEventAttendanceStatus.NOT_GOING,
        TeamEventAbsenceReason.OTHER,
        "planned to skip",
    )

    await events.save_diary_entry(player, team.id, event.id, "Came anyway")

    await db_session.refresh(player)
    assert player.xp == TEAM_TRAINING_XP_BONUS


@pytest.mark.asyncio
async def test_stat_gain_diminishes_near_cap(db_session) -> None:
    """Same curve as block_completed.stat_consumer: a stat starting near
    the 100 cap gains visibly less than one starting at 0 for an identical
    diary save."""
    low_starter, player, team = await _make_team_with_player(db_session)
    high_starter = _make_user()
    db_session.add(high_starter)
    await db_session.flush()
    teams = TeamService(db_session)
    request = await teams.join_by_code(high_starter, team.invite_code)
    await teams.approve_request(low_starter, request.id)

    db_session.add(
        UserStat(user_id=high_starter.id, stat_type=TargetStat.INTELLECT, current_value=80.0)
    )
    await db_session.flush()
    events = TeamEventService(db_session)
    event = await events.create_event(low_starter, team.id, TeamEventType.TRAINING, _future(), None)

    await events.save_diary_entry(player, team.id, event.id, None)
    await events.save_diary_entry(high_starter, team.id, event.id, None)

    low_gain = await _stat_value(db_session, player.id, TargetStat.INTELLECT)
    high_value = await _stat_value(db_session, high_starter.id, TargetStat.INTELLECT)
    high_gain = high_value - 80.0
    assert 0.0 < high_gain < low_gain <= 100.0
