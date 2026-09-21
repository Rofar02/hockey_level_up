"""One-off data fix (2026-09-21): the 3 sled exercises had no equipment
tag at all (equip=[]) -- found spot-checking untagged "bodyweight"
exercises for equipment-implying keywords after the yearly
equipment-profile simulation. A sled push/pull genuinely needs a sled;
nothing in this app's product assumes users own one, so these were
wrongly treated as bodyweight-accessible, available even to the
no-equipment profile.

No dedicated SLED EquipmentItem exists (and doesn't need to -- see
GYM_MACHINE's own docstring: "catch-all for fixed gym equipment with no
item of its own yet ... leg press, lat pulldown, seated row, Smith
machine, rowing machine, assault bike, GHD" -- a sled fits that same
bucket). Tagged all 3 with gym_machine.

Idempotent: sets each exercise's equipment list to exactly [GYM_MACHINE],
replacing whatever was there before (nothing, in practice), so re-running
is a no-op.

Run manually (local): poetry run python scripts/retag_sled_exercises.py
Run in prod: docker compose -f docker-compose.prod.yml exec backend \
    python scripts/retag_sled_exercises.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import Exercise, EquipmentItem  # noqa: E402
from app.repositories.exercise_repository import ExerciseRepository  # noqa: E402

TARGET_NAMES = [
    "Толкание саней",
    "Тяга саней",
    "Тяга саней спиной вперёд",
]


async def retag() -> None:
    async with AsyncSessionLocal() as session:
        repo = ExerciseRepository(session)
        for name in TARGET_NAMES:
            exercises = (
                (await session.execute(select(Exercise).where(Exercise.name == name)))
                .scalars()
                .all()
            )
            if not exercises:
                print(f"SKIP (not found): {name}")
                continue
            for exercise in exercises:
                before = await repo.list_equipment_items(exercise.id)
                await repo.replace_equipment_items(exercise.id, [EquipmentItem.GYM_MACHINE])
                print(f"OK: {name} ({exercise.id}) {before} -> ['gym_machine']")
        await session.commit()


if __name__ == "__main__":
    asyncio.run(retag())
