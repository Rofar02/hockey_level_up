"""Tag the catalog with the new MuscleGroup.FOREARMS value (added
2026-08-20, see app.models.exercise.MuscleGroup's own docstring for why).

Two different kinds of fix, both driven by the same underlying gap --
grip/wrist/forearm work had no honest home in the original 8 groups:

1. STICK_HANDLING exercises (already added 2026-08-19, see
   backfill_coordination_patterns.py) were tagged core:0.5/shoulders:0.5,
   which was never right -- stick-handling's actual primary demand is
   wrist/forearm rotation, not core or shoulders. Full replace, not a
   scale-down, since the old weights were wrong outright, not just
   missing a secondary.

2. Real pulling/hinging movements that hold external load under tension
   (rows, pull-ups, deadlift-family hinges, farmer's walk) DO genuinely
   tax grip as a secondary mover, and previously got zero credit for it.
   Proportionally scales each exercise's EXISTING weights down to make
   room (ExerciseMuscleGroup enforces sum <= 1.0, see
   ExerciseService.replace_muscle_groups), then adds forearms as a
   secondary. Deliberately NOT applied to every hip_hinge exercise --
   checked the real catalog first: bodyweight glute bridges, rolls, and
   isometric holds in that pattern hold no external load and place no
   real strain on grip, only the 4 barbell/dumbbell-loaded ones ("тяга")
   do. Same reasoning excludes most of the "pull" pattern's cable/band
   isolation work in spirit, but pull's own real content is uniformly
   grip-loaded (every entry holds a bar/handle/TRX/band under tension),
   so that one is applied catalog-wide within the pattern.

Not a migration -- run manually:

    poetry run python scripts/backfill_forearms_muscle_group.py

Idempotent: an exercise that already has a `forearms` row is left alone
(covers both re-runs and any exercise a human already hand-tagged via the
admin panel in the meantime), safe to re-run.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import (  # noqa: E402
    Exercise,
    ExerciseMuscleGroup,
    MuscleGroup,
)

# name -> (forearms weight, core weight, shoulders weight) -- full replace,
# see module docstring point 1.
STICK_HANDLING_TARGET: dict[str, dict[MuscleGroup, float]] = {
    name: {MuscleGroup.FOREARMS: 0.6, MuscleGroup.CORE: 0.25, MuscleGroup.SHOULDERS: 0.15}
    for name in (
        "Подбрасывание шайбы на крюке клюшки",
        "Ведение мяча / шайбы клюшкой (off-ice)",
        "Ведение теннисного мяча клюшкой на асфальте",
    )
}

# name -> (existing-weight scale factor, forearms weight) -- see module
# docstring point 2.
PULL_SECONDARY_NAMES = (
    "Y на наклонной скамье",
    "Австралийские подтягивания",
    "Внутренняя часть лопатки - ролл",
    "Горизонтальная тяга (TRX / кольца / низкий блок)",
    "Гребля (Concept2 или тренажёр)",
    "Гребной тренажёр (лёгкий темп)",
    "Гребной тренажёр интервалами",
    "Наружная ротация гантели сидя",
    "Наружная часть лопатки - ролл",
    "Подтягивания (нейтральный хват)",
    "Подтягивания на TRX / кольцах",
    "Сведение лопаток с резиной в полуприседе на колене",
    "Тяга верхнего блока / горизонтального блока",
    "Тяга гантели в наклоне (Single-Arm Dumbbell Row)",
    "Тяга к лицу",
    "Тяга резины к поясу / лицу",
    "Тяга сидя на одном колене (горизонтальная)",
    "Тяга штанги в наклоне",
)
PULL_SCALE_FACTOR = 0.8
PULL_FOREARMS_WEIGHT = 0.2

HIP_HINGE_LOADED_NAMES = (
    "Становая тяга",
    "Румынская тяга",
    "Румынская тяга на одной ноге",
    "Румынская тяга с гантелями (темп 6-0-0-0)",
)
HIP_HINGE_SCALE_FACTOR = 0.85
HIP_HINGE_FOREARMS_WEIGHT = 0.15

FARMER_CARRY_NAMES = ("Фермерская прогулка",)
FARMER_CARRY_SCALE_FACTOR = 0.75
FARMER_CARRY_FOREARMS_WEIGHT = 0.25


async def backfill() -> None:
    async with AsyncSessionLocal() as session:
        all_names = (
            set(STICK_HANDLING_TARGET)
            | set(PULL_SECONDARY_NAMES)
            | set(HIP_HINGE_LOADED_NAMES)
            | set(FARMER_CARRY_NAMES)
        )
        exercises = (
            await session.execute(select(Exercise).where(Exercise.name.in_(all_names)))
        ).scalars().all()
        by_name = {e.name: e for e in exercises}

        missing = all_names - set(by_name)
        if missing:
            print(f"WARNING: {len(missing)} name(s) not found in DB, skipping: {sorted(missing)}")

        existing_groups: dict = {}
        for row in (
            await session.execute(
                select(ExerciseMuscleGroup).where(
                    ExerciseMuscleGroup.exercise_id.in_([e.id for e in exercises])
                )
            )
        ).scalars().all():
            existing_groups.setdefault(row.exercise_id, {})[row.muscle_group] = row.weight

        updated = 0
        skipped = 0

        def already_tagged(exercise_id) -> bool:
            return MuscleGroup.FOREARMS in existing_groups.get(exercise_id, {})

        async def apply_full_replace(name: str, target: dict[MuscleGroup, float]) -> None:
            nonlocal updated, skipped
            exercise = by_name.get(name)
            if exercise is None:
                return
            if already_tagged(exercise.id):
                skipped += 1
                return
            await session.execute(
                ExerciseMuscleGroup.__table__.delete().where(
                    ExerciseMuscleGroup.exercise_id == exercise.id
                )
            )
            for group, weight in target.items():
                session.add(
                    ExerciseMuscleGroup(exercise_id=exercise.id, muscle_group=group, weight=weight)
                )
            updated += 1
            print(f"  [stick_handling] {name!r}: -> {target}")

        async def apply_secondary(name: str, scale: float, forearms_weight: float) -> None:
            nonlocal updated, skipped
            exercise = by_name.get(name)
            if exercise is None:
                return
            if already_tagged(exercise.id):
                skipped += 1
                return
            current = existing_groups.get(exercise.id, {})
            if not current:
                print(f"  WARNING: {name!r} has no existing muscle groups, skipping")
                return
            new_weights = {group: round(weight * scale, 4) for group, weight in current.items()}
            new_weights[MuscleGroup.FOREARMS] = forearms_weight
            await session.execute(
                ExerciseMuscleGroup.__table__.delete().where(
                    ExerciseMuscleGroup.exercise_id == exercise.id
                )
            )
            for group, weight in new_weights.items():
                session.add(
                    ExerciseMuscleGroup(exercise_id=exercise.id, muscle_group=group, weight=weight)
                )
            updated += 1
            print(f"  {name!r}: {current} -> {new_weights}")

        print("Stick-handling (full replace):")
        for name, target in STICK_HANDLING_TARGET.items():
            await apply_full_replace(name, target)

        print("Pull-pattern secondary grip credit:")
        for name in PULL_SECONDARY_NAMES:
            await apply_secondary(name, PULL_SCALE_FACTOR, PULL_FOREARMS_WEIGHT)

        print("Loaded hip-hinge secondary grip credit:")
        for name in HIP_HINGE_LOADED_NAMES:
            await apply_secondary(name, HIP_HINGE_SCALE_FACTOR, HIP_HINGE_FOREARMS_WEIGHT)

        print("Farmer's carry secondary grip credit:")
        for name in FARMER_CARRY_NAMES:
            await apply_secondary(name, FARMER_CARRY_SCALE_FACTOR, FARMER_CARRY_FOREARMS_WEIGHT)

        await session.commit()
        print(f"\nUpdated {updated} exercise(s), skipped {skipped} already-tagged.")


if __name__ == "__main__":
    asyncio.run(backfill())
