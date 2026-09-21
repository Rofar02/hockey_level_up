"""One-off data fix (2026-09-21): remove "Плавание на выносливость" (pool
swimming) from the catalog -- requires a pool, doesn't fit the product.
Also the only PULL+ENDURANCE candidate for a bodyweight-only user (see
scripts/retag_fitball_exercises.py's neighbor investigation, the yearly
equipment-profile simulation), which meant guarantee_endurance landed on
it deterministically whenever PULL was picked as the guaranteed pattern --
62/424 off-ice MAIN slots in a 52-week bodyweight-only simulation. Removing
it doesn't leave PULL+ENDURANCE empty for bodyweight users in a worse way
than before (it already had no bodyweight alternative); LOCOMOTION still
has real bodyweight-friendly endurance content ("Бег на выносливость",
"Велосипед интервалы", etc.) for guarantee_endurance to fall back to.

Already removed from scripts/import_master_catalog.py and marked УДАЛЕНО
in icelevel_master_catalog.md, so a future full catalog rebuild won't
reintroduce it. This script removes the already-imported row from a live
database. Idempotent: no-ops if the exercise doesn't exist.

Uses ExerciseService.delete_exercise (the same path the admin UI's delete
button calls) rather than a raw DELETE, so a still-in-use row (real logged
SessionBlock/SetCompletion history) fails the same documented way the
admin UI would -- 409-shaped, not a silent skip.

Run manually (local): poetry run python scripts/remove_swimming_endurance_exercise.py
Run in prod: docker compose -f docker-compose.prod.yml exec backend \
    python scripts/remove_swimming_endurance_exercise.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import Exercise  # noqa: E402
from app.services.exercise_service import ExerciseService  # noqa: E402

EXERCISE_NAME = "Плавание на выносливость"


async def main() -> None:
    async with AsyncSessionLocal() as session:
        exercise = (
            (await session.execute(select(Exercise).where(Exercise.name == EXERCISE_NAME)))
            .scalars()
            .first()
        )
        if exercise is None:
            print(f"SKIP (not found, already removed): {EXERCISE_NAME}")
            return

        try:
            await ExerciseService(session).delete_exercise(exercise.id)
        except HTTPException as exc:
            print(f"BLOCKED: {EXERCISE_NAME} ({exercise.id}) -- {exc.detail}")
            return
        print(f"OK: deleted {EXERCISE_NAME} ({exercise.id})")


if __name__ == "__main__":
    asyncio.run(main())
