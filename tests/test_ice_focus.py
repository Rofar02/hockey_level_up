"""Focus of the day (2026-10-08): the content's integrity, which focus is
picked (game report's "над чем поработать" first, else the lowest on-ice
stat, rotating by date), the per-session endpoint and the report bonus."""
import uuid
from datetime import timedelta

import pytest

from app.core.ice_focus import FOCUS_BY_ID, ICE_FOCUSES, ON_ICE_STATS, WORK_ON_STATS, pick_focus
from app.models.exercise import TargetStat
from app.models.progress import UserStat
from app.models.schedule import DayPlan, DaySessionType, TrainingSession, WeeklyPlan
from app.models.training_diary import FocusResult, GameResult, GameWorkOn, IceEffort
from app.models.user import User
from app.schemas.training_diary import DiaryReportIn
from app.services.ice_focus_service import IceFocusService
from app.services.training_diary_service import DIARY_STAT_REWARDS, TrainingDiaryService, report_base_gains
from tests.dates import utc_today


def test_every_focus_is_well_formed() -> None:
    assert len(FOCUS_BY_ID) == len(ICE_FOCUSES)
    for focus in ICE_FOCUSES:
        assert focus.stat in ON_ICE_STATS
        assert focus.title and len(focus.cues) == 2 and len(focus.id) <= 40
        assert focus.work_on is None or WORK_ON_STATS[focus.work_on] == focus.stat
    for stat in ON_ICE_STATS:
        assert sum(focus.stat == stat for focus in ICE_FOCUSES) >= 5


def test_lowest_on_ice_stat_is_worked_and_the_pick_rotates_by_day() -> None:
    stats = {TargetStat.ON_ICE_SKATING: 40.0, TargetStat.PUCK_HANDLING: 12.0, TargetStat.INTELLECT: 30.0}
    picks = [pick_focus(day, stats, None) for day in range(738000, 738005)]
    assert all(focus.stat == TargetStat.PUCK_HANDLING for focus, _ in picks)
    assert len({focus.id for focus, _ in picks}) > 1
    assert "самый низкий" in picks[0][1]
    # A stat the player never earned counts as 0.
    assert pick_focus(738000, {TargetStat.PUCK_HANDLING: 5.0}, None)[0].stat == TargetStat.ON_ICE_SKATING


def test_game_report_work_on_wins_over_the_lowest_stat() -> None:
    stats = {TargetStat.ON_ICE_SKATING: 50.0, TargetStat.PUCK_HANDLING: 1.0, TargetStat.INTELLECT: 50.0}
    focus, reason = pick_focus(738000, stats, ["defense"])
    assert focus.work_on == "defense"
    assert "игру в защите" in reason


def test_focus_result_adds_to_its_stat() -> None:
    focus = next(f for f in ICE_FOCUSES if f.stat == TargetStat.INTELLECT)
    base = report_base_gains(DaySessionType.ON_ICE, DiaryReportIn(duration_minutes=60, effort=IceEffort.NORMAL))
    done = report_base_gains(
        DaySessionType.ON_ICE,
        DiaryReportIn(duration_minutes=60, effort=IceEffort.NORMAL, focus_id=focus.id, focus_result=FocusResult.DONE),
    )
    unknown = report_base_gains(
        DaySessionType.ON_ICE,
        DiaryReportIn(duration_minutes=60, effort=IceEffort.NORMAL, focus_id="nope", focus_result=FocusResult.DONE),
    )
    assert done[TargetStat.INTELLECT] == pytest.approx(base[TargetStat.INTELLECT] + 0.4)
    assert unknown == base == DIARY_STAT_REWARDS[DaySessionType.ON_ICE]


async def _user_with_days(db_session):
    unique = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), username=f"focus_{unique}", email=f"focus_{unique}@example.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()
    today = utc_today()
    weekly_plan = WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=today - timedelta(days=today.weekday()))
    sessions = {}
    for offset, session_type in ((-2, DaySessionType.GAME), (0, DaySessionType.ON_ICE)):
        training_session = TrainingSession(id=uuid.uuid4(), blocks=[])
        weekly_plan.day_plans.append(
            DayPlan(id=uuid.uuid4(), date=today + timedelta(days=offset), session_type=session_type,
                    training_session=training_session)
        )
        sessions[session_type] = training_session
    db_session.add(weekly_plan)
    db_session.add(UserStat(user_id=user.id, stat_type=TargetStat.ON_ICE_SKATING, current_value=3.0))
    db_session.add(UserStat(user_id=user.id, stat_type=TargetStat.PUCK_HANDLING, current_value=30.0))
    db_session.add(UserStat(user_id=user.id, stat_type=TargetStat.INTELLECT, current_value=30.0))
    await db_session.flush()
    return user, sessions


@pytest.mark.asyncio
async def test_endpoint_follows_stats_then_the_last_game_report(db_session) -> None:
    user, sessions = await _user_with_days(db_session)
    service = IceFocusService(db_session)

    assert await service.focus_for_session(user, sessions[DaySessionType.GAME].id) is None
    before = await service.focus_for_session(user, sessions[DaySessionType.ON_ICE].id)
    assert before.stat == TargetStat.ON_ICE_SKATING

    await TrainingDiaryService(db_session).save_entry(
        user,
        sessions[DaySessionType.GAME].id,
        None,
        DiaryReportIn(game_result=GameResult.LOSS, self_rating=2, work_on=[GameWorkOn.SHOOTING]),
    )
    after = await service.focus_for_session(user, sessions[DaySessionType.ON_ICE].id)
    assert after.stat == TargetStat.PUCK_HANDLING and FOCUS_BY_ID[after.id].work_on == "shooting"


@pytest.mark.asyncio
async def test_report_stores_the_focus_and_pays_its_bonus(db_session) -> None:
    user, sessions = await _user_with_days(db_session)
    focus = await IceFocusService(db_session).focus_for_session(user, sessions[DaySessionType.ON_ICE].id)

    saved = await TrainingDiaryService(db_session).save_entry(
        user,
        sessions[DaySessionType.ON_ICE].id,
        None,
        DiaryReportIn(duration_minutes=60, effort=IceEffort.NORMAL, focus_id=focus.id, focus_result=FocusResult.DONE),
    )

    assert saved.focus_id == focus.id and saved.focus_result == FocusResult.DONE
    assert saved.stat_rewards[focus.stat] > 0
