"""One-off seed script for the exercise catalog (Phase 1).

Not a migration -- run manually whenever the catalog needs (re)seeding:

    poetry run python scripts/seed_exercises.py

Idempotent: skips any exercise whose `name` already exists.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import Exercise  # noqa: E402

EXERCISES: list[dict] = [
    # -- warmup --
    {
        "name": "Суставная разминка (вращения)",
        "category": "off_ice",
        "phase": "warmup",
        "target_stat": "agility",
        "difficulty_level": 1,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Скакалка для разогрева",
        "category": "off_ice",
        "phase": "warmup",
        "target_stat": "endurance",
        "difficulty_level": 2,
        "equipment_type": "home",
    },
    {
        "name": "Динамическая растяжка ног",
        "category": "off_ice",
        "phase": "warmup",
        "target_stat": "agility",
        "difficulty_level": 1,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Приставные шаги в стойке",
        "category": "off_ice",
        "phase": "warmup",
        "target_stat": "agility",
        "difficulty_level": 2,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Лёгкое катание для разогрева",
        "category": "on_ice",
        "phase": "warmup",
        "target_stat": "endurance",
        "difficulty_level": 1,
        "equipment_type": "bodyweight",
    },
    # -- main --
    {
        "name": "Приседания со штангой",
        "category": "off_ice",
        "phase": "main",
        "target_stat": "strength",
        "difficulty_level": 4,
        "equipment_type": "gym",
    },
    {
        "name": "Становая тяга",
        "category": "off_ice",
        "phase": "main",
        "target_stat": "strength",
        "difficulty_level": 5,
        "equipment_type": "gym",
    },
    {
        "name": "Выпады с гантелями",
        "category": "off_ice",
        "phase": "main",
        "target_stat": "strength",
        "difficulty_level": 3,
        "equipment_type": "home",
    },
    {
        "name": "Приседания с весом тела",
        "category": "off_ice",
        "phase": "main",
        "target_stat": "strength",
        "difficulty_level": 2,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Прыжки на тумбу",
        "category": "off_ice",
        "phase": "main",
        "target_stat": "agility",
        "difficulty_level": 4,
        "equipment_type": "gym",
    },
    {
        "name": "Координационная лестница",
        "category": "off_ice",
        "phase": "main",
        "target_stat": "agility",
        "difficulty_level": 3,
        "equipment_type": "home",
    },
    {
        "name": "Спринты с ускорением на льду",
        "category": "on_ice",
        "phase": "main",
        "target_stat": "agility",
        "difficulty_level": 4,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Малые игры 2х2 на льду",
        "category": "on_ice",
        "phase": "main",
        "target_stat": "intellect",
        "difficulty_level": 3,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Обводка в ограниченном пространстве",
        "category": "on_ice",
        "phase": "main",
        "target_stat": "intellect",
        "difficulty_level": 2,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Гребной тренажёр интервалами",
        "category": "off_ice",
        "phase": "main",
        "target_stat": "endurance",
        "difficulty_level": 3,
        "equipment_type": "gym",
    },
    {
        "name": "Бёрпи",
        "category": "off_ice",
        "phase": "main",
        "target_stat": "endurance",
        "difficulty_level": 3,
        "equipment_type": "bodyweight",
    },
    # -- cooldown --
    {
        "name": "Растяжка мышц ног после тренировки",
        "category": "off_ice",
        "phase": "cooldown",
        "target_stat": "agility",
        "difficulty_level": 1,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Растяжка плечевого пояса и спины",
        "category": "off_ice",
        "phase": "cooldown",
        "target_stat": "agility",
        "difficulty_level": 1,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Миофасциальный релиз на роллере",
        "category": "off_ice",
        "phase": "cooldown",
        "target_stat": "endurance",
        "difficulty_level": 1,
        "equipment_type": "home",
    },
    {
        "name": "Лёгкое катание для заминки",
        "category": "on_ice",
        "phase": "cooldown",
        "target_stat": "endurance",
        "difficulty_level": 1,
        "equipment_type": "bodyweight",
    },
]


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        existing_names = set(
            (await session.execute(select(Exercise.name))).scalars().all()
        )

        created = 0
        for data in EXERCISES:
            if data["name"] in existing_names:
                continue
            session.add(Exercise(**data))
            created += 1

        await session.commit()
        print(f"Seeded {created} new exercise(s), skipped {len(EXERCISES) - created} existing.")


if __name__ == "__main__":
    asyncio.run(seed())
