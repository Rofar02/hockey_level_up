"""2026-09-18 audit round 2 item #1 -- the week-patch half of ceiling
escalation, ScheduleService.escalate_ceiling_variant_for_week.
test_pick_main_bodyweight_escalation.py already covers is_stuck_at_ceiling
breaking a *fresh* pick at assembly time; this file covers the other half
the audit called out: create_weekly_plan builds every day of the week up
front, so an already-generated-but-not-yet-started day needs its own
SessionBlock rows patched directly, not just the pin. Scoped to the patch
mechanics (which rows move, which don't, what's reported back) -- the
difficulty tiering itself is covered by test_tier_by_escalated_difficulty.py.
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
from app.services.schedule_service import ScheduleService

TODAY = date(2026, 9, 18)  # a Friday -- irrelevant, just fixed for determinism


def _isolate_candidates(monkeypatch, exercises: list[Exercise]) -> None:
    """Same reasoning as test_pick_main_bodyweight_escalation.py's own
    helper: db_session runs against the real dev Postgres DB (see
    conftest.py), which already carries the real seeded catalog --
    list_for_assembly would otherwise hand _pick_ceiling_escalation_candidate
    hundreds of unrelated real exercises alongside this test's own fixtures.
    Patched at the class level (not on one instance) so it also covers the
    ScheduleService that SessionBlockService.complete_block constructs
    internally.
    """
    async def fake_list_for_assembly(self, *, phase, user, category, suitable_for_game_day=None):
        return [e for e in exercises if e.phase == phase and e.category == category]

    monkeypatch.setattr(ExerciseRepository, "list_for_assembly", fake_list_for_assembly)


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"ceiling_{unique}",
        email=f"ceiling_{unique}@example.com",
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


def _make_block(user: User) -> TrainingBlock:
    return TrainingBlock(id=uuid.uuid4(), user_id=user.id, block_number=1)


def _make_pin(user: User, exercise: Exercise) -> UserMovementPatternVariant:
    return UserMovementPatternVariant(
        user_id=user.id,
        category=ExerciseCategory.OFF_ICE,
        movement_pattern=MovementPattern.CORE,
        archetype=None,
        exercise_id=exercise.id,
        block_number=1,
    )


async def _add_stuck_history(db_session, user: User, exercise: Exercise) -> None:
    """Three sets, all at rep_range_max, good feedback on the last one --
    RepsSuggestionService.is_stuck_at_ceiling's condition. Logged against a
    real prior-week TrainingSession (SetCompletion.training_session_id is a
    real FK) rather than today's own week, so it can't collide with a
    test's own current-week WeeklyPlan fixture.
    """
    prior_week_start = TODAY - timedelta(days=14)
    training_session = TrainingSession(id=uuid.uuid4(), blocks=[])
    day_plan = DayPlan(
        id=uuid.uuid4(),
        date=prior_week_start,
        session_type=DaySessionType.OFF_ICE,
        training_session=training_session,
    )
    weekly_plan = WeeklyPlan(
        id=uuid.uuid4(), user_id=user.id, week_start_date=prior_week_start, day_plans=[day_plan]
    )
    db_session.add(weekly_plan)
    await db_session.flush()

    base = datetime.now(timezone.utc)
    for index, reps in enumerate([12, 12, 12], start=1):
        db_session.add(
            SetCompletion(
                id=uuid.uuid4(),
                user_id=user.id,
                exercise_id=exercise.id,
                training_session_id=training_session.id,
                set_number=index,
                reps_completed=reps,
                feedback=SetFeedback.NORMAL if index == 3 else None,
                completed_at=base + timedelta(seconds=index),
            )
        )
    await db_session.flush()


async def _get_pin(db_session, user: User) -> UserMovementPatternVariant:
    result = await db_session.execute(
        select(UserMovementPatternVariant).where(
            UserMovementPatternVariant.user_id == user.id,
            UserMovementPatternVariant.category == ExerciseCategory.OFF_ICE,
            UserMovementPatternVariant.movement_pattern == MovementPattern.CORE,
        )
    )
    return result.scalar_one()


@pytest.mark.asyncio
async def test_escalates_pin_and_patches_untouched_future_day_only(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    stuck_ex, stuck_pattern, stuck_stat = _make_exercise("Stuck push-up", difficulty_level=2)
    harder_ex, harder_pattern, harder_stat = _make_exercise("Harder push-up", difficulty_level=3)
    db_session.add_all([stuck_ex, harder_ex, stuck_pattern, harder_pattern, stuck_stat, harder_stat])
    db_session.add(_make_block(user))
    db_session.add(_make_pin(user, stuck_ex))
    await db_session.flush()

    # Today's own session -- already completed, holds the stuck history.
    today_session = TrainingSession(
        id=uuid.uuid4(),
        blocks=[
            SessionBlock(
                id=uuid.uuid4(),
                phase=TrainingPhase.MAIN,
                exercise_id=stuck_ex.id,
                order=0,
                completed_at=datetime.now(timezone.utc),
            )
        ],
    )
    today_plan = DayPlan(
        id=uuid.uuid4(), date=TODAY, session_type=DaySessionType.OFF_ICE, training_session=today_session
    )

    # Tomorrow: not started at all -- must be patched.
    future_block = SessionBlock(
        id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=stuck_ex.id, order=0
    )
    future_session = TrainingSession(id=uuid.uuid4(), blocks=[future_block])
    future_plan = DayPlan(
        id=uuid.uuid4(),
        date=TODAY + timedelta(days=1),
        session_type=DaySessionType.OFF_ICE,
        training_session=future_session,
    )

    weekly_plan = WeeklyPlan(
        id=uuid.uuid4(), user_id=user.id, week_start_date=TODAY, day_plans=[today_plan, future_plan]
    )
    db_session.add(weekly_plan)
    await db_session.flush()
    await _add_stuck_history(db_session, user, stuck_ex)

    _isolate_candidates(monkeypatch, [stuck_ex, harder_ex])
    service = ScheduleService(db_session)
    result = await service.escalate_ceiling_variant_for_week(user, stuck_ex)

    assert [(r.old_exercise_name, r.new_exercise_name) for r in result] == [
        ("Stuck push-up", "Harder push-up")
    ]

    pin = await _get_pin(db_session, user)
    assert pin.exercise_id == harder_ex.id

    await db_session.refresh(future_block)
    assert future_block.exercise_id == harder_ex.id

    # Today's already-completed block is untouched.
    today_block = today_session.blocks[0]
    await db_session.refresh(today_block)
    assert today_block.exercise_id == stuck_ex.id


@pytest.mark.asyncio
async def test_does_not_patch_a_future_day_that_has_already_started(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    stuck_ex, stuck_pattern, stuck_stat = _make_exercise("Stuck push-up", difficulty_level=2)
    harder_ex, harder_pattern, harder_stat = _make_exercise("Harder push-up", difficulty_level=3)
    db_session.add_all([stuck_ex, harder_ex, stuck_pattern, harder_pattern, stuck_stat, harder_stat])
    db_session.add(_make_block(user))
    db_session.add(_make_pin(user, stuck_ex))
    await db_session.flush()

    today_session_id = uuid.uuid4()
    today_plan = DayPlan(
        id=uuid.uuid4(),
        date=TODAY,
        session_type=DaySessionType.OFF_ICE,
        training_session=TrainingSession(
            id=today_session_id,
            blocks=[
                SessionBlock(
                    id=uuid.uuid4(),
                    phase=TrainingPhase.MAIN,
                    exercise_id=stuck_ex.id,
                    order=0,
                    completed_at=datetime.now(timezone.utc),
                )
            ],
        ),
    )

    # A future day, but its WARMUP block is already done -- the MAIN slot
    # holding the stuck exercise is untouched, but the day as a whole has
    # already started, so it must be left alone entirely.
    started_main_block = SessionBlock(
        id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=stuck_ex.id, order=1
    )
    started_plan = DayPlan(
        id=uuid.uuid4(),
        date=TODAY + timedelta(days=1),
        session_type=DaySessionType.OFF_ICE,
        training_session=TrainingSession(
            id=uuid.uuid4(),
            blocks=[
                SessionBlock(
                    id=uuid.uuid4(),
                    phase=TrainingPhase.WARMUP,
                    exercise_id=stuck_ex.id,
                    order=0,
                    completed_at=datetime.now(timezone.utc),
                ),
                started_main_block,
            ],
        ),
    )

    weekly_plan = WeeklyPlan(
        id=uuid.uuid4(), user_id=user.id, week_start_date=TODAY, day_plans=[today_plan, started_plan]
    )
    db_session.add(weekly_plan)
    await db_session.flush()
    await _add_stuck_history(db_session, user, stuck_ex)

    _isolate_candidates(monkeypatch, [stuck_ex, harder_ex])
    service = ScheduleService(db_session)
    result = await service.escalate_ceiling_variant_for_week(user, stuck_ex)

    assert result == []
    pin = await _get_pin(db_session, user)
    assert pin.exercise_id == stuck_ex.id
    await db_session.refresh(started_main_block)
    assert started_main_block.exercise_id == stuck_ex.id


@pytest.mark.asyncio
async def test_no_escalation_when_not_stuck(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    stuck_ex, stuck_pattern, stuck_stat = _make_exercise("Push-up", difficulty_level=2)
    harder_ex, harder_pattern, harder_stat = _make_exercise("Harder push-up", difficulty_level=3)
    db_session.add_all([stuck_ex, harder_ex, stuck_pattern, harder_pattern, stuck_stat, harder_stat])
    db_session.add(_make_block(user))
    db_session.add(_make_pin(user, stuck_ex))
    await db_session.flush()
    # No SetCompletion history at all -- is_stuck_at_ceiling is False.

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
        id=uuid.uuid4(), user_id=user.id, week_start_date=TODAY, day_plans=[future_plan]
    )
    db_session.add(weekly_plan)
    await db_session.flush()

    service = ScheduleService(db_session)
    result = await service.escalate_ceiling_variant_for_week(user, stuck_ex)

    assert result == []
    await db_session.refresh(future_block)
    assert future_block.exercise_id == stuck_ex.id


@pytest.mark.asyncio
async def test_no_escalation_for_a_tracks_weight_exercise(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    stuck_ex, stuck_pattern, stuck_stat = _make_exercise("Bench press", difficulty_level=2)
    stuck_ex.tracks_weight = True
    db_session.add_all([stuck_ex, stuck_pattern, stuck_stat])
    db_session.add(_make_block(user))
    db_session.add(_make_pin(user, stuck_ex))
    await db_session.flush()

    await _add_stuck_history(db_session, user, stuck_ex)

    service = ScheduleService(db_session)
    result = await service.escalate_ceiling_variant_for_week(user, stuck_ex)

    assert result == []


@pytest.mark.asyncio
async def test_no_pin_means_no_escalation(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    stuck_ex, stuck_pattern, stuck_stat = _make_exercise("Push-up", difficulty_level=2)
    db_session.add_all([stuck_ex, stuck_pattern, stuck_stat])
    db_session.add(_make_block(user))
    # Deliberately no UserMovementPatternVariant row for this exercise.
    await db_session.flush()

    await _add_stuck_history(db_session, user, stuck_ex)

    service = ScheduleService(db_session)
    result = await service.escalate_ceiling_variant_for_week(user, stuck_ex)

    assert result == []
