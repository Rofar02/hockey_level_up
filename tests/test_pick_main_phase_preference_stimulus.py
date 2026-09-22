"""Phase/escalation difficulty narrowing must not drop the day archetype's own
stimulus (2026-09-21, found by a 52-week simulation against a copy of prod).

Two steps in ScheduleService._pick_main's pick_for_pattern used to narrow the
WHOLE pattern pool by difficulty *before* the archetype's stimulus preference
was applied:

  B1. The block-phase preference (INTENSIFICATION keeps difficulty >= 4,
      DELOAD keeps <= 2). A cell whose genuine-stimulus exercises all sit
      below the floor (e.g. push/POWER tops out at difficulty 3) lost every
      one of them and got a strength exercise instead -- ~44% of all
      "Day-archetype fallback" warnings in the simulated year.
  B3. Bodyweight-escalation tiering ("strictly harder than the exercise
      that's stuck at its rep ceiling"), which likewise picked the harder
      exercise from ANY stimulus.

Both now narrow within the wanted stimulus first. These tests fail on the
old ordering and pass on the new one.
"""
import random
import uuid
from datetime import date, timedelta

import pytest

from app.models.exercise import (
    Exercise,
    ExerciseCategory,
    ExerciseMovementPattern,
    ExerciseTargetStat,
    MovementPattern,
    StimulusType,
    TargetStat,
    TrainingPhase,
    UserMovementPatternVariant,
)
from app.models.progress import UserStat
from app.models.schedule import BlockPhase, TrainingBlock
from app.models.user import User
from app.services.schedule_service import ScheduleService

TODAY = date(2026, 9, 21)


@pytest.fixture(autouse=True)
def deterministic_random(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(random, "choice", lambda pool: sorted(pool, key=lambda e: e.name)[0])
    monkeypatch.setattr(random, "shuffle", lambda seq: None)


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"phasepref_{unique}",
        email=f"phasepref_{unique}@example.com",
        password_hash="irrelevant",
        level=15,
    )


def _make_squat(name: str, stimulus_type: StimulusType, difficulty_level: int) -> tuple[
    Exercise, ExerciseMovementPattern, ExerciseTargetStat
]:
    exercise = Exercise(
        id=uuid.uuid4(),
        name=name,
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=difficulty_level,
        stimulus_type=stimulus_type,
        tracks_weight=False,
    )
    return (
        exercise,
        ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=MovementPattern.SQUAT),
        # A classified primary stat, plus the UserStat below, keeps the readiness
        # cap out of this file's way (an unclassified exercise gets cap 1).
        ExerciseTargetStat(exercise_id=exercise.id, target_stat=TargetStat.STRENGTH, order=0),
    )


def _isolate_candidates(service: ScheduleService, exercises: list[Exercise]) -> None:
    async def fake_list_for_assembly(*, phase, user, category, suitable_for_game_day=None):
        return [e for e in exercises if e.phase == phase and e.category == category]

    service._exercises.list_for_assembly = fake_list_for_assembly


async def _seed(db_session, user: User, rows) -> list[Exercise]:
    db_session.add(user)
    await db_session.flush()
    db_session.add_all([e for e, _, _ in rows])
    db_session.add_all([p for _, p, _ in rows])
    db_session.add_all([s for _, _, s in rows])
    db_session.add(UserStat(user_id=user.id, stat_type=TargetStat.STRENGTH, current_value=90.0))
    await db_session.flush()
    return [e for e, _, _ in rows]


def _pin(user: User, archetype: StimulusType, exercise: Exercise, *, days_ago: int, times_chosen: int = 0):
    return UserMovementPatternVariant(
        user_id=user.id,
        category=ExerciseCategory.OFF_ICE,
        movement_pattern=MovementPattern.SQUAT,
        archetype=archetype,
        exercise_id=exercise.id,
        block_number=1,
        last_chosen_at=TODAY - timedelta(days=days_ago),
        times_chosen=times_chosen,
    )


@pytest.mark.asyncio
async def test_intensification_keeps_the_archetypes_stimulus_when_it_has_nothing_at_the_floor(
    db_session,
) -> None:
    """B1: today's archetype is POWER, whose only exercise is difficulty 3 --
    below INTENSIFICATION's floor of 4. The strength exercise at difficulty 4
    used to win because the phase preference wiped the POWER one first."""
    user = _make_user()
    power, strength = (
        _make_squat("Power-d3", StimulusType.POWER, 3),
        _make_squat("Strength-d4", StimulusType.STRENGTH, 4),
    )
    exercises = await _seed(db_session, user, [power, strength])
    block = TrainingBlock(user_id=user.id, block_number=1, phase=BlockPhase.INTENSIFICATION)
    db_session.add(block)
    await db_session.flush()
    power_ex, strength_ex = exercises
    # STRENGTH and SKILL were trained recently, POWER never -> POWER is due.
    db_session.add_all([
        _pin(user, StimulusType.STRENGTH, strength_ex, days_ago=1),
        _pin(user, StimulusType.SKILL, strength_ex, days_ago=2),
    ])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.INTENSIFICATION, training_block=block, today=TODAY
    )

    assert "Power-d3" in [e.name for e in picked]
    assert "Strength-d4" not in [e.name for e in picked]


@pytest.mark.asyncio
async def test_escalation_stays_within_the_archetypes_stimulus(db_session) -> None:
    """B3: the pinned SKILL exercise is stuck at its rep ceiling. "Strictly
    harder" used to be judged across every stimulus, so the strength
    exercise at difficulty 3 won; the only SKILL alternative (an easier one)
    should be used instead of leaving the archetype."""
    user = _make_user()
    rows = [
        _make_squat("Skill-A-d2-pinned", StimulusType.SKILL, 2),
        _make_squat("Skill-B-d1", StimulusType.SKILL, 1),
        _make_squat("Strength-C-d2", StimulusType.STRENGTH, 2),
        _make_squat("Strength-D-d3", StimulusType.STRENGTH, 3),
    ]
    exercises = await _seed(db_session, user, rows)
    skill_a, _skill_b, strength_c, _strength_d = exercises
    block = TrainingBlock(user_id=user.id, block_number=1, phase=BlockPhase.ACCUMULATION)
    db_session.add(block)
    await db_session.flush()
    # SKILL is the stalest archetype, and its pin is in this block -> reused
    # unless escalation breaks it.
    db_session.add_all([
        _pin(user, StimulusType.SKILL, skill_a, days_ago=10, times_chosen=1),
        _pin(user, StimulusType.STRENGTH, strength_c, days_ago=1),
        _pin(user, StimulusType.POWER, strength_c, days_ago=2),
    ])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)

    async def always_stuck(user, exercise):
        return exercise.id == skill_a.id

    service._reps_suggestions.is_stuck_at_ceiling = always_stuck
    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block, today=TODAY
    )

    assert "Skill-B-d1" in [e.name for e in picked]
    assert "Strength-D-d3" not in [e.name for e in picked]


def _ex(name: str, stimulus_type: StimulusType, difficulty_level: int) -> Exercise:
    return Exercise(id=uuid.uuid4(), name=name, stimulus_type=stimulus_type, difficulty_level=difficulty_level)


def test_phase_preference_helper_keeps_wanted_stimulus_the_predicate_would_drop() -> None:
    power_d3 = _ex("power-d3", StimulusType.POWER, 3)
    strength_d4 = _ex("strength-d4", StimulusType.STRENGTH, 4)

    result = ScheduleService._prefer_by_phase_difficulty(
        [power_d3, strength_d4], lambda e: e.difficulty_level >= 4, frozenset({StimulusType.POWER})
    )

    assert result == [power_d3]


def test_phase_preference_helper_still_narrows_when_the_wanted_stimulus_survives() -> None:
    power_d2 = _ex("power-d2", StimulusType.POWER, 2)
    power_d4 = _ex("power-d4", StimulusType.POWER, 4)
    strength_d4 = _ex("strength-d4", StimulusType.STRENGTH, 4)

    result = ScheduleService._prefer_by_phase_difficulty(
        [power_d2, power_d4, strength_d4], lambda e: e.difficulty_level >= 4, frozenset({StimulusType.POWER})
    )

    assert result == [power_d4, strength_d4]  # unchanged from the old behaviour: only the >=4 ones


def test_phase_preference_helper_matches_old_behaviour_without_a_stimulus_preference() -> None:
    low = _ex("low", StimulusType.STRENGTH, 1)
    high = _ex("high", StimulusType.POWER, 5)

    assert ScheduleService._prefer_by_phase_difficulty(
        [low, high], lambda e: e.difficulty_level >= 4, None
    ) == [high]


def test_phase_preference_helper_falls_back_to_the_pool_when_nothing_matches() -> None:
    low = _ex("low", StimulusType.STRENGTH, 1)
    also_low = _ex("also-low", StimulusType.POWER, 2)

    assert ScheduleService._prefer_by_phase_difficulty(
        [low, also_low], lambda e: e.difficulty_level >= 4, frozenset({StimulusType.SKILL})
    ) == [low, also_low]


def test_phase_preference_helper_deload_ceiling_keeps_wanted_stimulus_too() -> None:
    skill_d3 = _ex("skill-d3", StimulusType.SKILL, 3)
    strength_d1 = _ex("strength-d1", StimulusType.STRENGTH, 1)

    result = ScheduleService._prefer_by_phase_difficulty(
        [skill_d3, strength_d1], lambda e: e.difficulty_level <= 2, frozenset({StimulusType.SKILL})
    )

    assert result == [skill_d3]
