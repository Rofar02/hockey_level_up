"""One-off backfill (Phase 1 follow-up): sets/reps/duration_seconds for the
54 exercises that had none of target_sets/target_reps/target_duration_seconds
set after the Phase 1 metadata backfill (see
scripts/backfill_exercise_metadata.py). Estimated by pattern-matching
existing catalog conventions for the same stimulus_type/difficulty_level,
not sourced from a real training program -- flagged to the product owner
for revision, not a substitute for one. Same idempotent full-overwrite shape
as backfill_exercise_metadata.py: reruns after editing VOLUME below are safe.

Historical note (Phase: П.1 double progression): target_reps was later
replaced by a rep_range_min/rep_range_max pair -- see
scripts/backfill_exercise_rep_ranges.py, which is what actually populates
reps for sets_reps exercises now. This script no longer writes reps at all;
the REPS values in VOLUME below are kept only as the original one-off
per-exercise draft data this file was seeded with, in case they're useful
input the next time someone hand-tunes a specific exercise's rep range.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import Exercise  # noqa: E402

# name -> (target_sets, REPS -- no longer written, see module docstring, target_duration_seconds)
VOLUME: dict[str, tuple[int | None, int | None, int | None]] = {
    "Активация плеч эспандером": (2, 15, None),
    "Бег на месте": (None, None, 60),
    "Бросок набивного мяча от груди": (3, 8, None),
    "Бёрпи": (3, 12, None),
    "Ведение мяча между конусами": (None, None, 180),
    "Ведение теннисного мяча клюшкой на асфальте": (None, None, 180),
    "Велотренажёр (лёгкая интенсивность)": (None, None, 300),
    "Гребной тренажёр (лёгкий темп)": (None, None, 300),
    "Гребной тренажёр интервалами": (None, None, 600),
    "Динамическая растяжка (махи)": (None, None, 60),
    "Динамическая растяжка на льду перед стартом": (None, None, 120),
    "Динамическая растяжка ног": (None, None, 60),
    "Жим гантелей от груди": (3, 8, None),
    "Жонглирование двумя мячами": (None, None, 120),
    "Интервальный спринт 10×30м": (10, 1, None),
    "Катание спиной вперёд в медленном темпе": (None, None, 120),
    "Комплекс суставной гимнастики": (None, None, 180),
    "Координационная лестница": (None, None, 180),
    "Кошка-корова": (None, None, 60),
    "Кросс (бег на длинную дистанцию)": (None, None, 1200),
    "Лестница для ног (agility ladder)": (None, None, 180),
    "Ловля теннисного мяча на реакцию": (None, None, 120),
    "Лягушка (прыжковые приседания)": (3, 12, None),
    "Лёгкое катание для заминки": (None, None, 300),
    "Лёгкое катание для разогрева": (None, None, 300),
    "Малые игры 2х2 на льду": (None, None, 600),
    "Малые игры 3х3 на льду": (None, None, 600),
    "Миофасциальный релиз на роллере": (None, None, 120),
    "Обводка в ограниченном пространстве": (None, None, 180),
    "Отжимания с хлопком": (3, 6, None),
    "Подбрасывание шайбы на крюке клюшки": (None, None, 120),
    "Присед на одной ноге (пистолетик)": (3, 5, None),
    "Приставные шаги в стойке": (None, None, 60),
    "Прыжки в сторону (имитация конькобежного бега)": (3, 10, None),
    "Прыжки на скакалке (лёгкий темп)": (None, None, 120),
    "Прыжки на тумбу": (3, 6, None),
    "Работа с пустым грифом": (2, 10, None),
    "Растяжка голени у стены": (None, None, 30),
    "Растяжка квадрицепса стоя": (None, None, 30),
    "Растяжка мышц ног после тренировки": (None, None, 30),
    "Растяжка на мате в зале": (None, None, 60),
    "Растяжка на подвижность бедра": (None, None, 120),
    "Растяжка плечевого пояса и спины": (None, None, 30),
    "Растяжка подколенных сухожилий стоя": (None, None, 30),
    "Растяжка с использованием скамьи": (None, None, 30),
    "Растяжка с полотенцем (подколенные)": (None, None, 30),
    "Скакалка для разогрева": (None, None, 120),
    "Складка сидя на коврике": (None, None, 30),
    "Слалом с шайбой между конусами": (None, None, 180),
    "Спринты с ускорением на льду": (6, 1, None),
    "Становая тяга": (3, 5, None),
    "Стойка на одной ноге с закрытыми глазами": (None, None, 60),
    "Суставная гимнастика": (None, None, 180),
    "Суставная разминка (вращения)": (None, None, 180),
}


async def backfill() -> None:
    async with AsyncSessionLocal() as session:
        exercises = (await session.execute(select(Exercise))).scalars().all()
        by_name = {e.name: e for e in exercises}

        missing = set(VOLUME) - set(by_name)
        if missing:
            print(f"WARNING: {len(missing)} name(s) not found in DB, skipping: {sorted(missing)}")

        updated = 0
        for name, (sets, _reps, duration) in VOLUME.items():
            exercise = by_name.get(name)
            if exercise is None:
                continue
            exercise.target_sets = sets
            exercise.target_duration_seconds = duration
            updated += 1

        await session.commit()
        print(f"Updated {updated} exercise(s) with draft volume data.")


if __name__ == "__main__":
    asyncio.run(backfill())
