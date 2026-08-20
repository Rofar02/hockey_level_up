"""_apply_muscle_balance: soft anatomical variety rule, Stage 2.4 -- now
role-4-only (accessories/core), aware of every muscle group loaded
anywhere earlier in the session (roles 1-3, plus role 4's own picks so
far), not just the last two picks like the pre-2.4 version. See
test_schedule_service_pick_main.py for the readiness/phase/SkillTag
priority chain this layers on top of, and test_pick_main_roles.py for
role ordering itself.

Verifies:
  1. A role-4 pick avoids repeating a muscle group an earlier pick (in
     this session) already loaded, when an alternative exists in the pool.
  2. With no such alternative, the repeat is still picked rather than
     leaving the slot empty.
  3. on_ice exercises (no ExerciseMuscleGroup rows at all in these tests)
     never trigger or get filtered by the rule -- it's a natural
     consequence of an empty muscle-group set never intersecting anything,
     not a category special-case.
  4. SkillTag priority still wins a real conflict: muscle balance only
     narrows within the tag-priority pool, never reaches back out to an
     untagged alternative from a different group.

All exercises here use ROTATION/CORE/ANKLE_MOBILITY -- role-4-only
patterns (see day_archetype.ARCHETYPE_ELIGIBLE_PATTERNS and
ScheduleService._pick_main's role-1 pattern list) -- so roles 1-3 always
contribute nothing and every pick in these tests comes from role 4 itself,
keeping the muscle-balance behavior isolated and deterministic.

`random.choice`/`random.randint` are monkeypatched exactly as in
test_schedule_service_pick_main.py so each pattern's candidate pool can be
asserted precisely.
"""
import random
import uuid

import pytest

from app.core.training_block import BlockPhase
from app.models.exercise import (
    Exercise,
    ExerciseCategory,
    ExerciseMovementPattern,
    ExerciseMuscleGroup,
    ExerciseTargetStat,
    MovementPattern,
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
    # _pick_main shuffles pattern order within each role -- a no-op here
    # keeps this file's assertions on exact pick order deterministic, same
    # intent as the randint/choice patches above.
    monkeypatch.setattr(random, "shuffle", lambda seq: None)


# Role-4-only patterns, in the order role 4 (with shuffle no-op'd) visits
# them: MovementPattern's own declaration order, filtered to the
# archetype-eligible/explosive ones role 4 never reaches -- ROTATION,
# then ANKLE_MOBILITY, then (skipping the empty-pool HIP_MOBILITY/
# SHOULDER_MOBILITY/WRIST_MOBILITY in between) CORE.
_STAT_TO_PATTERN: dict[TargetStat, MovementPattern] = {
    TargetStat.STRENGTH: MovementPattern.ROTATION,
    TargetStat.AGILITY: MovementPattern.ANKLE_MOBILITY,
    TargetStat.INTELLECT: MovementPattern.CORE,
}


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"user_{unique}",
        email=f"user_{unique}@example.com",
        password_hash="irrelevant",
    )


def _make_exercise(
    name: str,
    target_stat: TargetStat,
    *,
    category: ExerciseCategory = ExerciseCategory.OFF_ICE,
    muscle_group: MuscleGroup | None = None,
) -> tuple[Exercise, ExerciseTargetStat, ExerciseMovementPattern, ExerciseMuscleGroup | None]:
    exercise = Exercise(
        id=uuid.uuid4(),
        name=name,
        category=category,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
    )
    muscle_group_row = (
        ExerciseMuscleGroup(exercise_id=exercise.id, muscle_group=muscle_group, weight=1.0)
        if muscle_group is not None
        else None
    )
    return (
        exercise,
        ExerciseTargetStat(exercise_id=exercise.id, target_stat=target_stat, order=0),
        ExerciseMovementPattern(
            exercise_id=exercise.id, movement_pattern=_STAT_TO_PATTERN[target_stat]
        ),
        muscle_group_row,
    )


def _add_all(
    db_session,
    rows: list[tuple[Exercise, ExerciseTargetStat, ExerciseMovementPattern, ExerciseMuscleGroup | None]],
) -> list[Exercise]:
    db_session.add_all([e for e, _, _, _ in rows])
    db_session.add_all([s for _, s, _, _ in rows])
    db_session.add_all([p for _, _, p, _ in rows])
    db_session.add_all([m for _, _, _, m in rows if m is not None])
    return [e for e, _, _, _ in rows]


def _isolate_candidates(service: ScheduleService, exercises: list[Exercise]) -> None:
    """Make list_for_assembly return only this test's own exercises -- the
    real dev DB now has a real seeded catalog that would otherwise leak
    extra same-stat/different-muscle-group candidates into these pools and
    break the "no alternative exists" assertions."""

    async def fake_list_for_assembly(*, phase, user, category, suitable_for_game_day=None):
        return [e for e in exercises if e.phase == phase and e.category == category]

    service._exercises.list_for_assembly = fake_list_for_assembly


@pytest.mark.asyncio
async def test_role4_pick_avoids_repeated_group_when_alternative_exists(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    exercises = _add_all(db_session, [
        _make_exercise("A-strength-chest", TargetStat.STRENGTH, muscle_group=MuscleGroup.CHEST),
        _make_exercise("A-agility-chest", TargetStat.AGILITY, muscle_group=MuscleGroup.CHEST),
        # Alphabetically first for INTELLECT is also chest -- without the
        # balance rule the deterministic tie-break would pick it, same as
        # the first two. The rule should skip it in favor of "B-...-quads".
        _make_exercise("A-intellect-chest", TargetStat.INTELLECT, muscle_group=MuscleGroup.CHEST),
        _make_exercise("B-intellect-quads", TargetStat.INTELLECT, muscle_group=MuscleGroup.QUADS),
    ])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == ["A-strength-chest", "A-agility-chest", "B-intellect-quads"]


@pytest.mark.asyncio
async def test_role4_pick_keeps_repeated_group_when_no_alternative(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    exercises = _add_all(db_session, [
        _make_exercise("A-strength-chest", TargetStat.STRENGTH, muscle_group=MuscleGroup.CHEST),
        _make_exercise("A-agility-chest", TargetStat.AGILITY, muscle_group=MuscleGroup.CHEST),
        # Only candidate for INTELLECT is chest too -- no alternative to
        # fall back on, so the slot must still be filled rather than
        # skipped.
        _make_exercise("A-intellect-chest", TargetStat.INTELLECT, muscle_group=MuscleGroup.CHEST),
    ])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == ["A-strength-chest", "A-agility-chest", "A-intellect-chest"]


@pytest.mark.asyncio
async def test_on_ice_exercises_never_participate_in_muscle_balance(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    # on_ice exercises here carry no ExerciseMuscleGroup rows at all -- the
    # balance rule must be a complete no-op, identical to plain round-robin.
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
        _make_exercise("A-strength-chest", TargetStat.STRENGTH, muscle_group=MuscleGroup.CHEST),
        _make_exercise("A-agility-chest", TargetStat.AGILITY, muscle_group=MuscleGroup.CHEST),
        # INTELLECT has a chest candidate (tagged) and a quads candidate
        # (untagged). Muscle balance alone would prefer the quads one, but
        # SkillTag priority narrows the pool to the tagged chest exercise
        # first -- balance must not reach past that to the quads exercise.
        _make_exercise("A-intellect-chest", TargetStat.INTELLECT, muscle_group=MuscleGroup.CHEST),
        _make_exercise("B-intellect-quads", TargetStat.INTELLECT, muscle_group=MuscleGroup.QUADS),
    ])

    skill = Skill(id=uuid.uuid4(), name=f"Test skill {uuid.uuid4().hex[:8]}")
    db_session.add(skill)
    await db_session.flush()

    intellect_chest = next(e for e in exercises if e.name == "A-intellect-chest")
    db_session.add(
        SkillTag(
            exercise_id=intellect_chest.id,
            skill_id=skill.id,
            transfer_note="test transfer note",
        )
    )
    db_session.add(UserSkillPreference(user_id=user.id, skill_id=skill.id))
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == ["A-strength-chest", "A-agility-chest", "A-intellect-chest"]
