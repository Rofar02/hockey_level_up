"""Applies a catalog export (see scripts/export_exercise_catalog.py) onto
this environment's database, matching exercises by `name` -- never by id,
since ids are independently random per environment (see that script's own
docstring for why a raw table copy can't work here).

Usage (run against whichever database this environment's DATABASE_URL
points at -- on the server, that's prod):

    poetry run python scripts/import_exercise_catalog.py

Safe to re-run: every write is either "set this scalar field to the
exported value" or a full delete-then-insert of a tag table for one
exercise, so running twice with the same export file converges to the
same state, not duplicates.

Conservative by design -- an exported field/tag-list that's empty (None,
or an empty list) is treated as "nothing recorded on the source side yet",
not "clear this on the target": it's skipped rather than blanking out
something the target database already has. Only a name that doesn't
resolve to an exercise, or a skill_name that doesn't resolve to a skill,
is reported as skipped -- everything else applies silently.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import (  # noqa: E402
    EquipmentItem,
    Exercise,
    ExerciseEquipmentItem,
    ExerciseType,
    ExerciseMovementPattern,
    ExerciseMuscleGroup,
    MovementPattern,
    MuscleGroup,
    StimulusType,
    WarmupStage,
)
from app.models.skill import Skill, SkillTag  # noqa: E402

INPUT_PATH = Path(__file__).resolve().parent / "exercise_catalog_export.json"

ENUM_FIELDS = {
    "stimulus_type": StimulusType,
    "exercise_type": ExerciseType,
    "warmup_stage": WarmupStage,
}
PLAIN_SCALAR_FIELDS = [
    "description",
    "video_source_type",
    "video_source_id",
    "tracks_weight",
    "bodyweight_ratio",
    "suitable_for_game_day",
    "is_unilateral",
]


async def import_catalog() -> None:
    catalog = json.loads(INPUT_PATH.read_text(encoding="utf-8"))

    async with AsyncSessionLocal() as session:
        skill_id_by_name = {
            skill.name: skill.id for skill in (await session.execute(select(Skill))).scalars().all()
        }

        updated = 0
        missing_exercises: list[str] = []
        missing_skills: set[str] = set()

        for entry in catalog:
            exercise = (
                await session.execute(select(Exercise).where(Exercise.name == entry["name"]))
            ).scalar_one_or_none()
            if exercise is None:
                missing_exercises.append(entry["name"])
                continue

            changed = False
            for field in PLAIN_SCALAR_FIELDS:
                value = entry.get(field)
                if value is not None and getattr(exercise, field) != value:
                    setattr(exercise, field, value)
                    changed = True
            for field, enum_cls in ENUM_FIELDS.items():
                raw_value = entry.get(field)
                if raw_value is not None:
                    value = enum_cls(raw_value)
                    if getattr(exercise, field) != value:
                        setattr(exercise, field, value)
                        changed = True

            if entry.get("muscle_groups"):
                desired = {(row["muscle_group"], row["weight"]) for row in entry["muscle_groups"]}
                existing = {
                    (row.muscle_group.value, row.weight)
                    for row in (
                        await session.execute(
                            select(ExerciseMuscleGroup).where(
                                ExerciseMuscleGroup.exercise_id == exercise.id
                            )
                        )
                    ).scalars().all()
                }
                if desired != existing:
                    await session.execute(
                        delete(ExerciseMuscleGroup).where(
                            ExerciseMuscleGroup.exercise_id == exercise.id
                        )
                    )
                    for muscle_group, weight in desired:
                        session.add(
                            ExerciseMuscleGroup(
                                exercise_id=exercise.id,
                                muscle_group=MuscleGroup(muscle_group),
                                weight=weight,
                            )
                        )
                    changed = True

            if entry.get("movement_patterns"):
                desired_patterns = set(entry["movement_patterns"])
                existing_patterns = {
                    row.movement_pattern.value
                    for row in (
                        await session.execute(
                            select(ExerciseMovementPattern).where(
                                ExerciseMovementPattern.exercise_id == exercise.id
                            )
                        )
                    ).scalars().all()
                }
                if desired_patterns != existing_patterns:
                    await session.execute(
                        delete(ExerciseMovementPattern).where(
                            ExerciseMovementPattern.exercise_id == exercise.id
                        )
                    )
                    for pattern in desired_patterns:
                        session.add(
                            ExerciseMovementPattern(
                                exercise_id=exercise.id, movement_pattern=MovementPattern(pattern)
                            )
                        )
                    changed = True

            if entry.get("equipment_items"):
                desired_items = set(entry["equipment_items"])
                existing_items = {
                    row.equipment_item.value
                    for row in (
                        await session.execute(
                            select(ExerciseEquipmentItem).where(
                                ExerciseEquipmentItem.exercise_id == exercise.id
                            )
                        )
                    ).scalars().all()
                }
                if desired_items != existing_items:
                    await session.execute(
                        delete(ExerciseEquipmentItem).where(
                            ExerciseEquipmentItem.exercise_id == exercise.id
                        )
                    )
                    for item in desired_items:
                        session.add(
                            ExerciseEquipmentItem(
                                exercise_id=exercise.id, equipment_item=EquipmentItem(item)
                            )
                        )
                    changed = True

            if entry.get("skill_tags"):
                resolved_tags = []
                for tag in entry["skill_tags"]:
                    skill_id = skill_id_by_name.get(tag["skill_name"])
                    if skill_id is None:
                        missing_skills.add(tag["skill_name"])
                        continue
                    resolved_tags.append((skill_id, tag["transfer_note"]))
                if resolved_tags:
                    desired_tags = set(resolved_tags)
                    existing_tags = {
                        (row.skill_id, row.transfer_note)
                        for row in (
                            await session.execute(
                                select(SkillTag).where(SkillTag.exercise_id == exercise.id)
                            )
                        ).scalars().all()
                    }
                    if desired_tags != existing_tags:
                        await session.execute(
                            delete(SkillTag).where(SkillTag.exercise_id == exercise.id)
                        )
                        for skill_id, transfer_note in desired_tags:
                            session.add(
                                SkillTag(
                                    exercise_id=exercise.id,
                                    skill_id=skill_id,
                                    transfer_note=transfer_note,
                                )
                            )
                        changed = True

            if changed:
                updated += 1

        await session.commit()
        print(f"Updated {updated} of {len(catalog)} exercise(s).")
        if missing_exercises:
            print(f"Skipped {len(missing_exercises)} name(s) not found in this database:")
            for name in missing_exercises:
                print(f"  - {name}")
        if missing_skills:
            print(f"Skipped tag(s) referencing {len(missing_skills)} skill name(s) not found here:")
            for name in sorted(missing_skills):
                print(f"  - {name}")


if __name__ == "__main__":
    asyncio.run(import_catalog())
