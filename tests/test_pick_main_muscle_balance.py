"""_apply_muscle_balance: soft push/pull/legs/core variety rule layered on
top of ScheduleService._pick_main's existing level/difficulty/SkillTag
priority chain (see test_schedule_service_pick_main.py for those).

Verifies the four behaviors called out for this change:
  1. A third main-block pick in a row sharing the same muscle_group is
     replaced by a same-stat alternative from a different group, when one
     exists in the candidate pool.
  2. With no such alternative, the streak-violating exercise is still
     picked rather than leaving the slot empty.
  3. on_ice exercises (muscle_group always None for that category) never
     trigger or block on the rule -- _pick_main(ON_ICE, ...) is unaffected.
  4. SkillTag priority still wins a real conflict: muscle balance only
     narrows within the tag-priority pool, never reaches back out to an
     untagged alternative from a different group.

`random.choice`/`random.randint` are monkeypatched exactly as in
test_schedule_service_pick_main.py so each stat's candidate pool can be
asserted precisely.
"""
import random
import uuid

import pytest

from app.core.training_block import BlockPhase
from app.models.exercise import (
    EquipmentType,
    Exercise,
    ExerciseCategory,
    ExerciseTargetStat,
    MuscleGroup,
    TargetStat,
    TrainingPhase,
)
from app.models.skill import Skill, SkillTag, UserSkillPreference
from app.models.user import User
from app.services.schedule_service import ScheduleService


@pytest.fixture(autouse=True)
def deterministic_random(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(random, "randint", lambda a, b: 3)
    monkeypatch.setattr(random, "choice", lambda pool: sorted(pool, key=lambda e: e.name)[0])


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"user_{unique}",
        email=f"user_{unique}@example.com",
        password_hash="irrelevant",
        equipment_access=EquipmentType.BODYWEIGHT,
    )


def _make_exercise(
    name: str,
    target_stat: TargetStat,
    *,
    category: ExerciseCategory = ExerciseCategory.OFF_ICE,
    muscle_group: MuscleGroup | None = None,
) -> tuple[Exercise, ExerciseTargetStat]:
    exercise = Exercise(
        id=uuid.uuid4(),
        name=name,
        category=category,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
        equipment_type=EquipmentType.BODYWEIGHT,
        muscle_group=muscle_group,
    )
    return exercise, ExerciseTargetStat(exercise_id=exercise.id, target_stat=target_stat, order=0)


def _add_all(db_session, pairs: list[tuple[Exercise, ExerciseTargetStat]]) -> list[Exercise]:
    db_session.add_all([e for e, _ in pairs])
    db_session.add_all([s for _, s in pairs])
    return [e for e, _ in pairs]


def _isolate_candidates(service: ScheduleService, exercises: list[Exercise]) -> None:
    """Make list_for_assembly return only this test's own exercises -- the
    real dev DB now has a real seeded catalog (see the 90-exercise import)
    that would otherwise leak extra same-stat/different-muscle-group
    candidates into these pools and break the "no alternative exists"
    assertions."""

    async def fake_list_for_assembly(*, phase, equipment_access, category, suitable_for_game_day=None):
        return [e for e in exercises if e.phase == phase and e.category == category]

    service._exercises.list_for_assembly = fake_list_for_assembly


@pytest.mark.asyncio
async def test_third_pick_in_a_row_avoids_repeated_group_when_alternative_exists(
    db_session,
) -> None:
    user = _make_user()
    db_session.add(user)
    exercises = _add_all(db_session, [
        _make_exercise("A-strength-push", TargetStat.STRENGTH, muscle_group=MuscleGroup.PUSH),
        _make_exercise("A-agility-push", TargetStat.AGILITY, muscle_group=MuscleGroup.PUSH),
        # Alphabetically first for INTELLECT is also push -- without the
        # balance rule the deterministic tie-break would pick it, same as
        # the first two. The rule should skip it in favor of "B-...-legs".
        _make_exercise("A-intellect-push", TargetStat.INTELLECT, muscle_group=MuscleGroup.PUSH),
        _make_exercise("B-intellect-legs", TargetStat.INTELLECT, muscle_group=MuscleGroup.LEGS),
    ])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == ["A-strength-push", "A-agility-push", "B-intellect-legs"]


@pytest.mark.asyncio
async def test_third_pick_keeps_repeated_group_when_no_alternative(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    exercises = _add_all(db_session, [
        _make_exercise("A-strength-push", TargetStat.STRENGTH, muscle_group=MuscleGroup.PUSH),
        _make_exercise("A-agility-push", TargetStat.AGILITY, muscle_group=MuscleGroup.PUSH),
        # Only candidate for INTELLECT is push too -- no alternative to fall
        # back on, so the slot must still be filled rather than skipped.
        _make_exercise("A-intellect-push", TargetStat.INTELLECT, muscle_group=MuscleGroup.PUSH),
    ])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == ["A-strength-push", "A-agility-push", "A-intellect-push"]


@pytest.mark.asyncio
async def test_on_ice_exercises_never_participate_in_muscle_balance(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    # on_ice exercises always carry muscle_group=None -- the balance rule
    # must be a complete no-op for this category, identical to plain
    # round-robin.
    exercises = _add_all(db_session, [
        _make_exercise("A-strength", TargetStat.STRENGTH, category=ExerciseCategory.ON_ICE),
        _make_exercise("A-agility", TargetStat.AGILITY, category=ExerciseCategory.ON_ICE),
        _make_exercise("A-intellect", TargetStat.INTELLECT, category=ExerciseCategory.ON_ICE),
    ])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    picked = await service._pick_main(ExerciseCategory.ON_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == ["A-strength", "A-agility", "A-intellect"]


@pytest.mark.asyncio
async def test_skill_tag_priority_wins_over_muscle_balance_on_conflict(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    exercises = _add_all(db_session, [
        _make_exercise("A-strength-push", TargetStat.STRENGTH, muscle_group=MuscleGroup.PUSH),
        _make_exercise("A-agility-push", TargetStat.AGILITY, muscle_group=MuscleGroup.PUSH),
        # INTELLECT has a push candidate (tagged) and a legs candidate
        # (untagged). Muscle balance alone would prefer the legs one, but
        # SkillTag priority narrows the pool to the tagged push exercise
        # first -- balance must not reach past that to the legs exercise.
        _make_exercise("A-intellect-push", TargetStat.INTELLECT, muscle_group=MuscleGroup.PUSH),
        _make_exercise("B-intellect-legs", TargetStat.INTELLECT, muscle_group=MuscleGroup.LEGS),
    ])

    skill = Skill(id=uuid.uuid4(), name=f"Test skill {uuid.uuid4().hex[:8]}")
    db_session.add(skill)
    await db_session.flush()

    intellect_push = next(e for e in exercises if e.name == "A-intellect-push")
    db_session.add(
        SkillTag(
            exercise_id=intellect_push.id,
            skill_id=skill.id,
            transfer_note="test transfer note",
        )
    )
    db_session.add(UserSkillPreference(user_id=user.id, skill_id=skill.id))
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == ["A-strength-push", "A-agility-push", "A-intellect-push"]
