"""One-off backfill (Phase: П.1 double progression): rep_range_min/
rep_range_max for every exercise_type=sets_reps exercise, defaulted per its
stimulus_type. Ranges are drawn from a physiology-based rule of thumb, not a
real training program -- flagged to the product owner for revision like
every other draft-data backfill in this directory. STIMULUS_MOBILITY_RANGE
isn't from the original design spec (which assumed mobility work is always
duration-based); added here because 8 real sets_reps/mobility rows exist in
the catalog and need *some* default, not because a real number was sourced
for it.

Idempotent: only fills rows where rep_range_min IS NULL, so rerunning after
an admin hand-edits a specific exercise's range is always safe -- it will
never overwrite a value someone already set on purpose.

    docker compose exec backend poetry run python scripts/backfill_exercise_rep_ranges.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import Exercise, ExerciseType, StimulusType  # noqa: E402

_DEFAULT_RANGE: dict[StimulusType, tuple[int, int]] = {
    StimulusType.STRENGTH: (6, 12),
    StimulusType.ENDURANCE: (12, 20),
    StimulusType.SKILL: (8, 12),
    # Narrow on purpose: explosive/power work loses quality once fatigue
    # accumulates, so a wide range would encourage grinding out sloppy reps
    # instead of stopping the set.
    StimulusType.POWER: (3, 5),
    StimulusType.MOBILITY: (10, 15),
}


async def backfill() -> None:
    async with AsyncSessionLocal() as session:
        exercises = (
            (
                await session.execute(
                    select(Exercise).where(
                        Exercise.exercise_type == ExerciseType.SETS_REPS,
                        Exercise.rep_range_min.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )

        updated = 0
        skipped_unclassified: list[str] = []
        for exercise in exercises:
            if exercise.stimulus_type is None:
                skipped_unclassified.append(exercise.name)
                continue
            rep_range_min, rep_range_max = _DEFAULT_RANGE[exercise.stimulus_type]
            exercise.rep_range_min = rep_range_min
            exercise.rep_range_max = rep_range_max
            updated += 1

        await session.commit()
        print(f"Updated {updated} exercise(s) with a default rep range.")
        if skipped_unclassified:
            print(
                f"WARNING: {len(skipped_unclassified)} sets_reps exercise(s) have no "
                f"stimulus_type, skipped: {sorted(skipped_unclassified)}"
            )


if __name__ == "__main__":
    asyncio.run(backfill())
