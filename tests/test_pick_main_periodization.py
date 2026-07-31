"""Phase 9: block-phase difficulty preference in ScheduleService._pick_main.

Verifies:
  1. intensification prefers difficulty>=4, falling back to the full stat
     pool when no candidate meets that bar for a given stat (block isn't
     skipped).
  2. deload prefers difficulty<=2 AND shrinks the main-block count to 1-2
     (the only place phase changes count, not just selection).
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
from app.models.exercise import EquipmentType, Exercise, ExerciseCategory, TargetStat, TrainingPhase
from app.models.skill import Skill, SkillTag, UserSkillPreference
from app.models.user import User
from app.services.schedule_service import ScheduleService


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"periodization_{unique}",
        email=f"periodization_{unique}@example.com",
        password_hash="irrelevant",
        equipment_access=EquipmentType.BODYWEIGHT,
    )


def _make_exercise(name: str, target_stat: TargetStat, difficulty_level: int) -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=name,
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        target_stat=target_stat,
        difficulty_level=difficulty_level,
        equipment_type=EquipmentType.BODYWEIGHT,
    )


async def _seed_candidates(db_session) -> dict[str, Exercise]:
    exercises = {
        "low_strength": _make_exercise("Low-strength", TargetStat.STRENGTH, 1),
        "high_strength": _make_exercise("High-strength", TargetStat.STRENGTH, 5),
        "low_agility": _make_exercise("Low-agility", TargetStat.AGILITY, 1),
        "high_agility": _make_exercise("High-agility", TargetStat.AGILITY, 5),
        "mid_intellect": _make_exercise("Mid-intellect", TargetStat.INTELLECT, 3),
    }
    db_session.add_all(exercises.values())
    await db_session.flush()
    return exercises


def _isolate_candidates(service: ScheduleService, exercises: dict[str, Exercise]) -> None:
    """Make list_for_assembly return only this test's exercises.

    The real dev DB already has a full Phase 1/7 catalog for
    off_ice/main/bodyweight, which would otherwise mix into the candidate
    pool and make picks non-deterministic here.
    """

    async def fake_list_for_assembly(*, phase, equipment_access, category):
        return list(exercises.values())

    service._exercises.list_for_assembly = fake_list_for_assembly


@pytest.mark.asyncio
async def test_intensification_prefers_high_difficulty_with_fallback(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _make_user()
    db_session.add(user)
    exercises = await _seed_candidates(db_session)

    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(random, "randint", lambda a, b: calls.append((a, b)) or b)

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.INTENSIFICATION)

    assert calls == [(2, 3)]  # intensification doesn't change the count range
    by_stat = {e.target_stat: e.name for e in picked}
    assert by_stat[TargetStat.STRENGTH] == exercises["high_strength"].name
    assert by_stat[TargetStat.AGILITY] == exercises["high_agility"].name
    # no difficulty>=4 candidate for intellect -> falls back, not skipped
    assert by_stat[TargetStat.INTELLECT] == exercises["mid_intellect"].name


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

    assert calls == [(1, 2)]  # deload is the one phase that shrinks the count range
    assert len(picked) == 2  # fake randint returns the upper bound (2)
    by_stat = {e.target_stat: e.name for e in picked}
    assert by_stat[TargetStat.STRENGTH] == exercises["low_strength"].name
    assert by_stat[TargetStat.AGILITY] == exercises["low_agility"].name


@pytest.mark.asyncio
async def test_skilltag_priority_applies_within_the_difficulty_envelope(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Difficulty narrows first, SkillTag narrows further within that pool."""
    user = _make_user()
    db_session.add(user)

    low = _make_exercise("Low-strength", TargetStat.STRENGTH, 1)
    high_untagged = _make_exercise("High-strength-untagged", TargetStat.STRENGTH, 5)
    high_tagged = _make_exercise("High-strength-tagged", TargetStat.STRENGTH, 5)
    db_session.add_all([low, high_untagged, high_tagged])
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
