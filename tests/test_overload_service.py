"""Phase 5 integration: OverloadRepository's real SQL aggregation,
OverloadService.apply_brakes wiring both brakes together, and
_apply_difficulty_gate actually narrowing exercise selection once
user.difficulty_throttle_steps is nonzero.

Same isolation/style conventions as test_stat_difficulty_gate.py/
test_schedule_service_pick_main.py.
"""
import random
import uuid
from datetime import date, timedelta

import pytest

from app.core.overload import SessionSignal
from app.core.training_block import BlockPhase
from app.models.exercise import (
    Exercise,
    ExerciseCategory,
    ExerciseMovementPattern,
    ExerciseTargetStat,
    MovementPattern,
    StimulusType,
    TargetStat,
    TrainingPhase,
)
from app.models.progress import UserStat
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.set_completion import SetCompletion, SetFeedback
from app.models.user import User
from app.repositories.overload_repository import OverloadRepository
from app.services.overload_service import OverloadService
from app.services.schedule_service import ScheduleService


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"overload_{unique}",
        email=f"overload_{unique}@example.com",
        password_hash="irrelevant",
        level=20,  # clears the level cap entirely -- these tests are about throttle, not level
    )


def _make_exercise(
    name: str,
    target_stat: TargetStat,
    difficulty_level: int = 1,
    stimulus_type: StimulusType | None = None,
) -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=name,
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=difficulty_level,
        stimulus_type=stimulus_type,
    )


async def _seed_session(
    db_session,
    user: User,
    *,
    session_date: date,
    feedback_by_exercise: dict[str, SetFeedback],
    stimulus_type_by_exercise: dict[str, StimulusType] | None = None,
) -> TrainingSession:
    """A real off-ice TrainingSession on `session_date`, with one SetCompletion
    (set_number=1) per entry in feedback_by_exercise -- each carrying that
    feedback value, so total_with_feedback == len(feedback_by_exercise).
    stimulus_type_by_exercise (optional, same keys) tags that exercise's own
    stimulus_type -- for POWER_DAY_FEEDBACK_DISCOUNT tests; unset keys stay
    stimulus_type=None (not yet classified), same as every other test here.
    """
    weekly_plan = WeeklyPlan(
        id=uuid.uuid4(),
        user_id=user.id,
        week_start_date=session_date - timedelta(days=session_date.weekday()),
    )
    blocks = []
    set_completions = []
    for i, (exercise_name, feedback) in enumerate(feedback_by_exercise.items()):
        exercise = _make_exercise(
            f"{exercise_name}-{uuid.uuid4().hex[:6]}",
            TargetStat.STRENGTH,
            stimulus_type=(stimulus_type_by_exercise or {}).get(exercise_name),
        )
        db_session.add(exercise)
        await db_session.flush()
        blocks.append(SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=i))
        set_completions.append(
            SetCompletion(
                id=uuid.uuid4(),
                user_id=user.id,
                exercise_id=exercise.id,
                training_session_id=None,  # filled in below once the session id exists
                set_number=1,
                feedback=feedback,
            )
        )

    training_session = TrainingSession(id=uuid.uuid4(), blocks=blocks)
    weekly_plan.day_plans.append(
        DayPlan(
            id=uuid.uuid4(), date=session_date, session_type=DaySessionType.OFF_ICE,
            training_session=training_session,
        )
    )
    db_session.add(weekly_plan)
    await db_session.flush()

    for set_completion in set_completions:
        set_completion.training_session_id = training_session.id
        db_session.add(set_completion)
    await db_session.flush()

    return training_session


@pytest.mark.asyncio
async def test_repository_excludes_sessions_below_feedback_minimum(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    # Only 2 exercises with feedback -- below MIN_FEEDBACK_SETS_FOR_SIGNAL (3).
    await _seed_session(
        db_session, user, session_date=date(2026, 1, 5),
        feedback_by_exercise={"a": SetFeedback.HARD, "b": SetFeedback.HARD},
    )

    repo = OverloadRepository(db_session)
    counts = await repo.list_recent_session_feedback_counts(user.id, limit=10)
    assert counts == []


@pytest.mark.asyncio
async def test_repository_aggregates_hard_max_and_total_correctly(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    await _seed_session(
        db_session, user, session_date=date(2026, 1, 5),
        feedback_by_exercise={
            "a": SetFeedback.HARD,
            "b": SetFeedback.MAX,
            "c": SetFeedback.NORMAL,
            "d": SetFeedback.EASY,
        },
    )

    repo = OverloadRepository(db_session)
    counts = await repo.list_recent_session_feedback_counts(user.id, limit=10)
    assert counts == [(1, 1, 4)]  # (hard_count, max_count, total_with_feedback)


@pytest.mark.asyncio
async def test_repository_orders_newest_session_first(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    older = await _seed_session(
        db_session, user, session_date=date(2026, 1, 5),
        feedback_by_exercise={"a": SetFeedback.EASY, "b": SetFeedback.EASY, "c": SetFeedback.HARD},
    )
    newer = await _seed_session(
        db_session, user, session_date=date(2026, 1, 12),
        feedback_by_exercise={"a": SetFeedback.MAX, "b": SetFeedback.MAX, "c": SetFeedback.MAX},
    )

    repo = OverloadRepository(db_session)
    counts = await repo.list_recent_session_feedback_counts(user.id, limit=10)
    # newer (all max, 3/3) first, older (1 hard of 3) second
    assert counts == [(0, 3, 3), (1, 0, 3)]
    assert older.id != newer.id


@pytest.mark.asyncio
async def test_apply_brakes_cold_start_does_not_engage_or_throttle(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = OverloadService(db_session)
    effective_phase = await service.apply_brakes(user, BlockPhase.ACCUMULATION)

    assert effective_phase == BlockPhase.ACCUMULATION
    assert user.difficulty_throttle_steps == 0


@pytest.mark.asyncio
async def test_apply_brakes_tactical_forces_deload_on_two_overload_sessions(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    # Two sessions in a row, both hard+max ratio >= 0.5 -> overload.
    for i, d in enumerate([date(2026, 1, 5), date(2026, 1, 12)]):
        await _seed_session(
            db_session, user, session_date=d,
            feedback_by_exercise={
                f"a{i}": SetFeedback.HARD, f"b{i}": SetFeedback.HARD, f"c{i}": SetFeedback.MAX,
            },
        )

    service = OverloadService(db_session)
    effective_phase = await service.apply_brakes(user, BlockPhase.ACCUMULATION)

    assert effective_phase == BlockPhase.DELOAD


@pytest.mark.asyncio
async def test_apply_brakes_recovers_once_latest_session_is_ok(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    await _seed_session(
        db_session, user, session_date=date(2026, 1, 5),
        feedback_by_exercise={"a": SetFeedback.HARD, "b": SetFeedback.HARD, "c": SetFeedback.MAX},
    )
    await _seed_session(
        db_session, user, session_date=date(2026, 1, 12),
        feedback_by_exercise={"a": SetFeedback.EASY, "b": SetFeedback.NORMAL, "c": SetFeedback.EASY},
    )

    service = OverloadService(db_session)
    effective_phase = await service.apply_brakes(user, BlockPhase.ACCUMULATION)

    assert effective_phase == BlockPhase.ACCUMULATION


@pytest.mark.asyncio
async def test_apply_brakes_refreshes_structural_throttle_on_the_user(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    # 3 of trailing 5 valid-signal sessions overload -> structural push.
    signals = [SessionSignal.OVERLOAD, SessionSignal.OVERLOAD, SessionSignal.OVERLOAD, SessionSignal.OK, SessionSignal.OK]
    feedback_for = {
        SessionSignal.OVERLOAD: {"a": SetFeedback.MAX, "b": SetFeedback.MAX, "c": SetFeedback.MAX},
        SessionSignal.OK: {"a": SetFeedback.EASY, "b": SetFeedback.EASY, "c": SetFeedback.EASY},
    }
    for i, signal in enumerate(signals):
        await _seed_session(
            db_session, user, session_date=date(2026, 1, 5) + timedelta(weeks=i),
            feedback_by_exercise={f"{k}{i}": v for k, v in feedback_for[signal].items()},
        )

    service = OverloadService(db_session)
    await service.apply_brakes(user, BlockPhase.ACCUMULATION)

    assert user.difficulty_throttle_steps == 1


@pytest.mark.asyncio
async def test_structural_throttle_narrows_exercise_selection(db_session) -> None:
    """End-to-end: a nonzero difficulty_throttle_steps on the user actually
    excludes over-throttle-cap exercises from _pick_main, on top of
    (not instead of) the level cap."""
    user = _make_user()
    user.difficulty_throttle_steps = 1
    db_session.add(user)
    await db_session.flush()
    # Off-ice difficulty is gated by UserStat now, not User.level (see
    # tests/test_stat_difficulty_gate.py) -- strength=90 -> band 5,
    # uncapped by the readiness cap alone, but throttle=1 should still
    # exclude the difficulty-5 candidate on top of that.
    db_session.add(UserStat(user_id=user.id, stat_type=TargetStat.STRENGTH, current_value=90.0))
    await db_session.flush()

    capped_out = _make_exercise("Very-hard", TargetStat.STRENGTH, difficulty_level=5)
    survives = _make_exercise("Hard", TargetStat.STRENGTH, difficulty_level=4)
    db_session.add_all([capped_out, survives])
    db_session.add_all([
        ExerciseTargetStat(exercise_id=capped_out.id, target_stat=TargetStat.STRENGTH, order=0),
        ExerciseTargetStat(exercise_id=survives.id, target_stat=TargetStat.STRENGTH, order=0),
    ])
    # _pick_main now buckets by movement_pattern, not target_stat -- both
    # need to share one so they still compete in the same pool, same intent
    # as sharing TargetStat.STRENGTH above.
    db_session.add_all([
        ExerciseMovementPattern(exercise_id=capped_out.id, movement_pattern=MovementPattern.HIP_HINGE),
        ExerciseMovementPattern(exercise_id=survives.id, movement_pattern=MovementPattern.HIP_HINGE),
    ])
    await db_session.flush()

    service = ScheduleService(db_session)

    async def fake_list_for_assembly(*, phase, user, category):
        return [capped_out, survives]

    service._exercises.list_for_assembly = fake_list_for_assembly
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == ["Hard"]


@pytest.mark.asyncio
async def test_repository_discounts_hard_max_feedback_from_power_exercises(db_session) -> None:
    """Stage 2.4's own plan text (2026-08-20 planning session): a POWER-day
    set subjectively feels harder than a STRENGTH set at the same objective
    load, so its HARD/MAX feedback should count for less toward the
    overload ratio -- see POWER_DAY_FEEDBACK_DISCOUNT."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    await _seed_session(
        db_session, user, session_date=date(2026, 1, 5),
        feedback_by_exercise={"a": SetFeedback.HARD, "b": SetFeedback.HARD, "c": SetFeedback.MAX},
        stimulus_type_by_exercise={"a": StimulusType.POWER, "b": StimulusType.POWER, "c": StimulusType.POWER},
    )

    repo = OverloadRepository(db_session)
    counts = await repo.list_recent_session_feedback_counts(user.id, limit=10)
    # 2 HARD + 1 MAX, all POWER-discounted to 0.5 each -> 1.0 + 0.5 = 1.5.
    assert counts == [(1.0, 0.5, 3)]


@pytest.mark.asyncio
async def test_apply_brakes_power_discount_can_prevent_tactical_engagement(db_session) -> None:
    """Same 2-overload-sessions-in-a-row shape as
    test_apply_brakes_tactical_forces_deload_on_two_overload_sessions, but
    every set is on a POWER exercise -- the discount pulls the ratio below
    _HARD_OR_MAX_OVERLOAD_RATIO (2 HARD/4 = 0.5 undiscounted -> 1.0/4 = 0.25
    discounted), so neither session classifies as overload and the
    tactical brake never engages."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    for i, d in enumerate([date(2026, 1, 5), date(2026, 1, 12)]):
        await _seed_session(
            db_session, user, session_date=d,
            feedback_by_exercise={
                f"a{i}": SetFeedback.HARD, f"b{i}": SetFeedback.HARD,
                f"c{i}": SetFeedback.NORMAL, f"d{i}": SetFeedback.NORMAL,
            },
            stimulus_type_by_exercise={f"a{i}": StimulusType.POWER, f"b{i}": StimulusType.POWER},
        )

    service = OverloadService(db_session)
    effective_phase = await service.apply_brakes(user, BlockPhase.ACCUMULATION)

    assert effective_phase == BlockPhase.ACCUMULATION
