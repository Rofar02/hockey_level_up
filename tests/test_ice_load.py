"""Ice and games on the muscle map (2026-10-09, release plan step 4): the
report charges ICE_SESSION_DOSE x its scale, "Не был" takes it back, no
report means a 24-hour default, and a late report only adds the
difference.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.muscle_load import ICE_SESSION_DOSE, ice_load_scale, recovery_factor
from app.models.exercise import MuscleGroup
from app.models.progress import IceLoadCharge, UserMuscleLoad
from app.models.schedule import DayPlan, DaySessionType, TrainingSession, WeeklyPlan
from app.models.training_diary import IceEffort
from app.models.user import User
from app.schemas.training_diary import DiaryReportIn
from app.services.ice_load_service import charge_default_ice_loads, ice_ended_at
from app.services.training_diary_service import TrainingDiaryService
from tests.dates import utc_today


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"ice_{unique}",
        email=f"ice_{unique}@example.com",
        password_hash="irrelevant",
        timezone="UTC",
    )


async def _ice_day(db_session, user: User, session_type=DaySessionType.ON_ICE, days_ago: int = 0) -> TrainingSession:
    day = utc_today() - timedelta(days=days_ago)
    training_session = TrainingSession(id=uuid.uuid4(), blocks=[])
    day_plan = DayPlan(id=uuid.uuid4(), date=day, session_type=session_type, training_session=training_session)
    db_session.add(WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=day, day_plans=[day_plan]))
    await db_session.flush()
    return training_session


async def _loads(db_session, user: User) -> dict[MuscleGroup, float]:
    rows = (await db_session.scalars(select(UserMuscleLoad).where(UserMuscleLoad.user_id == user.id))).all()
    return {row.muscle_group: row.current_value for row in rows}


def test_scale_follows_length_effort_and_game() -> None:
    assert ice_load_scale(DaySessionType.ON_ICE, 60, IceEffort.NORMAL) == pytest.approx(1.0)
    assert ice_load_scale(DaySessionType.ON_ICE, 120, IceEffort.HARD) == pytest.approx(1.5 * 1.4)
    assert ice_load_scale(DaySessionType.ON_ICE, 30, IceEffort.EASY) == pytest.approx(0.5 * 0.6)
    assert ice_load_scale(DaySessionType.ON_ICE, None, None) == pytest.approx(1.0)
    assert ice_load_scale(DaySessionType.GAME, None, None) == pytest.approx(1.3)


def test_recovery_factor_has_the_map_grace_and_half_life() -> None:
    assert recovery_factor(0) == 1.0
    assert recovery_factor(12) == 1.0
    assert recovery_factor(24) == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_medium_ice_report_loads_glutes_and_quads(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    session = await _ice_day(db_session, user)

    await TrainingDiaryService(db_session).save_entry(
        user, session.id, None, DiaryReportIn(duration_minutes=60, effort=IceEffort.NORMAL)
    )

    loads = await _loads(db_session, user)
    assert loads[MuscleGroup.GLUTES] == pytest.approx(4.5, abs=0.05)
    assert loads[MuscleGroup.QUADS] == pytest.approx(4.5, abs=0.05)
    assert loads[MuscleGroup.SHOULDERS] == pytest.approx(1.0, abs=0.05)
    assert MuscleGroup.CHEST not in loads


@pytest.mark.asyncio
async def test_resubmitted_report_adds_only_the_difference_and_skip_takes_it_back(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    session = await _ice_day(db_session, user)
    diary = TrainingDiaryService(db_session)

    await diary.save_entry(user, session.id, None, DiaryReportIn(duration_minutes=60, effort=IceEffort.NORMAL))
    await diary.save_entry(user, session.id, None, DiaryReportIn(duration_minutes=60, effort=IceEffort.NORMAL))
    assert (await _loads(db_session, user))[MuscleGroup.GLUTES] == pytest.approx(4.5, abs=0.05)

    await diary.save_entry(user, session.id, None, DiaryReportIn(skipped=True))
    assert (await _loads(db_session, user))[MuscleGroup.GLUTES] == pytest.approx(0.0, abs=0.05)


@pytest.mark.asyncio
async def test_game_is_heavier_and_hits_the_cap_when_stacked(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    game = await _ice_day(db_session, user, DaySessionType.GAME)
    from app.models.training_diary import GameResult

    await TrainingDiaryService(db_session).save_entry(
        user, game.id, None, DiaryReportIn(game_result=GameResult.WIN, self_rating=4)
    )
    assert (await _loads(db_session, user))[MuscleGroup.GLUTES] == pytest.approx(4.5 * 1.3, abs=0.05)


@pytest.mark.asyncio
async def test_default_charge_after_24h_once_then_late_report_adds_difference(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    session = await _ice_day(db_session, user, days_ago=2)
    day_plan = await db_session.get(DayPlan, session.day_plan_id)
    ended = await ice_ended_at(db_session, day_plan, "UTC")
    now = ended + timedelta(hours=25)

    await charge_default_ice_loads(db_session, now)
    await charge_default_ice_loads(db_session, now)  # never twice
    charge = (
        await db_session.scalars(select(IceLoadCharge).where(IceLoadCharge.training_session_id == session.id))
    ).one()
    assert charge.scale == pytest.approx(1.0)
    glutes = (await _loads(db_session, user))[MuscleGroup.GLUTES]
    assert glutes == pytest.approx(ICE_SESSION_DOSE[MuscleGroup.GLUTES] * recovery_factor(25), abs=0.05)


@pytest.mark.asyncio
async def test_no_default_for_a_reported_or_too_old_day(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    reported = await _ice_day(db_session, user, days_ago=1)
    await TrainingDiaryService(db_session).save_entry(user, reported.id, None, DiaryReportIn(skipped=True))
    old = await _ice_day(db_session, user, days_ago=4)

    day_plan = await db_session.get(DayPlan, old.day_plan_id)
    ended = await ice_ended_at(db_session, day_plan, "UTC")
    await charge_default_ice_loads(db_session, ended + timedelta(hours=80))

    rows = (await db_session.scalars(select(IceLoadCharge).where(IceLoadCharge.user_id == user.id))).all()
    assert [(row.training_session_id, row.scale) for row in rows] == [(reported.id, 0.0)]
