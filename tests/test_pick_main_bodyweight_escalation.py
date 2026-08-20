"""Stage 2.6 (2026-08-20 planning session): bodyweight-progression
escalation, exercised end-to-end through ScheduleService._pick_main.
Ordinary double progression has no weight lever for a tracks_weight=false
exercise (WeightSuggestionService.suggest_weight returns None outright for
those), so RepsSuggestionService.is_stuck_at_ceiling
(test_reps_suggestion_stuck_at_ceiling.py) feeds a same-block pin-break here
instead, biasing the fresh pick toward a harder same-pattern candidate.
Uses MovementPattern.CORE (a role-4/accessory pattern, archetype=None) so
none of role 2-3's day-archetype machinery is in play -- this feature
applies uniformly across all four roles, this file just proves it for the
simplest one.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

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
from app.models.progress import UserStat
from app.models.schedule import BlockPhase, DayPlan, DaySessionType, SessionBlock, TrainingBlock, TrainingSession, WeeklyPlan
from app.models.set_completion import SetCompletion, SetFeedback
from app.models.user import User
from app.services.schedule_service import ScheduleService

TODAY = date(2026, 8, 20)


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"escalate_{unique}",
        email=f"escalate_{unique}@example.com",
        password_hash="irrelevant",
        level=15,
    )


def _make_block(user: User, *, block_number: int = 1, is_macrocycle_deload: bool = False) -> TrainingBlock:
    return TrainingBlock(
        user_id=user.id,
        block_number=block_number,
        phase=BlockPhase.ACCUMULATION,
        is_macrocycle_deload=is_macrocycle_deload,
    )


def _make_core_exercise(name: str, *, difficulty_level: int) -> tuple[Exercise, ExerciseMovementPattern, ExerciseTargetStat]:
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


def _isolate_candidates(service: ScheduleService, exercises: list[Exercise]) -> None:
    async def fake_list_for_assembly(*, phase, user, category, suitable_for_game_day=None):
        return [e for e in exercises if e.phase == phase and e.category == category]

    service._exercises.list_for_assembly = fake_list_for_assembly


async def _get_pin(db_session, user: User) -> UserMovementPatternVariant:
    result = await db_session.execute(
        select(UserMovementPatternVariant).where(
            UserMovementPatternVariant.user_id == user.id,
            UserMovementPatternVariant.category == ExerciseCategory.OFF_ICE,
            UserMovementPatternVariant.movement_pattern == MovementPattern.CORE,
        )
    )
    return result.scalar_one()


async def _make_stuck_history(db_session, user: User, exercise: Exercise) -> None:
    """One prior session where every set hit rep_range_max with good
    feedback -- the is_stuck_at_ceiling condition."""
    blocks = [SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=0)]
    day_plan = DayPlan(
        id=uuid.uuid4(),
        date=date.today(),
        session_type=DaySessionType.OFF_ICE,
        training_session=TrainingSession(id=uuid.uuid4(), blocks=blocks),
    )
    weekly_plan = WeeklyPlan(
        id=uuid.uuid4(), user_id=user.id, week_start_date=date.today(), day_plans=[day_plan]
    )
    db_session.add(weekly_plan)
    await db_session.flush()

    training_session_id = day_plan.training_session.id
    base = datetime.now(timezone.utc)
    for index, reps in enumerate([12, 12, 12], start=1):
        db_session.add(
            SetCompletion(
                id=uuid.uuid4(),
                user_id=user.id,
                exercise_id=exercise.id,
                training_session_id=training_session_id,
                set_number=index,
                reps_completed=reps,
                feedback=SetFeedback.NORMAL if index == 3 else None,
                completed_at=base + timedelta(seconds=index),
            )
        )
    await db_session.flush()


@pytest.mark.asyncio
async def test_stuck_at_ceiling_breaks_a_same_block_pin_for_a_harder_variant(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    easy_ex, easy_pattern, easy_stat = _make_core_exercise("Easy plank", difficulty_level=1)
    hard_ex, hard_pattern, hard_stat = _make_core_exercise("Hard plank", difficulty_level=3)
    db_session.add_all([easy_ex, hard_ex, easy_pattern, hard_pattern, easy_stat, hard_stat])
    db_session.add(UserStat(user_id=user.id, stat_type=TargetStat.STRENGTH, current_value=60.0))
    block = _make_block(user, block_number=1)
    db_session.add(block)
    await db_session.flush()

    db_session.add(
        UserMovementPatternVariant(
            user_id=user.id, category=ExerciseCategory.OFF_ICE, movement_pattern=MovementPattern.CORE,
            archetype=None, exercise_id=easy_ex.id, block_number=1,
        )
    )
    await db_session.flush()
    await _make_stuck_history(db_session, user, easy_ex)

    service = ScheduleService(db_session)
    _isolate_candidates(service, [easy_ex, hard_ex])
    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block, today=TODAY
    )

    assert [e.name for e in picked] == ["Hard plank"]
    pin = await _get_pin(db_session, user)
    assert pin.exercise_id == hard_ex.id
    assert pin.block_number == 1  # rotated mid-block, not at a real boundary


@pytest.mark.asyncio
async def test_no_history_does_not_escalate_and_keeps_the_pin(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    easy_ex, easy_pattern, easy_stat = _make_core_exercise("Easy plank", difficulty_level=1)
    hard_ex, hard_pattern, hard_stat = _make_core_exercise("Hard plank", difficulty_level=3)
    db_session.add_all([easy_ex, hard_ex, easy_pattern, hard_pattern, easy_stat, hard_stat])
    db_session.add(UserStat(user_id=user.id, stat_type=TargetStat.STRENGTH, current_value=60.0))
    block = _make_block(user, block_number=1)
    db_session.add(block)
    await db_session.flush()

    db_session.add(
        UserMovementPatternVariant(
            user_id=user.id, category=ExerciseCategory.OFF_ICE, movement_pattern=MovementPattern.CORE,
            archetype=None, exercise_id=easy_ex.id, block_number=1,
        )
    )
    await db_session.flush()
    # No SetCompletion history at all -- is_stuck_at_ceiling must be False.

    service = ScheduleService(db_session)
    _isolate_candidates(service, [easy_ex, hard_ex])
    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block, today=TODAY
    )

    assert [e.name for e in picked] == ["Easy plank"]
    pin = await _get_pin(db_session, user)
    assert pin.exercise_id == easy_ex.id


@pytest.mark.asyncio
async def test_does_not_escalate_through_a_macrocycle_deload_hold(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    easy_ex, easy_pattern, easy_stat = _make_core_exercise("Easy plank", difficulty_level=1)
    hard_ex, hard_pattern, hard_stat = _make_core_exercise("Hard plank", difficulty_level=3)
    db_session.add_all([easy_ex, hard_ex, easy_pattern, hard_pattern, easy_stat, hard_stat])
    db_session.add(UserStat(user_id=user.id, stat_type=TargetStat.STRENGTH, current_value=60.0))
    # Deload block, pin from a prior (non-deload) block -- hold_through_deload
    # keeps the pin regardless of block_number match.
    block = _make_block(user, block_number=2, is_macrocycle_deload=True)
    db_session.add(block)
    await db_session.flush()

    db_session.add(
        UserMovementPatternVariant(
            user_id=user.id, category=ExerciseCategory.OFF_ICE, movement_pattern=MovementPattern.CORE,
            archetype=None, exercise_id=easy_ex.id, block_number=1,
        )
    )
    await db_session.flush()
    await _make_stuck_history(db_session, user, easy_ex)

    service = ScheduleService(db_session)
    _isolate_candidates(service, [easy_ex, hard_ex])
    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.DELOAD, training_block=block, today=TODAY
    )

    assert [e.name for e in picked] == ["Easy plank"]
    pin = await _get_pin(db_session, user)
    assert pin.exercise_id == easy_ex.id
    assert pin.block_number == 2  # bookmark bumped, variant untouched
