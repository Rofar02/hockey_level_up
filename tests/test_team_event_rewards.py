"""Team-training rewards through the personal diary's report (2026-10-08):
the first rewarded report for a day a TRAINING event took over
(DayPlan.team_event_id) earns TEAM_TRAINING_XP_BONUS in place of the
ordinary report XP, and the stats come from the report alone -- one reward
per day, not two. Re-submitting never re-grants; "Не был" earns nothing; a
game day, an ordinary ice day or a player who left the team get the
ordinary report XP; a player already rewarded through the old team diary
isn't given the team XP again.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.models.exercise import TargetStat
from app.models.progress import StatHistory, UserStat
from app.models.schedule import (
    DayPlan,
    DaySessionType,
    TrainingBlock,
    TrainingSession,
    WeeklyPlan,
)
from app.models.team import TeamMembership
from app.models.team_event import TeamEventType
from app.models.user import User
from app.repositories.team_event_repository import TeamEventRepository
from app.services.team_event_service import TEAM_TRAINING_XP_BONUS, TeamEventService
from app.services.team_service import TeamService
from app.models.training_diary import GameResult, IceEffort
from app.schemas.training_diary import DiaryReportIn
from app.services.training_diary_service import REPORT_XP, TrainingDiaryService
from tests.dates import utc_today


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
    monday = utc_today() - timedelta(days=utc_today().weekday()) + timedelta(weeks=block_number - 1)
    block = TrainingBlock(id=uuid.uuid4(), user_id=user.id, block_number=block_number, phase_started_at=monday)
    db_session.add(block)
    await db_session.flush()
    session = TrainingSession(id=uuid.uuid4(), blocks=[])
    weekly_plan = WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=monday, training_block_id=block.id)
    weekly_plan.day_plans.append(
        DayPlan(
            id=uuid.uuid4(),
            date=utc_today(),
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


ICE_REPORT = DiaryReportIn(duration_minutes=60, effort=IceEffort.NORMAL)
GAME_REPORT = DiaryReportIn(game_result=GameResult.WIN, self_rating=4)


@pytest.mark.asyncio
async def test_team_training_report_earns_team_xp_and_one_set_of_stats(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    event = await _training(db_session, captain, team)
    session = await _day(db_session, player, team_event_id=event.id)
    diary = TrainingDiaryService(db_session)

    saved = await diary.save_entry(player, session.id, "Хорошая тренировка", ICE_REPORT)

    assert saved.xp_reward == TEAM_TRAINING_XP_BONUS
    await db_session.refresh(player)
    assert player.xp == TEAM_TRAINING_XP_BONUS
    for stat_type in (TargetStat.INTELLECT, TargetStat.PUCK_HANDLING, TargetStat.ON_ICE_SKATING):
        assert await _stat_value(db_session, player.id, stat_type) > 0
    history = (await db_session.execute(select(StatHistory).where(StatHistory.user_id == player.id))).scalars().all()
    assert len(history) == 3  # the report's three stats, no separate team credit

    # A sent report is final (2026-10-10) -- re-submitting is refused and
    # nothing is granted twice.
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await diary.save_entry(player, session.id, "Отредактированная заметка", ICE_REPORT)
    assert exc.value.status_code == 409
    await db_session.refresh(player)
    assert player.xp == TEAM_TRAINING_XP_BONUS


@pytest.mark.asyncio
async def test_note_or_skip_alone_grants_nothing(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    event = await _training(db_session, captain, team)
    session = await _day(db_session, player, team_event_id=event.id)
    diary = TrainingDiaryService(db_session)

    await diary.save_entry(player, session.id, None)
    await diary.save_entry(player, session.id, None, DiaryReportIn(skipped=True))

    await db_session.refresh(player)
    assert player.xp == 0


@pytest.mark.asyncio
async def test_the_coach_is_rewarded_the_same_way(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    event = await _training(db_session, captain, team)
    session = await _day(db_session, captain, team_event_id=event.id)

    await TrainingDiaryService(db_session).save_entry(captain, session.id, "Провёл тренировку", ICE_REPORT)

    await db_session.refresh(captain)
    assert captain.xp == TEAM_TRAINING_XP_BONUS


@pytest.mark.asyncio
async def test_game_day_and_ordinary_ice_day_earn_the_ordinary_report_xp(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    game = await TeamEventService(db_session).create_event(
        captain, team.id, TeamEventType.GAME, _future(), "Rival HC"
    )
    game_day = await _day(db_session, player, DaySessionType.GAME, team_event_id=game.id)
    ordinary_ice = await _day(db_session, player, DaySessionType.ON_ICE, block_number=2)
    diary = TrainingDiaryService(db_session)

    await diary.save_entry(player, game_day.id, "Игра прошла хорошо", GAME_REPORT)
    await diary.save_entry(player, ordinary_ice.id, "Свой лёд", ICE_REPORT)

    await db_session.refresh(player)
    assert player.xp == REPORT_XP[DaySessionType.GAME] + REPORT_XP[DaySessionType.ON_ICE]


@pytest.mark.asyncio
async def test_player_who_left_the_team_gets_no_team_xp(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    event = await _training(db_session, captain, team)
    session = await _day(db_session, player, team_event_id=event.id)
    await db_session.execute(delete(TeamMembership).where(TeamMembership.user_id == player.id))
    await db_session.flush()

    await TrainingDiaryService(db_session).save_entry(player, session.id, "Уже не в команде", ICE_REPORT)

    await db_session.refresh(player)
    assert player.xp == REPORT_XP[DaySessionType.ON_ICE]


@pytest.mark.asyncio
async def test_already_rewarded_through_the_old_team_diary_gets_no_team_xp_again(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    event = await _training(db_session, captain, team)
    # The old team diary tab left this marker (and already paid out).
    await TeamEventRepository(db_session).create_diary_entry(event.id, player.id, "старая запись")
    session = await _day(db_session, player, team_event_id=event.id)

    await TrainingDiaryService(db_session).save_entry(player, session.id, "Новая запись", ICE_REPORT)

    await db_session.refresh(player)
    assert player.xp == REPORT_XP[DaySessionType.ON_ICE]


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
    await diary.save_entry(player, low_session.id, None, ICE_REPORT)
    await diary.save_entry(high_starter, high_session.id, None, ICE_REPORT)

    low_gain = await _stat_value(db_session, player.id, TargetStat.INTELLECT)
    high_gain = await _stat_value(db_session, high_starter.id, TargetStat.INTELLECT) - 80.0
    assert 0.0 < high_gain < low_gain <= 100.0
