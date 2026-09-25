"""Team-training rewards through the personal diary: there is no separate
team diary -- the first personal-diary save for a day a TRAINING event took
over (DayPlan.team_event_id) grants INTELLECT/PUCK_HANDLING/ON_ICE_SKATING +
50 XP once. Editing the note never re-grants; a game day, an ordinary ice
day or a player who left the team get nothing; a player already rewarded
through the old team diary isn't rewarded again.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.models.exercise import TargetStat
from app.models.progress import StatHistory, UserStat
from app.models.schedule import DaySessionType, DayPlan, TrainingBlock, TrainingSession, WeeklyPlan
from app.models.team import TeamMembership
from app.models.team_event import TeamEventType
from app.models.user import User
from app.repositories.team_event_repository import TeamEventRepository
from app.services.team_event_service import TEAM_TRAINING_XP_BONUS, TeamEventService
from app.services.team_service import TeamService
from app.services.training_diary_service import TrainingDiaryService


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


async def _day(
    db_session,
    user: User,
    session_type: DaySessionType = DaySessionType.ON_ICE,
    team_event_id: uuid.UUID | None = None,
    block_number: int = 1,
) -> TrainingSession:
    """One day of the user's own week, optionally taken over by a team
    event -- what the diary is written against."""
    monday = date.today() - timedelta(days=date.today().weekday()) + timedelta(weeks=block_number - 1)
    block = TrainingBlock(id=uuid.uuid4(), user_id=user.id, block_number=block_number, phase_started_at=monday)
    db_session.add(block)
    await db_session.flush()
    session = TrainingSession(id=uuid.uuid4(), blocks=[])
    weekly_plan = WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=monday, training_block_id=block.id)
    weekly_plan.day_plans.append(
        DayPlan(
            id=uuid.uuid4(),
            date=monday,
            session_type=session_type,
            team_event_id=team_event_id,
            training_session=session,
        )
    )
    db_session.add(weekly_plan)
    await db_session.flush()
    return session


async def _stat_value(db_session, user_id: uuid.UUID, stat_type: TargetStat) -> float:
    result = await db_session.execute(
        select(UserStat.current_value).where(
            UserStat.user_id == user_id, UserStat.stat_type == stat_type
        )
    )
    return result.scalar_one_or_none() or 0.0


async def _training(db_session, captain, team):
    return await TeamEventService(db_session).create_event(
        captain, team.id, TeamEventType.TRAINING, _future(), None
    )


@pytest.mark.asyncio
async def test_first_diary_save_on_a_team_day_grants_stats_and_xp_once(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    event = await _training(db_session, captain, team)
    session = await _day(db_session, player, team_event_id=event.id)
    diary = TrainingDiaryService(db_session)

    await diary.save_entry(player, session.id, "Хорошая тренировка")

    await db_session.refresh(player)
    assert player.xp == TEAM_TRAINING_XP_BONUS
    for stat_type in (TargetStat.INTELLECT, TargetStat.PUCK_HANDLING, TargetStat.ON_ICE_SKATING):
        assert await _stat_value(db_session, player.id, stat_type) > 0
    history = (await db_session.execute(select(StatHistory).where(StatHistory.user_id == player.id))).scalars().all()
    assert len(history) == 3

    # Editing the note afterward must not re-grant.
    await diary.save_entry(player, session.id, "Отредактированная заметка")
    await db_session.refresh(player)
    assert player.xp == TEAM_TRAINING_XP_BONUS


@pytest.mark.asyncio
async def test_explicit_skip_still_grants_rewards(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    event = await _training(db_session, captain, team)
    session = await _day(db_session, player, team_event_id=event.id)

    entry = await TrainingDiaryService(db_session).save_entry(player, session.id, None)
    assert entry.note is None

    await db_session.refresh(player)
    assert player.xp == TEAM_TRAINING_XP_BONUS


@pytest.mark.asyncio
async def test_the_coach_is_rewarded_the_same_way(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    event = await _training(db_session, captain, team)
    session = await _day(db_session, captain, team_event_id=event.id)

    await TrainingDiaryService(db_session).save_entry(captain, session.id, "Провёл тренировку")

    await db_session.refresh(captain)
    assert captain.xp == TEAM_TRAINING_XP_BONUS


@pytest.mark.asyncio
async def test_game_day_and_ordinary_ice_day_grant_no_team_reward(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    game = await TeamEventService(db_session).create_event(
        captain, team.id, TeamEventType.GAME, _future(), "Rival HC"
    )
    game_day = await _day(db_session, player, DaySessionType.GAME, team_event_id=game.id)
    ordinary_ice = await _day(db_session, player, DaySessionType.ON_ICE, block_number=2)
    diary = TrainingDiaryService(db_session)

    await diary.save_entry(player, game_day.id, "Игра прошла хорошо")
    await diary.save_entry(player, ordinary_ice.id, "Свой лёд")

    await db_session.refresh(player)
    assert player.xp == 0


@pytest.mark.asyncio
async def test_player_who_left_the_team_gets_no_reward(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    event = await _training(db_session, captain, team)
    session = await _day(db_session, player, team_event_id=event.id)
    await db_session.execute(delete(TeamMembership).where(TeamMembership.user_id == player.id))
    await db_session.flush()

    await TrainingDiaryService(db_session).save_entry(player, session.id, "Уже не в команде")

    await db_session.refresh(player)
    assert player.xp == 0


@pytest.mark.asyncio
async def test_already_rewarded_through_the_old_team_diary_is_not_rewarded_again(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    event = await _training(db_session, captain, team)
    # The old team diary tab left this marker (and already paid out).
    await TeamEventRepository(db_session).create_diary_entry(event.id, player.id, "старая запись")
    session = await _day(db_session, player, team_event_id=event.id)

    await TrainingDiaryService(db_session).save_entry(player, session.id, "Новая запись")

    await db_session.refresh(player)
    assert player.xp == 0


@pytest.mark.asyncio
async def test_stat_gain_diminishes_near_cap(db_session) -> None:
    """Same curve as block_completed.stat_consumer: a stat starting near
    the 100 cap gains visibly less than one starting at 0."""
    captain, player, team = await _make_team_with_player(db_session)
    high_starter = _make_user()
    db_session.add(high_starter)
    await db_session.flush()
    teams = TeamService(db_session)
    request = await teams.join_by_code(high_starter, team.invite_code)
    await teams.approve_request(captain, request.id)
    db_session.add(UserStat(user_id=high_starter.id, stat_type=TargetStat.INTELLECT, current_value=80.0))
    await db_session.flush()

    event = await _training(db_session, captain, team)
    low_session = await _day(db_session, player, team_event_id=event.id)
    high_session = await _day(db_session, high_starter, team_event_id=event.id)
    diary = TrainingDiaryService(db_session)
    await diary.save_entry(player, low_session.id, None)
    await diary.save_entry(high_starter, high_session.id, None)

    low_gain = await _stat_value(db_session, player.id, TargetStat.INTELLECT)
    high_gain = await _stat_value(db_session, high_starter.id, TargetStat.INTELLECT) - 80.0
    assert 0.0 < high_gain < low_gain <= 100.0
