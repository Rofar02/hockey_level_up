"""«Как прошёл день» (2026-10-10): a gym day's sets, weights and muscles, an
ice day's report, one report for a double day."""
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.models.exercise import Exercise, ExerciseCategory, ExerciseMuscleGroup, MuscleGroup, TrainingPhase
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.set_completion import SetCompletion
from app.models.training_diary import IceEffort
from app.models.user import User
from app.schemas.training_diary import DiaryReportIn
from app.services.day_report_service import DayReportService
from app.services.training_diary_service import TrainingDiaryService
from tests.dates import utc_today


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(id=uuid.uuid4(), username=f"dr_{unique}", email=f"dr_{unique}@example.com", password_hash="x", timezone="UTC")


@pytest.mark.asyncio
async def test_double_day_report_has_sets_weights_muscles_and_the_ice(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    row = Exercise(
        id=uuid.uuid4(), name=f"dr row {uuid.uuid4().hex[:6]}", category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN, difficulty_level=4, tracks_weight=True,
    )
    db_session.add(row)
    await db_session.flush()
    db_session.add(ExerciseMuscleGroup(exercise_id=row.id, muscle_group=MuscleGroup.BACK, weight=1.0))
    today = utc_today()
    now = datetime.now(timezone.utc)
    gym = TrainingSession(
        id=uuid.uuid4(),
        blocks=[SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=row.id, order=0, completed_at=now)],
    )
    ice = TrainingSession(id=uuid.uuid4(), blocks=[])
    days = [
        DayPlan(id=uuid.uuid4(), date=today, session_type=DaySessionType.ON_ICE, time_of_day="evening", training_session=ice),
        DayPlan(id=uuid.uuid4(), date=today, session_type=DaySessionType.OFF_ICE, is_extra=True, time_of_day="morning", training_session=gym),
    ]
    db_session.add(WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=today, day_plans=days))
    await db_session.flush()
    for number, (weight, reps) in enumerate([(20.0, 8), (22.5, 8)], start=1):
        db_session.add(
            SetCompletion(
                user_id=user.id, exercise_id=row.id, training_session_id=gym.id, set_number=number,
                weight_kg=weight, reps_completed=reps, completed_at=now,
            )
        )
    await db_session.flush()
    await TrainingDiaryService(db_session).save_entry(
        user, ice.id, "Хорошо", DiaryReportIn(duration_minutes=75, effort=IceEffort.HARD)
    )

    report = await DayReportService(db_session).report(user, today)

    assert [t.time_of_day for t in report.trainings] == ["morning", "evening"]
    gym_read, ice_read = report.trainings
    assert gym_read.sets_total == 2 and gym_read.tonnage_kg == pytest.approx(20 * 8 + 22.5 * 8)
    assert [(s.weight_kg, s.reps) for s in gym_read.exercises[0].sets] == [(20.0, 8), (22.5, 8)]
    assert ice_read.ice is not None and ice_read.ice.duration_minutes == 75 and ice_read.ice.note == "Хорошо"
    muscles = {m.muscle_group: m.intensity for m in report.muscles}
    assert muscles["back"] > 0  # the gym's rows and the ice both load the back
    assert muscles["quads"] > 0  # the ice only
    assert report.sets_total == 2


@pytest.mark.asyncio
async def test_no_plan_no_report(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    with pytest.raises(HTTPException) as exc:
        await DayReportService(db_session).report(user, utc_today())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_stats_follow_the_days_rewards_not_the_record_date(db_session) -> None:
    """Review 2026-10-11, 5.1: yesterday's ice reported this morning moves
    yesterday's stats, «до» starts from 0, a reward of something else that
    day isn't counted."""
    from datetime import timedelta

    from app.models.exercise import TargetStat
    from app.models.progress import StatHistory, UserStat

    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    yesterday = utc_today() - timedelta(days=1)
    ice = TrainingSession(id=uuid.uuid4(), blocks=[])
    db_session.add(
        WeeklyPlan(
            id=uuid.uuid4(), user_id=user.id, week_start_date=yesterday,
            day_plans=[DayPlan(id=uuid.uuid4(), date=yesterday, session_type=DaySessionType.ON_ICE, training_session=ice)],
        )
    )
    db_session.add(
        StatHistory(
            user_id=user.id, stat_type=TargetStat.INTELLECT, value=5.0, reason="team_bonus",
            recorded_at=datetime.combine(yesterday, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=12),
        )
    )
    db_session.add(UserStat(user_id=user.id, stat_type=TargetStat.INTELLECT, current_value=5.0))
    await db_session.flush()
    await TrainingDiaryService(db_session).save_entry(
        user, ice.id, None, DiaryReportIn(duration_minutes=60, effort=IceEffort.NORMAL)
    )

    stats = {s.stat: s for s in (await DayReportService(db_session).report(user, yesterday)).stats}

    assert stats["on_ice_skating"].before == 0 and stats["on_ice_skating"].after > 0
    assert stats["intellect"].before == 5.0 and stats["intellect"].after > 5.0  # the ice's own gain only
