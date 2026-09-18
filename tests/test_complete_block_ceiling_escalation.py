"""2026-09-18 audit round 2 item #1, part C: SessionBlockService.complete_block
wires ScheduleService.escalate_ceiling_variant_for_week into the same
transaction as the block completion itself, and surfaces the result on
SessionBlockRead.ceiling_escalations for the frontend's SessionCompleteModal
card. test_ceiling_escalation_week_patch.py already covers the patch
mechanics directly against ScheduleService; this file covers the wiring:
that complete_block actually calls it, includes the result in its response,
and that everything (block completion + pin move + week patch) commits
together.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.exercise import (
    Exercise,
    ExerciseCategory,
    ExerciseMovementPattern,
    ExerciseTargetStat,
    ExerciseType,
    MovementPattern,
    TargetStat,
    TrainingPhase,
    UserMovementPatternVariant,
)
from app.models.schedule import (
    DayPlan,
    DaySessionType,
    SessionBlock,
    TrainingBlock,
    TrainingSession,
    WeeklyPlan,
)
from app.models.set_completion import SetCompletion, SetFeedback
from app.models.user import User
from app.repositories.exercise_repository import ExerciseRepository
from app.services.session_block_service import SessionBlockService

TODAY = date(2026, 9, 18)


def _isolate_candidates(monkeypatch, exercises: list[Exercise]) -> None:
    """db_session runs against the real dev Postgres DB (see conftest.py),
    which already carries the real seeded catalog -- patched at the class
    level so it also covers the ScheduleService that complete_block
    constructs internally, not just a directly-held instance."""
    async def fake_list_for_assembly(self, *, phase, user, category, suitable_for_game_day=None):
        return [e for e in exercises if e.phase == phase and e.category == category]

    monkeypatch.setattr(ExerciseRepository, "list_for_assembly", fake_list_for_assembly)


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"complete_ceiling_{unique}",
        email=f"complete_ceiling_{unique}@example.com",
        password_hash="irrelevant",
        level=15,
    )


def _make_exercise(
    name: str, *, difficulty_level: int
) -> tuple[Exercise, ExerciseMovementPattern, ExerciseTargetStat]:
    exercise = Exercise(
        id=uuid.uuid4(),
        name=name,
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=difficulty_level,
        exercise_type=ExerciseType.SETS_REPS,
        rep_range_min=8,
        rep_range_max=12,
        tracks_weight=False,
    )
    pattern = ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=MovementPattern.CORE)
    target_stat = ExerciseTargetStat(exercise_id=exercise.id, target_stat=TargetStat.STRENGTH, order=0)
    return exercise, pattern, target_stat


@pytest.mark.asyncio
async def test_complete_block_reports_and_applies_a_ceiling_escalation(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    stuck_ex, stuck_pattern, stuck_stat = _make_exercise("Stuck plank", difficulty_level=2)
    harder_ex, harder_pattern, harder_stat = _make_exercise("Harder plank", difficulty_level=3)
    db_session.add_all([stuck_ex, harder_ex, stuck_pattern, harder_pattern, stuck_stat, harder_stat])
    db_session.add(TrainingBlock(id=uuid.uuid4(), user_id=user.id, block_number=1))
    db_session.add(
        UserMovementPatternVariant(
            user_id=user.id,
            category=ExerciseCategory.OFF_ICE,
            movement_pattern=MovementPattern.CORE,
            archetype=None,
            exercise_id=stuck_ex.id,
            block_number=1,
        )
    )
    await db_session.flush()

    # A prior session's worth of "hit the top, felt fine" sets -- already
    # satisfies is_stuck_at_ceiling before today's block is even completed.
    # A real prior-week TrainingSession, not a bare uuid -- SetCompletion.
    # training_session_id is a real FK.
    prior_week_start = TODAY - timedelta(days=14)
    prior_session = TrainingSession(id=uuid.uuid4(), blocks=[])
    prior_day_plan = DayPlan(
        id=uuid.uuid4(),
        date=prior_week_start,
        session_type=DaySessionType.OFF_ICE,
        training_session=prior_session,
    )
    db_session.add(
        WeeklyPlan(
            id=uuid.uuid4(),
            user_id=user.id,
            week_start_date=prior_week_start,
            day_plans=[prior_day_plan],
        )
    )
    await db_session.flush()

    base = datetime.now(timezone.utc) - timedelta(days=2)
    for index, reps in enumerate([12, 12, 12], start=1):
        db_session.add(
            SetCompletion(
                id=uuid.uuid4(),
                user_id=user.id,
                exercise_id=stuck_ex.id,
                training_session_id=prior_session.id,
                set_number=index,
                reps_completed=reps,
                feedback=SetFeedback.NORMAL if index == 3 else None,
                completed_at=base + timedelta(seconds=index),
            )
        )

    today_block = SessionBlock(
        id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=stuck_ex.id, order=0
    )
    today_plan = DayPlan(
        id=uuid.uuid4(),
        date=TODAY,
        session_type=DaySessionType.OFF_ICE,
        training_session=TrainingSession(id=uuid.uuid4(), blocks=[today_block]),
    )

    future_block = SessionBlock(
        id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=stuck_ex.id, order=0
    )
    future_plan = DayPlan(
        id=uuid.uuid4(),
        date=TODAY + timedelta(days=1),
        session_type=DaySessionType.OFF_ICE,
        training_session=TrainingSession(id=uuid.uuid4(), blocks=[future_block]),
    )

    weekly_plan = WeeklyPlan(
        id=uuid.uuid4(), user_id=user.id, week_start_date=TODAY, day_plans=[today_plan, future_plan]
    )
    db_session.add(weekly_plan)
    await db_session.flush()

    _isolate_candidates(monkeypatch, [stuck_ex, harder_ex])
    result = await SessionBlockService(db_session).complete_block(today_block.id, user)

    assert result.completed_at is not None
    assert [(e.old_exercise_name, e.new_exercise_name) for e in result.ceiling_escalations] == [
        ("Stuck plank", "Harder plank")
    ]

    await db_session.refresh(future_block)
    assert future_block.exercise_id == harder_ex.id
    # The just-completed block itself keeps the exercise it was actually
    # done with -- only untouched future days move.
    await db_session.refresh(today_block)
    assert today_block.exercise_id == stuck_ex.id


@pytest.mark.asyncio
async def test_complete_block_reports_no_escalation_when_not_stuck(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    exercise, pattern, stat = _make_exercise("Plank", difficulty_level=2)
    db_session.add_all([exercise, pattern, stat])
    db_session.add(TrainingBlock(id=uuid.uuid4(), user_id=user.id, block_number=1))
    db_session.add(
        UserMovementPatternVariant(
            user_id=user.id,
            category=ExerciseCategory.OFF_ICE,
            movement_pattern=MovementPattern.CORE,
            archetype=None,
            exercise_id=exercise.id,
            block_number=1,
        )
    )
    await db_session.flush()
    # No SetCompletion history at all -- is_stuck_at_ceiling is False.

    block = SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=0)
    day_plan = DayPlan(
        id=uuid.uuid4(),
        date=TODAY,
        session_type=DaySessionType.OFF_ICE,
        training_session=TrainingSession(id=uuid.uuid4(), blocks=[block]),
    )
    weekly_plan = WeeklyPlan(
        id=uuid.uuid4(), user_id=user.id, week_start_date=TODAY, day_plans=[day_plan]
    )
    db_session.add(weekly_plan)
    await db_session.flush()

    result = await SessionBlockService(db_session).complete_block(block.id, user)

    assert result.ceiling_escalations == []
