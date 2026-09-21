"""One-off data fix (2026-09-21): tag the master catalog's fitball
exercises with the new EquipmentItem.FITBALL, added alongside this
script. Before FITBALL existed these had nothing to tag them with, so
they were either untagged (visible to every user regardless of
equipment) or -- in one case -- wrongly tagged gym_machine.

Idempotent: sets each exercise's equipment list to exactly [FITBALL],
replacing whatever was there before, so re-running is a no-op. Deliberately
NOT run against "Планка на нестабильной поверхности", which the catalog
text explicitly allows fitball/BOSU/balance-disc as interchangeable
alternatives for -- tagging it FITBALL specifically would narrow its
availability versus the author's intent, since equipment tags are AND
(all-required), not "any of".

Run manually (local): poetry run python scripts/retag_fitball_exercises.py
Run in prod: docker compose -f docker-compose.prod.yml exec backend \
    python scripts/retag_fitball_exercises.py
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
    "Мешай в котле",
    "Планка на фитболе с перекатом",
    "Сгибание ног на мяче",
    "Сгибание ног на фитболе (эксцентрика)",
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
                await repo.replace_equipment_items(exercise.id, [EquipmentItem.FITBALL])
                print(f"OK: {name} ({exercise.id}) {before} -> ['fitball']")
        await session.commit()


if __name__ == "__main__":
    asyncio.run(retag())
