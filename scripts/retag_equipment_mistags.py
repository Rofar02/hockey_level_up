"""One-off fix: 16 exercises tagged equipment_type=gym (or, in two cases,
home) that don't actually need that tier of equipment -- band/resistance
work, a pull-up bar or table edge, a stability-ball glute bridge, a portable
med ball, wrist rotation with no equipment at all. Found by manually
checking every gym-tagged exercise's real requirement against its
description (2026-08-18 planning session), not by the earlier regex sweep
(too many false positives, discarded).

Not a migration -- run manually:

    poetry run python scripts/retag_equipment_mistags.py

Idempotent: only touches rows whose current equipment_type differs from the
target, safe to re-run.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import Exercise, EquipmentType  # noqa: E402

# name -> new equipment_type
RETAG: dict[str, EquipmentType] = {
    # Needs literally nothing (pure bodyweight).
    "Ягодичный мост": EquipmentType.BODYWEIGHT,
    "Ягодичный мост на одной ноге": EquipmentType.BODYWEIGHT,
    "Пронация / супинация кисти": EquipmentType.BODYWEIGHT,
    # Needs a resistance band, TRX/rings, a table edge/pull-up bar, a med
    # ball, or a bench/step -- cheap, portable, or common household items,
    # not gym-specific equipment.
    "Антиротационный жим (Pallof)": EquipmentType.HOME,
    "Антиротационный жим (Pallof) + варианты": EquipmentType.HOME,
    "Антиротационный пресс с резиной (Pallof Press)": EquipmentType.HOME,
    "Приведение бедра с резиной": EquipmentType.HOME,
    "Тяга к лицу": EquipmentType.HOME,
    "Подтягивания (нейтральный хват)": EquipmentType.HOME,
    "Подтягивания на TRX / кольцах": EquipmentType.HOME,
    "Горизонтальная тяга (TRX / кольца / низкий блок)": EquipmentType.HOME,
    "Австралийские подтягивания": EquipmentType.HOME,
    "Ягодичный мост на лавке (shoulders elevated)": EquipmentType.HOME,
    "Хамстринг на одной ноге (Nordic / с темпом)": EquipmentType.HOME,
    "Бросок набивного мяча от груди": EquipmentType.HOME,
    "Зашагивание на тумбу": EquipmentType.HOME,
}


async def retag() -> None:
    async with AsyncSessionLocal() as session:
        exercises = (
            await session.execute(select(Exercise).where(Exercise.name.in_(RETAG)))
        ).scalars().all()
        by_name = {e.name: e for e in exercises}

        missing = set(RETAG) - set(by_name)
        if missing:
            print(f"WARNING: {len(missing)} name(s) not found in DB, skipping: {sorted(missing)}")

        updated = 0
        for name, new_tier in RETAG.items():
            exercise = by_name.get(name)
            if exercise is None:
                continue
            if exercise.equipment_type == new_tier:
                continue
            print(f"{name}: {exercise.equipment_type.value} -> {new_tier.value}")
            exercise.equipment_type = new_tier
            updated += 1

        await session.commit()
        print(f"Retagged {updated} exercise(s).")


if __name__ == "__main__":
    asyncio.run(retag())
