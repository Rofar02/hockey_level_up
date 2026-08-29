"""Exports the admin-edited exercise catalog content (technique text, video,
muscle/movement/equipment tags, skill tags, per-exercise classification
flags) to a name-keyed JSON snapshot, for syncing this content onto another
environment's database via scripts/import_exercise_catalog.py.

Exists because none of this content lives in scripts/seed_exercises.py --
that script only seeds the base exercise rows (name/category/phase/
difficulty/target stats) with placeholder descriptions; everything richer
is entered by hand through the admin panel and lives only in whichever
database it was entered against. A raw pg_dump of the `exercises` table
can't move between environments -- local and prod each generated their own
random UUIDs for the "same" (by name) exercise, so a straight table copy
either 409s on the unique `name` constraint or silently creates duplicate
rows under fresh ids. Name-keyed export/import sidesteps that entirely.

Usage (run wherever the source-of-truth database is, e.g. local dev):

    poetry run python scripts/export_exercise_catalog.py

Writes scripts/exercise_catalog_export.json, committed to the repo so a
`git pull` on the target environment delivers it -- then run
scripts/import_exercise_catalog.py there.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import (  # noqa: E402
    Exercise,
    ExerciseEquipmentItem,
    ExerciseMovementPattern,
    ExerciseMuscleGroup,
)
from app.models.skill import Skill, SkillTag  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parent / "exercise_catalog_export.json"

# Scalar fields entered/refined via the admin panel, never touched by
# seed_exercises.py beyond a placeholder description -- deliberately
# excludes name/category/phase/difficulty_level/target_sets/rep_range_*/
# target_duration_seconds, which are seed-script-owned base identity, not
# admin enrichment, and shouldn't be overwritten by this sync.
SCALAR_FIELDS = [
    "description",
    "video_source_type",
    "video_source_id",
    "stimulus_type",
    "exercise_type",
    "warmup_stage",
    "tracks_weight",
    "bodyweight_ratio",
    "suitable_for_game_day",
    "is_unilateral",
]


def _enum_value(value):
    return value.value if value is not None else None


async def export_catalog() -> None:
    async with AsyncSessionLocal() as session:
        exercises = (await session.execute(select(Exercise))).scalars().all()

        muscle_rows = (
            await session.execute(select(ExerciseMuscleGroup))
        ).scalars().all()
        muscles_by_exercise: dict = {}
        for row in muscle_rows:
            muscles_by_exercise.setdefault(row.exercise_id, []).append(
                {"muscle_group": row.muscle_group.value, "weight": row.weight}
            )

        pattern_rows = (
            await session.execute(select(ExerciseMovementPattern))
        ).scalars().all()
        patterns_by_exercise: dict = {}
        for row in pattern_rows:
            patterns_by_exercise.setdefault(row.exercise_id, []).append(row.movement_pattern.value)

        item_rows = (await session.execute(select(ExerciseEquipmentItem))).scalars().all()
        items_by_exercise: dict = {}
        for row in item_rows:
            items_by_exercise.setdefault(row.exercise_id, []).append(row.equipment_item.value)

        skill_by_id = {skill.id: skill.name for skill in (await session.execute(select(Skill))).scalars().all()}
        tag_rows = (await session.execute(select(SkillTag))).scalars().all()
        tags_by_exercise: dict = {}
        for row in tag_rows:
            skill_name = skill_by_id.get(row.skill_id)
            if skill_name is None:
                continue
            tags_by_exercise.setdefault(row.exercise_id, []).append(
                {"skill_name": skill_name, "transfer_note": row.transfer_note}
            )

        catalog = []
        for exercise in exercises:
            entry = {"name": exercise.name}
            for field in SCALAR_FIELDS:
                value = getattr(exercise, field)
                entry[field] = _enum_value(value) if hasattr(value, "value") else value
            entry["muscle_groups"] = muscles_by_exercise.get(exercise.id, [])
            entry["movement_patterns"] = patterns_by_exercise.get(exercise.id, [])
            entry["equipment_items"] = items_by_exercise.get(exercise.id, [])
            entry["skill_tags"] = tags_by_exercise.get(exercise.id, [])
            catalog.append(entry)

        catalog.sort(key=lambda entry: entry["name"])
        OUTPUT_PATH.write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Exported {len(catalog)} exercise(s) to {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(export_catalog())
