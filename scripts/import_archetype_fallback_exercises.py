"""One-off import of the 9 exercises drafted in
scripts/archetype_fallback_exercises_draft.md (approved by the user
2026-09-22) to close the two content-gap causes (A, B2) found in the
52-week archetype-fallback simulation -- see the `project_archetype_fallbacks`
memory / audit-round-4 write-up for the full investigation.

Safe to re-run: skips any name that already exists (same convention as
import_master_catalog.py), so a partial failure just picks up where it
left off instead of duplicating.

Usage (run against whichever database this environment's DATABASE_URL
points at -- on the server, that's prod):

    poetry run python scripts/import_archetype_fallback_exercises.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import EquipmentItem, Exercise, MovementPattern, TargetStat  # noqa: E402
from app.schemas.exercise import ExerciseCreate, MuscleGroupWeight  # noqa: E402
from app.services.exercise_service import ExerciseService  # noqa: E402

PULL_M = {"back": 0.6, "shoulders": 0.2, "core": 0.2}
PULL_GRIP_M = {"back": 0.4, "forearms": 0.4, "core": 0.2}
HINGE_M = {"hamstrings": 0.4, "glutes": 0.4, "back": 0.2}
GLUTE_M = {"glutes": 0.6, "hamstrings": 0.2, "core": 0.2}
SQUAT_M = {"quads": 0.5, "glutes": 0.3, "core": 0.2}


def E(name, desc, pattern, stimulus, diff, stats, muscles, equip=(), tw=False, bwr=None, uni=False, vol=(3, 8, 10)):
    sets, rmin, rmax = vol
    return {
        "name": name,
        "description": desc,
        "category": "off_ice",
        "phase": "main",
        "warmup_stage": None,
        "difficulty_level": diff,
        "exercise_type": "sets_reps",
        "target_sets": sets,
        "rep_range_min": rmin,
        "rep_range_max": rmax,
        "target_duration_seconds": None,
        "tracks_weight": tw,
        "bodyweight_ratio": bwr,
        "suitable_for_game_day": False,
        "is_unilateral": uni,
        "stimulus_type": stimulus,
        "target_stats": list(stats),
        "movement_patterns": [pattern],
        "muscle_groups": muscles,
        "equipment_items": list(equip),
    }


EXERCISES = [
    # -- B2: pull/skill (+3) --
    E(
        "Лопаточные подтягивания",
        "Вис на турнике прямыми руками, подъём/сведение лопаток без сгибания рук — база для полноценного подтягивания.",
        "pull", "skill", 1, ("strength",), PULL_GRIP_M, equip=["pull_up_bar"],
    ),
    E(
        "Тяга резины одной рукой стоя на одной ноге",
        "Стойка на одной ноге, тяга резины одной рукой к поясу — баланс усложняет обычную тягу резины без роста силовой нагрузки.",
        "pull", "skill", 2, ("strength", "agility"), PULL_M, equip=["resistance_band"], uni=True,
    ),
    E(
        "Тяга гантели в наклоне с паузой в верхней точке",
        "Тяга одной гантели в наклоне с паузой 1-2с в верхней точке — контроль сведения лопатки, а не про вес.",
        "pull", "skill", 2, ("strength",), PULL_M, equip=["dumbbells"], tw=True, bwr=0.2, uni=True,
    ),
    # -- B2: hip_hinge/skill (+3) --
    E(
        "Гуд-морнинг с палкой на плечах",
        "Палка на плечах как визуальный ориентир прямой спины, наклон корпуса вперёд с сохранением нейтрали — обучающий вариант перед весом.",
        "hip_hinge", "skill", 1, ("strength",), HINGE_M,
    ),
    E(
        "Румынская тяга на одной ноге без веса",
        "Баланс на одной ноге, наклон корпуса вперёд с прямой опорной ногой без веса — навыковая версия перед нагруженной RDL.",
        "hip_hinge", "skill", 2, ("strength", "agility"), HINGE_M, uni=True,
    ),
    E(
        "Сгибание ноги со слайдом",
        "Лёжа на спине, пятка на слайде/полотенце по полу, сгибание и разгибание ноги с эксцентрическим контролем хамстрингов.",
        "hip_hinge", "skill", 3, ("strength",), HINGE_M, vol=(3, 8, 12),
    ),
    # -- A: power difficulty 1 for beginners (+3) --
    E(
        "Приседание с мини-выпрыгиванием",
        "Присед до полуприседа, лёгкий подскок вверх на минимальную высоту, мягкое приземление — первое знакомство со взрывной работой ног.",
        "squat", "power", 1, ("agility", "strength"), SQUAT_M, vol=(3, 6, 8),
    ),
    E(
        "Взрывной подъём таза лёжа",
        "Ягодичный мост лёжа на спине, подъём таза резкий/взрывной вместо медленного, фиксация вверху на секунду, контролируемый спуск.",
        "hip_hinge", "power", 1, ("strength", "agility"), GLUTE_M,
    ),
    E(
        "Взрывная тяга резины к поясу стоя",
        "Лёгкая резина, стоя, резкое горизонтальное подтягивание рук к поясу на скорость, медленный контролируемый возврат.",
        "pull", "power", 1, ("strength", "agility"), PULL_M, equip=["resistance_band"],
    ),
]

names = [e["name"] for e in EXERCISES]
assert len(names) == len(set(names)), "duplicate name in EXERCISES"


async def main() -> None:
    async with AsyncSessionLocal() as session:
        service = ExerciseService(session)
        existing = await session.execute(select(Exercise.name))
        existing_names = {row[0] for row in existing.all()}

        added = 0
        skipped = 0
        for index, entry in enumerate(EXERCISES, start=1):
            name = entry["name"]
            if name in existing_names:
                print(f"[{index}/{len(EXERCISES)}] SKIP (exists): {name}")
                skipped += 1
                continue

            create_payload = ExerciseCreate(
                name=name,
                description=entry["description"],
                category=entry["category"],
                phase=entry["phase"],
                difficulty_level=entry["difficulty_level"],
                target_sets=entry["target_sets"],
                rep_range_min=entry["rep_range_min"],
                rep_range_max=entry["rep_range_max"],
                target_duration_seconds=entry["target_duration_seconds"],
                tracks_weight=entry["tracks_weight"],
                bodyweight_ratio=entry["bodyweight_ratio"],
                suitable_for_game_day=entry["suitable_for_game_day"],
                is_unilateral=entry["is_unilateral"],
                stimulus_type=entry["stimulus_type"],
                exercise_type=entry["exercise_type"],
                warmup_stage=entry["warmup_stage"],
            )
            created = await service.create_exercise(create_payload)

            await service.replace_target_stats(
                created.id, [TargetStat(s) for s in entry["target_stats"]]
            )
            await service.replace_movement_patterns(
                created.id, [MovementPattern(p) for p in entry["movement_patterns"]]
            )
            await service.replace_muscle_groups(
                created.id,
                [
                    MuscleGroupWeight(muscle_group=group, weight=weight)
                    for group, weight in entry["muscle_groups"].items()
                ],
            )
            if entry["equipment_items"]:
                await service.replace_equipment_items(
                    created.id, [EquipmentItem(i) for i in entry["equipment_items"]]
                )

            print(f"[{index}/{len(EXERCISES)}] added: {name}")
            added += 1

        print(f"\nDone. Added {added}, skipped {skipped} (already existed).")


if __name__ == "__main__":
    asyncio.run(main())
