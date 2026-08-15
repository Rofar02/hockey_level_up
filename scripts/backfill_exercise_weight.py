"""One-off backfill (Phase 1 follow-up): tracks_weight/bodyweight_ratio for
off_ice MAIN exercises whose name suggests external load (barbell/dumbbell/
cable/band) but that had tracks_weight=false. Ratios are estimated by
pattern-matching movement type against the few already-calibrated exercises
in the catalog (bench press dumbbell=0.35, barbell squat=0.75, RDL=1.0),
NOT sourced from a real training program -- a wrong ratio here directly
drives WeightSuggestionService's first-ever weight suggestion for a real
athlete, so this is flagged to the product owner for revision, not a
substitute for one. Band/cable-resisted exercises (Pallof press, face pull,
band row) and pure-bodyweight movements (push-ups, pistol squat) are
deliberately left tracks_weight=false -- their resistance doesn't scale as
an honest fraction of bodyweight. Same idempotent full-overwrite shape as
backfill_exercise_metadata.py: reruns after editing WEIGHT below are safe.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import Exercise  # noqa: E402

# name -> (tracks_weight, bodyweight_ratio) -- ratio is None wherever
# tracks_weight is recommended False.
WEIGHT: dict[str, tuple[bool, float | None]] = {
    "Антиротационный жим (Pallof)": (False, None),
    "Антиротационный жим (Pallof) + варианты": (False, None),
    "Боковой выпад": (True, 0.30),
    "Болгарский присед": (True, 0.30),
    "Выпад назад с грифом (RPE 7-8)": (True, 0.40),
    "Выпады с гантелями": (True, 0.30),
    "Горизонтальная тяга (TRX / кольца / низкий блок)": (False, None),
    "Жим гантелей на наклонной скамье": (True, 0.30),
    "Жим гантелей одной рукой": (True, 0.18),
    "Жим гантелей от груди": (True, 0.35),
    "Жим лендмайн / антиротационный жим": (True, 0.30),
    "Жим лёжа с темпом 6-0-0-0 (RPE 8)": (True, 0.45),
    "Жим штанги лёжа": (True, 0.50),
    "Изометрический сплит-присед (макс. усилие)": (False, None),
    "Латеральный выпад с гантелью на слайде": (True, 0.25),
    "Лягушка (прыжковые приседания)": (False, None),
    "Обратный выпад": (True, 0.30),
    "Отжимания": (False, None),
    "Отжимания на брусьях (если есть)": (False, None),
    "Отжимания с ногами на возвышении": (False, None),
    "Отжимания с хлопком": (False, None),
    "Подъём таза стоя (Hip Thrust standing / Good Morning лёгкий)": (True, 0.35),
    "Присед на одной ноге (пистолетик)": (False, None),
    "Присед со штангой / гоблет-присед": (True, 0.65),
    "Приседания с весом тела": (False, None),
    "Румынская тяга на одной ноге": (True, 0.35),
    "Румынская тяга с гантелями (темп 6-0-0-0)": (True, 0.60),
    "Сплит-присед": (True, 0.25),
    "Становая тяга": (True, 1.10),
    "Тяга верхнего блока / горизонтального блока": (True, 0.45),
    "Тяга гантели в наклоне (Single-Arm Dumbbell Row)": (True, 0.20),
    "Тяга к лицу": (False, None),
    "Тяга резины к поясу / лицу": (False, None),
    "Тяга штанги в наклоне": (True, 0.50),
    "Фронтальный присед (эксцентрика)": (True, 0.55),
}


async def backfill() -> None:
    async with AsyncSessionLocal() as session:
        exercises = (await session.execute(select(Exercise))).scalars().all()
        by_name = {e.name: e for e in exercises}

        missing = set(WEIGHT) - set(by_name)
        if missing:
            print(f"WARNING: {len(missing)} name(s) not found in DB, skipping: {sorted(missing)}")

        updated = 0
        for name, (tracks_weight, ratio) in WEIGHT.items():
            exercise = by_name.get(name)
            if exercise is None:
                continue
            exercise.tracks_weight = tracks_weight
            exercise.bodyweight_ratio = ratio
            updated += 1

        await session.commit()
        print(f"Updated {updated} exercise(s) with draft tracks_weight/bodyweight_ratio.")


if __name__ == "__main__":
    asyncio.run(backfill())
