"""SkillService.list_all_tags (GET /exercises/skill-tags) -- bulk,
non-admin-gated read backing the player-facing exercise catalog browser
(2026-08-30), which groups the whole exercise list by skill and would
otherwise need one GET .../{id}/skills per exercise. Same "look up this
test's own rows in the full result" approach as
test_exercise_equipment_requirements.py, since the seeded catalog also has
real skill tags.
"""
import uuid

import pytest

from app.models.exercise import Exercise, ExerciseCategory, TrainingPhase
from app.models.skill import Skill, SkillTag
from app.services.skill_service import SkillService


def _make_exercise() -> Exercise:
    unique = uuid.uuid4().hex[:8]
    return Exercise(
        id=uuid.uuid4(),
        name=f"Exercise {unique}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
    )


def _make_skill() -> Skill:
    unique = uuid.uuid4().hex[:8]
    return Skill(id=uuid.uuid4(), name=f"Skill {unique}")


@pytest.mark.asyncio
async def test_includes_a_tag_for_this_exercise_and_skill(db_session) -> None:
    exercise = _make_exercise()
    skill = _make_skill()
    db_session.add_all([exercise, skill])
    await db_session.flush()
    tag = SkillTag(
        id=uuid.uuid4(), exercise_id=exercise.id, skill_id=skill.id, transfer_note="note"
    )
    db_session.add(tag)
    await db_session.flush()

    tags = await SkillService(db_session).list_all_tags()

    match = next(t for t in tags if t.id == tag.id)
    assert match.exercise_id == exercise.id
    assert match.skill_id == skill.id


@pytest.mark.asyncio
async def test_an_exercise_tagged_for_two_skills_appears_twice(db_session) -> None:
    exercise = _make_exercise()
    skill_a = _make_skill()
    skill_b = _make_skill()
    db_session.add_all([exercise, skill_a, skill_b])
    await db_session.flush()
    db_session.add_all([
        SkillTag(id=uuid.uuid4(), exercise_id=exercise.id, skill_id=skill_a.id, transfer_note="a"),
        SkillTag(id=uuid.uuid4(), exercise_id=exercise.id, skill_id=skill_b.id, transfer_note="b"),
    ])
    await db_session.flush()

    tags = await SkillService(db_session).list_all_tags()

    matching_skill_ids = {t.skill_id for t in tags if t.exercise_id == exercise.id}
    assert matching_skill_ids == {skill_a.id, skill_b.id}


@pytest.mark.asyncio
async def test_an_untagged_exercise_contributes_no_rows(db_session) -> None:
    exercise = _make_exercise()
    db_session.add(exercise)
    await db_session.flush()

    tags = await SkillService(db_session).list_all_tags()

    assert all(t.exercise_id != exercise.id for t in tags)
