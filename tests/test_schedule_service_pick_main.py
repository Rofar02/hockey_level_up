"""Phase 7: SkillTag/UserSkillPreference priority in ScheduleService._pick_main.

Verifies the three behaviors called out for this change:
  1. A user with no UserSkillPreference at all gets plain round-robin --
     identical to the pre-Phase-7 behavior.
  2. A user with a chosen skill gets exercises tagged for that skill
     preferred over untagged ones, for the same target_stat.
  3. The "at most one exercise per target_stat per call" rule from Phase 2
     still holds on top of the new priority split.

`random.choice`/`random.randint` are monkeypatched to be deterministic
(alphabetically-first-name / fixed count 3) so the pool each stat draws
from can be asserted exactly, rather than just "some valid exercise".
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
from app.models.skill import Skill, SkillTag, UserSkillPreference
from app.models.user import User
from app.services.schedule_service import ScheduleService


@pytest.fixture(autouse=True)
def deterministic_random(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(random, "randint", lambda a, b: 3)
    monkeypatch.setattr(random, "choice", lambda pool: sorted(pool, key=lambda e: e.name)[0])
    # _pick_main now shuffles movement_pattern iteration order (see its
    # docstring) -- a no-op here keeps this file's assertions on exact pick
    # order deterministic, same intent as the randint/choice patches above.
    monkeypatch.setattr(random, "shuffle", lambda seq: None)


# _pick_main now buckets by movement_pattern, not target_stat (see its
# docstring), through Stage 2.4's fixed role order: role 2 visits
# [SQUAT, HIP_HINGE] (in that order, shuffle no-op'd below), role 3 visits
# [PUSH, PULL] next -- this maps each stat "role" this file already uses
# to a distinct pattern in that real visitation order, so the no-shuffle
# patch still sees them target_stat-equivalent-first/second/third,
# preserving every existing assertion's expected order. None of these
# exercises set stimulus_type, so Stage 2.4's day-archetype narrowing
# always falls back to the full pool here -- it never actually restricts
# anything in this file, only test_day_archetype.py/test_pick_main_roles.py
# exercise that layer directly.
_STAT_TO_PATTERN: dict[TargetStat, MovementPattern] = {
    TargetStat.STRENGTH: MovementPattern.SQUAT,
    TargetStat.AGILITY: MovementPattern.HIP_HINGE,
    TargetStat.INTELLECT: MovementPattern.PUSH,
}


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"user_{unique}",
        email=f"user_{unique}@example.com",
        password_hash="irrelevant",
    )


def _make_exercise(name: str, target_stat: TargetStat) -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=name,
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
    )


_CANDIDATE_STATS: dict[str, TargetStat] = {
    "a_strength": TargetStat.STRENGTH,
    "z_strength": TargetStat.STRENGTH,
    "a_agility": TargetStat.AGILITY,
    "z_agility": TargetStat.AGILITY,
    "a_intellect": TargetStat.INTELLECT,
    "z_intellect": TargetStat.INTELLECT,
}


def _isolate_candidates(service: ScheduleService, exercises: list[Exercise]) -> None:
    """Make list_for_assembly return only this test's own exercises.

    Previously unnecessary here by sheer luck: the old flat shuffle-every-
    pattern loop happened to visit HIP_HINGE/SQUAT/PUSH -- the only
    patterns this file's fixtures ever tag -- before any other pattern,
    simply because they're first in MovementPattern's declaration order,
    so real seeded-catalog candidates for every other pattern never
    factored in with count=3. Stage 2.4's role order tries
    LOCOMOTION/STICK_HANDLING/COORDINATION first (role 1) regardless of
    enum order, which broke that coincidence -- explicit isolation now,
    same as test_pick_main_muscle_balance.py/
    test_schedule_service_suggest_party_exercises.py already do."""

    async def fake_list_for_assembly(*, phase, user, category, suitable_for_game_day=None):
        return [e for e in exercises if e.phase == phase and e.category == category]

    service._exercises.list_for_assembly = fake_list_for_assembly


async def _seed_candidates(db_session) -> dict[str, Exercise]:
    exercises = {
        "a_strength": _make_exercise("A-strength", TargetStat.STRENGTH),
        "z_strength": _make_exercise("Z-strength", TargetStat.STRENGTH),
        "a_agility": _make_exercise("A-agility", TargetStat.AGILITY),
        "z_agility": _make_exercise("Z-agility", TargetStat.AGILITY),
        "a_intellect": _make_exercise("A-intellect", TargetStat.INTELLECT),
        "z_intellect": _make_exercise("Z-intellect", TargetStat.INTELLECT),
    }
    db_session.add_all(exercises.values())
    db_session.add_all([
        ExerciseTargetStat(exercise_id=exercises[key].id, target_stat=stat, order=0)
        for key, stat in _CANDIDATE_STATS.items()
    ])
    db_session.add_all([
        ExerciseMovementPattern(
            exercise_id=exercises[key].id, movement_pattern=_STAT_TO_PATTERN[stat]
        )
        for key, stat in _CANDIDATE_STATS.items()
    ])
    await db_session.flush()
    return exercises


@pytest.mark.asyncio
async def test_no_preference_is_plain_round_robin(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    exercises = await _seed_candidates(db_session)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, list(exercises.values()))
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    # No UserSkillPreference rows at all -> priority pool is always empty ->
    # falls back to the full per-stat pool every time, same as before.
    assert [e.name for e in picked] == [
        exercises["a_strength"].name,
        exercises["a_agility"].name,
        exercises["a_intellect"].name,
    ]


@pytest.mark.asyncio
async def test_preference_prioritizes_tagged_exercise_but_keeps_one_per_stat(
    db_session,
) -> None:
    user = _make_user()
    db_session.add(user)
    exercises = await _seed_candidates(db_session)

    skill = Skill(id=uuid.uuid4(), name=f"Test skill {uuid.uuid4().hex[:8]}")
    db_session.add(skill)
    await db_session.flush()

    # Tag only the alphabetically-last strength exercise -- without
    # priority the deterministic tie-break would never pick it.
    db_session.add(
        SkillTag(
            exercise_id=exercises["z_strength"].id,
            skill_id=skill.id,
            transfer_note="test transfer note",
        )
    )
    db_session.add(UserSkillPreference(user_id=user.id, skill_id=skill.id))
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, list(exercises.values()))
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == [
        exercises["z_strength"].name,  # tagged -> prioritized over "A-strength"
        exercises["a_agility"].name,  # untagged stat -> unaffected, old tie-break
        exercises["a_intellect"].name,  # untagged stat -> unaffected, old tie-break
    ]
    # one-per-stat rule still holds: exactly 3 picks, 3 distinct stats
    assert len(picked) == 3
    name_to_key = {exercises[key].name: key for key in exercises}
    assert len({_CANDIDATE_STATS[name_to_key[e.name]] for e in picked}) == 3
