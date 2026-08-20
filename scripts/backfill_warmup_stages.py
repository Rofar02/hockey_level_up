"""Backfill warmup_stage for every WARMUP-phase exercise (2026-08-18 planning
session: "always a proper warmup complex" -- soft tissue prep, raise, joint
mobility, activation, sport-specific dynamic movement, in that order, see
WarmupStage/WARMUP_STAGE_ORDER).

Cross-checked against a 47-row snapshot of the dev database's WARMUP/off_ice
catalog on 2026-08-18. Every stage except SOFT_TISSUE has bodyweight-tier
coverage (checked at classification time) -- SOFT_TISSUE is foam roller/
ball work, which genuinely has no zero-equipment substitute, so it's the
one stage that's simply absent from a bodyweight-only user's warmup
complex, not something patched around.

Not a migration -- run manually:

    poetry run python scripts/backfill_warmup_stages.py

Idempotent: only writes rows whose current warmup_stage differs from the
target, safe to re-run after editing CLASSIFICATION below.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import Exercise, TrainingPhase, WarmupStage  # noqa: E402

# name -> WarmupStage value
CLASSIFICATION: dict[str, str] = {
    # -- soft_tissue: foam roller / ball, no bodyweight-only equivalent --
    "Боковая поверхность бедра - ролл": "soft_tissue",
    "Боковая часть голени - мяч": "soft_tissue",
    "Внутренняя часть лопатки - ролл": "soft_tissue",
    "Грудь у стены - мяч": "soft_tissue",
    "Задняя поверхность бедра (бицепс бедра) - ролл": "soft_tissue",
    "Задняя часть приводящих на тумбе": "soft_tissue",
    "Наружная часть лопатки - ролл": "soft_tissue",
    "Передняя поверхность бедра (квадрицепс) - ролл": "soft_tissue",
    "Поясница - ролл": "soft_tissue",
    "Приводящие мышцы - ролл": "soft_tissue",
    "Стопа - мяч": "soft_tissue",
    "Ягодицы - ролл": "soft_tissue",

    # -- raise: pulse/temperature up, no joint/muscle-specific work --
    "Бег на месте": "raise",
    "Приставные шаги в стойке": "raise",
    "Велотренажёр (лёгкая интенсивность)": "raise",
    "Гребной тренажёр (лёгкий темп)": "raise",
    "Прыжки на скакалке (лёгкий темп)": "raise",
    "Скакалка для разогрева": "raise",

    # -- joint_mobility: moving a joint through its range, not activating a
    # specific muscle against resistance --
    "Голеностоп у стены (ПНФ)": "joint_mobility",
    "Диагональная дуга рукой лёжа на боку": "joint_mobility",
    "Йога-отжимание": "joint_mobility",
    "Мобилизация квадрицепса в полуприседе на одном колене": "joint_mobility",
    "Мобильность голеностопа у стены": "joint_mobility",
    "Перевёрнутый reach (перевёрнутая тяга)": "joint_mobility",
    "Суставная гимнастика": "joint_mobility",
    "Суставная разминка (вращения)": "joint_mobility",
    "Комплекс суставной гимнастики": "joint_mobility",
    "Комплекс голеностопа": "joint_mobility",
    "Поза голубя (активация перед игрой)": "joint_mobility",
    "Ротация бедра (внутренняя/наружная)": "joint_mobility",
    "Сгибание-разгибание голеностопа": "joint_mobility",

    # -- activation: contracting a specific muscle against resistance
    # (band, bodyweight-against-gravity) to "switch it on" before it's
    # needed in MAIN --
    "Жук (Dead Bug)": "activation",
    "Разгибание голеностопа с опорой о стену": "activation",
    "Активация плеч эспандером": "activation",
    "Боковая ходьба с мини-бэндом": "activation",
    "Голеностоп + резина": "activation",
    "Лежачее подтягивание поясничной мышцы с мини-бэндом": "activation",
    "Марш ягодицами у стены с мини-бэндом + изометрия": "activation",
    "Отведение бедра с резиной": "activation",
    "Сведение лопаток с резиной в полуприседе на колене": "activation",

    # -- dynamic: full-body movement close to what MAIN is about to ask
    # for, last stage before the real work starts --
    "Spiderman + ротация грудного отдела": "dynamic",
    "Боковой выпад на колене + наружная ротация": "dynamic",
    "Боковой присед с касанием внутренней части стопы": "dynamic",
    "Диагональное раскачивание таза с выходом в шаг": "dynamic",
    "Динамическая растяжка (махи)": "dynamic",
    "Динамическая растяжка ног": "dynamic",
    "Динамический выпад + открытие/закрытие бедра": "dynamic",
    "Работа с пустым грифом": "dynamic",

    # -- on-ice warmup (category=on_ice, no equipment gate applies) --
    "Лёгкое катание для разогрева": "raise",
    "Динамическая растяжка на льду перед стартом": "dynamic",
    "Катание спиной вперёд в медленном темпе": "dynamic",
}


async def backfill() -> None:
    async with AsyncSessionLocal() as session:
        exercises = (
            await session.execute(select(Exercise).where(Exercise.phase == TrainingPhase.WARMUP))
        ).scalars().all()
        by_name = {e.name: e for e in exercises}

        missing = set(CLASSIFICATION) - set(by_name)
        extra = set(by_name) - set(CLASSIFICATION)
        if missing:
            print(f"WARNING: {len(missing)} classified name(s) not found in DB, skipping: {sorted(missing)}")
        if extra:
            print(f"WARNING: {len(extra)} WARMUP exercise(s) have no stage classification, left untouched: {sorted(extra)}")

        updated = 0
        for name, stage in CLASSIFICATION.items():
            exercise = by_name.get(name)
            if exercise is None:
                continue
            target = WarmupStage(stage)
            if exercise.warmup_stage == target:
                continue
            exercise.warmup_stage = target
            updated += 1

        await session.commit()
        print(f"Classified {len(CLASSIFICATION)} exercise(s), updated {updated} changed row(s).")


if __name__ == "__main__":
    asyncio.run(backfill())
