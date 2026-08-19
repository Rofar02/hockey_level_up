"""Tag the catalog's stick-skill and general coordination/reaction/balance
off-ice exercises with the two movement_pattern values added 2026-08-19
(STICK_HANDLING, COORDINATION) -- without a movement_pattern these were
simply invisible to ScheduleService._pick_main (an exercise with no
patterns at all is absent from every bucket), so they could never actually
be assembled into a session no matter how well-tagged everything else was.

Balance work (the one-legged-eyes-closed drill) is folded into COORDINATION
rather than getting its own pattern -- movement_pattern only needs to be as
coarse as MAIN diversity / warmup-cooldown matching require, unlike
skill_tags, which still track "Баланс и устойчивость" as its own skill.

Additive only, not a full replace (unlike backfill_exercise_metadata.py):
these 6 exercises had zero movement_pattern rows going in, this only adds
the one row each needs. Not a migration -- run manually:

    poetry run python scripts/backfill_coordination_patterns.py

Idempotent: skips an exercise already carrying the target pattern, safe to
re-run.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import Exercise, ExerciseMovementPattern, MovementPattern  # noqa: E402

# name -> MovementPattern value
CLASSIFICATION: dict[str, str] = {
    "Ведение мяча / шайбы клюшкой (off-ice)": "stick_handling",
    "Ведение теннисного мяча клюшкой на асфальте": "stick_handling",
    "Подбрасывание шайбы на крюке клюшки": "stick_handling",
    "Жонглирование двумя мячами": "coordination",
    "Ловля теннисного мяча на реакцию": "coordination",
    "Стойка на одной ноге с закрытыми глазами": "coordination",
}


async def backfill() -> None:
    async with AsyncSessionLocal() as session:
        exercises = (
            await session.execute(select(Exercise).where(Exercise.name.in_(CLASSIFICATION)))
        ).scalars().all()
        by_name = {e.name: e for e in exercises}

        missing = set(CLASSIFICATION) - set(by_name)
        if missing:
            print(f"WARNING: {len(missing)} classified name(s) not found in DB, skipping: {sorted(missing)}")

        existing_pairs = {
            (row.exercise_id, row.movement_pattern)
            for row in (
                await session.execute(
                    select(ExerciseMovementPattern).where(
                        ExerciseMovementPattern.exercise_id.in_([e.id for e in exercises])
                    )
                )
            ).scalars().all()
        }

        added = 0
        for name, pattern in CLASSIFICATION.items():
            exercise = by_name.get(name)
            if exercise is None:
                continue
            target = MovementPattern(pattern)
            if (exercise.id, target) in existing_pairs:
                continue
            session.add(ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=target))
            added += 1

        await session.commit()
        print(f"Classified {len(CLASSIFICATION)} exercise(s), added {added} new pattern row(s).")


if __name__ == "__main__":
    asyncio.run(backfill())
