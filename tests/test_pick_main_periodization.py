"""Phase 9: block-phase difficulty preference in ScheduleService._pick_main.

Verifies:
  1. intensification prefers difficulty>=4, falling back to the full stat
     pool when no candidate meets that bar for a given stat (block isn't
     skipped).
  2. deload prefers difficulty<=2 AND uses its own (smallest) main-block
     count range, 3-4 -- accumulation and intensification each have their
     own wider ranges too (see MAIN_EXERCISE_COUNT_RANGE), this is just the
     one exercised here.
  3. The two priority layers combine in the documented order: block-phase
     difficulty narrows first, SkillTag preference (Phase 7) narrows
     further within that.

Only `random.randint` is monkeypatched (to record/control the count) --
`random.choice` is left real, since each scenario is set up so the
relevant pool has exactly one candidate after filtering, making the pick
deterministic without needing to fake randomness.
"""
import random
import uuid

import pytest

from app.core.training_block import BlockPhase
from app.models.exercise import (
    Exercise,
    ExerciseCategory,
    ExerciseMovementPattern,
    ExerciseTargetStat,
    MovementPattern,
    TargetStat,
    TrainingPhase,
)
from app.models.progress import UserStat
from app.models.skill import Skill, SkillTag, UserSkillPreference
from app.models.user import User
from app.services.schedule_service import ScheduleService

# _pick_main now buckets by movement_pattern, not target_stat (see its
# docstring) -- this file's `random.randint`-only monkeypatch leaves
# `random.shuffle` real, so each scenario still needs every candidate's
# pattern pool to end up a *singleton* after filtering (exactly as the old
# target_stat pool already was here), which is why this maps 1:1 from the
# stat "role" this file already uses rather than sharing one pattern across
# unrelated exercises.
_STAT_TO_PATTERN: dict[TargetStat, MovementPattern] = {
    TargetStat.STRENGTH: MovementPattern.HIP_HINGE,
    TargetStat.AGILITY: MovementPattern.SQUAT,
    TargetStat.INTELLECT: MovementPattern.PUSH,
}


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"periodization_{unique}",
        email=f"periodization_{unique}@example.com",
        password_hash="irrelevant",
        # High enough to clear the User.level difficulty cap entirely (see
        # test_level_difficulty_gate.py) -- this file is about block-phase
        # difficulty preference specifically, which needs difficulty 1/3/5
        # candidates all equally reachable, not about the level gate.
        level=15,
    )


def _make_exercise(name: str, target_stat: TargetStat, difficulty_level: int) -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=name,
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=difficulty_level,
    )


def _stat(exercise: Exercise, target_stat: TargetStat) -> ExerciseTargetStat:
    return ExerciseTargetStat(exercise_id=exercise.id, target_stat=target_stat, order=0)


def _pattern(exercise: Exercise, target_stat: TargetStat) -> ExerciseMovementPattern:
    return ExerciseMovementPattern(
        exercise_id=exercise.id, movement_pattern=_STAT_TO_PATTERN[target_stat]
    )


async def _seed_uncapped_stats(db_session, user: User) -> None:
    """This file is about block-phase difficulty *preference*
    (intensification/deload), not the readiness cap (see
    tests/test_stat_difficulty_gate.py for that) -- so every stat this file
    exercises (strength/agility/intellect) needs to already be in band 5
    (uncapped), same role _make_user's old level=15 played before the
    2026-08-18 switch from User.level to UserStat-based off-ice gating.
    """
    await db_session.flush()  # user itself must be committed before UserStat's FK can insert
    db_session.add_all(
        UserStat(user_id=user.id, stat_type=stat, current_value=90.0)
        for stat in (TargetStat.STRENGTH, TargetStat.AGILITY, TargetStat.INTELLECT)
    )
    await db_session.flush()


async def _seed_candidates(db_session) -> dict[str, Exercise]:
    exercises = {
        "low_strength": _make_exercise("Low-strength", TargetStat.STRENGTH, 1),
        "high_strength": _make_exercise("High-strength", TargetStat.STRENGTH, 5),
        "low_agility": _make_exercise("Low-agility", TargetStat.AGILITY, 1),
        "high_agility": _make_exercise("High-agility", TargetStat.AGILITY, 5),
        "mid_intellect": _make_exercise("Mid-intellect", TargetStat.INTELLECT, 3),
    }
    stats = {
        "low_strength": TargetStat.STRENGTH,
        "high_strength": TargetStat.STRENGTH,
        "low_agility": TargetStat.AGILITY,
        "high_agility": TargetStat.AGILITY,
        "mid_intellect": TargetStat.INTELLECT,
    }
    db_session.add_all(exercises.values())
    db_session.add_all([_stat(exercises[key], stats[key]) for key in exercises])
    db_session.add_all([_pattern(exercises[key], stats[key]) for key in exercises])
    await db_session.flush()
    return exercises


def _isolate_candidates(service: ScheduleService, exercises: dict[str, Exercise]) -> None:
    """Make list_for_assembly return only this test's exercises.

    The real dev DB already has a full Phase 1/7 catalog for
    off_ice/main/bodyweight, which would otherwise mix into the candidate
    pool and make picks non-deterministic here.
    """

    async def fake_list_for_assembly(*, phase, user, category):
        return list(exercises.values())

    service._exercises.list_for_assembly = fake_list_for_assembly


@pytest.mark.asyncio
async def test_intensification_prefers_high_difficulty_with_fallback(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _make_user()
    db_session.add(user)
    await _seed_uncapped_stats(db_session, user)
    exercises = await _seed_candidates(db_session)

    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(random, "randint", lambda a, b: calls.append((a, b)) or b)

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.INTENSIFICATION)

    assert calls == [(4, 5)]  # intensification's own count range
    picked_names = {e.name for e in picked}
    assert picked_names == {
        exercises["high_strength"].name,
        exercises["high_agility"].name,
        # no difficulty>=4 candidate for intellect -> falls back, not skipped
        exercises["mid_intellect"].name,
    }


@pytest.mark.asyncio
async def test_deload_prefers_low_difficulty_and_shrinks_count(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _make_user()
    db_session.add(user)
    exercises = await _seed_candidates(db_session)

    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(random, "randint", lambda a, b: calls.append((a, b)) or b)

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.DELOAD)

    assert calls == [(3, 4)]  # deload's own (smallest) count range
    # fake randint returns the upper bound (4), but only 3 seeded stats have
    # any candidate at all -- count is a ceiling, not a target to pad to.
    assert len(picked) == 3
    picked_names = {e.name for e in picked}
    assert picked_names == {
        exercises["low_strength"].name,
        exercises["low_agility"].name,
        # no difficulty<=2 candidate for intellect -> falls back, not skipped
        exercises["mid_intellect"].name,
    }


@pytest.mark.asyncio
async def test_skilltag_priority_applies_within_the_difficulty_envelope(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Difficulty narrows first, SkillTag narrows further within that pool."""
    user = _make_user()
    db_session.add(user)
    await _seed_uncapped_stats(db_session, user)

    low = _make_exercise("Low-strength", TargetStat.STRENGTH, 1)
    high_untagged = _make_exercise("High-strength-untagged", TargetStat.STRENGTH, 5)
    high_tagged = _make_exercise("High-strength-tagged", TargetStat.STRENGTH, 5)
    db_session.add_all([low, high_untagged, high_tagged])
    db_session.add_all([
        _stat(low, TargetStat.STRENGTH),
        _stat(high_untagged, TargetStat.STRENGTH),
        _stat(high_tagged, TargetStat.STRENGTH),
    ])
    db_session.add_all([
        _pattern(low, TargetStat.STRENGTH),
        _pattern(high_untagged, TargetStat.STRENGTH),
        _pattern(high_tagged, TargetStat.STRENGTH),
    ])
    await db_session.flush()

    skill = Skill(id=uuid.uuid4(), name=f"Test skill {uuid.uuid4().hex[:8]}")
    db_session.add(skill)
    await db_session.flush()
    db_session.add(
        SkillTag(exercise_id=high_tagged.id, skill_id=skill.id, transfer_note="test transfer note")
    )
    db_session.add(UserSkillPreference(user_id=user.id, skill_id=skill.id))
    await db_session.flush()

    monkeypatch.setattr(random, "randint", lambda a, b: b)

    service = ScheduleService(db_session)
    _isolate_candidates(service, {"low": low, "high_untagged": high_untagged, "high_tagged": high_tagged})
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.INTENSIFICATION)

    # difficulty>=4 narrows to {high_untagged, high_tagged} (excludes "Low");
    # SkillTag then narrows that down to {high_tagged} only.
    assert [e.name for e in picked] == [high_tagged.name]
