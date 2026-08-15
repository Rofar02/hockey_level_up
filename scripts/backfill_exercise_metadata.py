"""Backfill movement_pattern / stimulus_type / exercise_type for Phase 1.

One-off script (not a migration -- matches scripts/seed_exercises.py's own
convention for data, as opposed to schema, changes). Run manually:

    poetry run python scripts/backfill_exercise_metadata.py

Idempotent: re-running updates stimulus_type/exercise_type in place and
fully replaces each exercise's movement_pattern rows, so it's safe to run
again after editing CLASSIFICATION below.

Cross-checked 2026-08-15 against a 151-row snapshot of the dev database
(90-exercise import + 64 pre-existing, minus 3 name collisions that the
import skipped) -- see the review artifact for the full per-exercise
breakdown. Does NOT resolve the ~20 rows flagged as content
duplicates during that review (same exercise imported under two different
names) -- those still get classified like any other row here; merging or
deleting them is a separate decision, deliberately not bundled into this
backfill because deleting an Exercise row is destructive if it's already
referenced by a SessionBlock/SetCompletion somewhere.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import (  # noqa: E402
    Exercise,
    ExerciseMovementPattern,
    ExerciseType,
    MovementPattern,
    StimulusType,
)

# name -> (movement_patterns, stimulus_type, exercise_type)
CLASSIFICATION: dict[str, tuple[list[str], str, str]] = {
    '90/90 растяжка': (['hip_mobility'], 'mobility', 'duration'),
    'Dead Bug (Жук) + антиротация': (['core'], 'strength', 'sets_reps'),
    'Тяга к лицу': (['pull', 'shoulder_mobility'], 'strength', 'sets_reps'),
    'Антиротационный жим (Pallof)': (['core'], 'strength', 'sets_reps'),
    'Y на наклонной скамье': (['pull', 'shoulder_mobility'], 'strength', 'sets_reps'),
    'Австралийские подтягивания': (['pull'], 'strength', 'sets_reps'),
    'Антиротационный жим (Pallof) + варианты': (['core'], 'strength', 'sets_reps'),
    'Антиротационный пресс с резиной (Pallof Press)': (['core'], 'strength', 'sets_reps'),
    'Берд-дог': (['core'], 'strength', 'sets_reps'),
    'Берпи (умеренно)': (['squat', 'push', 'locomotion'], 'endurance', 'sets_reps'),
    'Боковая планка': (['core'], 'strength', 'duration'),
    'Боковой выпад': (['squat'], 'strength', 'sets_reps'),
    'Боковой прыжок / скачок': (['locomotion'], 'power', 'sets_reps'),
    'Боковой скачок': (['locomotion'], 'power', 'sets_reps'),
    'Болгарский присед': (['squat'], 'strength', 'sets_reps'),
    'Ведение мяча / шайбы клюшкой (off-ice)': ([], 'skill', 'duration'),
    'Велосипед интервалы': (['locomotion'], 'endurance', 'duration'),
    'Выпад назад с грифом (RPE 7-8)': (['squat'], 'strength', 'sets_reps'),
    'Голеностоп + резина': (['ankle_mobility'], 'mobility', 'sets_reps'),
    'Поза голубя': (['hip_mobility'], 'mobility', 'duration'),
    'Горизонтальная тяга (TRX / кольца / низкий блок)': (['pull'], 'strength', 'sets_reps'),
    'Гребля (Concept2 или тренажёр)': (['pull'], 'endurance', 'duration'),
    'Динамический выпад + открытие/закрытие бедра': (['squat', 'hip_mobility'], 'mobility', 'sets_reps'),
    'Дровосек': (['rotation'], 'power', 'sets_reps'),
    'Жим гантелей лёжа': (['push'], 'strength', 'sets_reps'),
    'Жим гантелей на наклонной скамье': (['push'], 'strength', 'sets_reps'),
    'Жим гантелей одной рукой': (['push'], 'strength', 'sets_reps'),
    'Жим лендмайн / антиротационный жим': (['push', 'rotation'], 'strength', 'sets_reps'),
    'Жим лёжа с темпом 6-0-0-0 (RPE 8)': (['push'], 'strength', 'sets_reps'),
    'Жим штанги лёжа': (['push'], 'strength', 'sets_reps'),
    'Жук + рол / статика': (['core'], 'strength', 'sets_reps'),
    'Зашагивание на тумбу': (['squat'], 'strength', 'sets_reps'),
    'Изометрический сплит-присед (макс. усилие)': (['squat'], 'strength', 'duration'),
    'Имитация броска с резиной': (['rotation'], 'power', 'sets_reps'),
    'Комплекс голеностопа': (['ankle_mobility'], 'mobility', 'duration'),
    'Копенгаген-планка (короткий рычаг)': (['core'], 'strength', 'duration'),
    'Кошка-корова + дыхание': (['core'], 'mobility', 'duration'),
    'Круги руками + лопатки': (['shoulder_mobility'], 'mobility', 'duration'),
    'Латеральный выпад с гантелью на слайде': (['squat'], 'strength', 'sets_reps'),
    'Марш с санями': (['locomotion'], 'power', 'duration'),
    'Обратный выпад': (['squat'], 'strength', 'sets_reps'),
    'Обратный дровосек': (['rotation'], 'power', 'sets_reps'),
    'Отведение бедра с резиной': (['hip_mobility'], 'mobility', 'sets_reps'),
    'Отжимания': (['push'], 'strength', 'sets_reps'),
    'Отжимания на брусьях (если есть)': (['push'], 'strength', 'sets_reps'),
    'Отжимания с ногами на возвышении': (['push'], 'strength', 'sets_reps'),
    'Планка': (['core'], 'strength', 'duration'),
    'Подтягивания (нейтральный хват)': (['pull'], 'strength', 'sets_reps'),
    'Подтягивания на TRX / кольцах': (['pull'], 'strength', 'sets_reps'),
    'Подъём таза стоя (Hip Thrust standing / Good Morning лёгкий)': (['hip_hinge'], 'strength', 'sets_reps'),
    'Поза голубя (активация перед игрой)': (['hip_mobility'], 'mobility', 'duration'),
    'Приведение бедра с резиной': (['hip_mobility'], 'mobility', 'sets_reps'),
    'Присед со штангой / гоблет-присед': (['squat'], 'strength', 'sets_reps'),
    'Пронация / супинация кисти': (['wrist_mobility'], 'mobility', 'sets_reps'),
    'Прыжки через барьеры / линии': (['locomotion'], 'power', 'sets_reps'),
    'Прыжок барьер 1 нога + пауза': (['locomotion'], 'power', 'sets_reps'),
    'Прыжок в длину с места + пауза': (['locomotion'], 'power', 'sets_reps'),
    'Прыжок на одной ноге (на месте / вперёд)': (['locomotion'], 'power', 'sets_reps'),
    'Прыжок на тумбу (Box Jump)': (['locomotion'], 'power', 'sets_reps'),
    'Прыжок на тумбу на одной ноге': (['locomotion'], 'power', 'sets_reps'),
    'Прыжок на тумбу 1 нога боком': (['locomotion'], 'power', 'sets_reps'),
    'Прыжок на тумбу 1 нога лицом': (['locomotion'], 'power', 'sets_reps'),
    'Раскатка на ролике / ab wheel': (['core'], 'strength', 'sets_reps'),
    'Роллаут': (['core'], 'strength', 'sets_reps'),
    'Ротационный бросок медбола': (['rotation'], 'power', 'sets_reps'),
    'Ротация бедра (внутренняя/наружная)': (['hip_mobility'], 'mobility', 'sets_reps'),
    'Румынская тяга': (['hip_hinge'], 'strength', 'sets_reps'),
    'Румынская тяга на одной ноге': (['hip_hinge'], 'strength', 'sets_reps'),
    'Румынская тяга с гантелями (темп 6-0-0-0)': (['hip_hinge'], 'strength', 'sets_reps'),
    'Русский твист (аккуратно)': (['rotation', 'core'], 'strength', 'sets_reps'),
    'Сгибание-разгибание голеностопа': (['ankle_mobility'], 'mobility', 'sets_reps'),
    'Скакалка': (['locomotion'], 'endurance', 'duration'),
    'Скорпион / грудной отдел': (['rotation', 'hip_mobility'], 'mobility', 'duration'),
    'Слалом с мячом / шайбой': (['locomotion'], 'skill', 'duration'),
    'Слэм медбола': (['core'], 'power', 'sets_reps'),
    'Сплит-присед': (['squat'], 'strength', 'sets_reps'),
    'Короткий спринт': (['locomotion'], 'power', 'sets_reps'),
    'Спрыгивание с тумбы + стабилизация': (['locomotion'], 'power', 'sets_reps'),
    'Теневой бой / имитация борьбы': (['core'], 'skill', 'duration'),
    'Тяга верхнего блока / горизонтального блока': (['pull'], 'strength', 'sets_reps'),
    'Тяга гантели в наклоне (Single-Arm Dumbbell Row)': (['pull'], 'strength', 'sets_reps'),
    'Тяга резины к поясу / лицу': (['pull'], 'strength', 'sets_reps'),
    'Тяга штанги в наклоне': (['pull'], 'strength', 'sets_reps'),
    'Фермерская прогулка': (['locomotion', 'core'], 'strength', 'duration'),
    'Фронтальный присед (эксцентрика)': (['squat'], 'strength', 'sets_reps'),
    'Хамстринг на одной ноге (Nordic / с темпом)': (['hip_hinge'], 'strength', 'sets_reps'),
    'Челночный бег 5-10-5': (['locomotion'], 'power', 'sets_reps'),
    'Ягодичный мост': (['hip_hinge'], 'strength', 'sets_reps'),
    'Ягодичный мост на лавке (shoulders elevated)': (['hip_hinge'], 'strength', 'sets_reps'),
    'Ягодичный мост на одной ноге': (['hip_hinge'], 'strength', 'sets_reps'),
    'Суставная разминка (вращения)': (['hip_mobility', 'shoulder_mobility'], 'mobility', 'duration'),
    'Скакалка для разогрева': (['locomotion'], 'endurance', 'duration'),
    'Динамическая растяжка ног': (['hip_mobility'], 'mobility', 'duration'),
    'Приставные шаги в стойке': (['locomotion'], 'skill', 'duration'),
    'Лёгкое катание для разогрева': (['locomotion'], 'endurance', 'duration'),
    'Становая тяга': (['hip_hinge'], 'strength', 'sets_reps'),
    'Выпады с гантелями': (['squat'], 'strength', 'sets_reps'),
    'Приседания с весом тела': (['squat'], 'strength', 'sets_reps'),
    'Прыжки на тумбу': (['locomotion'], 'power', 'sets_reps'),
    'Координационная лестница': (['locomotion'], 'skill', 'duration'),
    'Спринты с ускорением на льду': (['locomotion'], 'power', 'sets_reps'),
    'Малые игры 2х2 на льду': (['locomotion'], 'skill', 'duration'),
    'Обводка в ограниченном пространстве': ([], 'skill', 'duration'),
    'Гребной тренажёр интервалами': (['pull'], 'endurance', 'duration'),
    'Бёрпи': (['squat', 'push', 'locomotion'], 'endurance', 'sets_reps'),
    'Растяжка мышц ног после тренировки': (['hip_mobility'], 'mobility', 'duration'),
    'Растяжка плечевого пояса и спины': (['shoulder_mobility'], 'mobility', 'duration'),
    'Миофасциальный релиз на роллере': ([], 'mobility', 'duration'),
    'Лёгкое катание для заминки': (['locomotion'], 'endurance', 'duration'),
    'Прыжки в сторону (имитация конькобежного бега)': (['locomotion'], 'power', 'sets_reps'),
    'Жим гантелей от груди': (['push'], 'strength', 'sets_reps'),
    'Бросок набивного мяча от груди': (['push'], 'power', 'sets_reps'),
    'Отжимания с хлопком': (['push'], 'power', 'sets_reps'),
    'Кросс (бег на длинную дистанцию)': (['locomotion'], 'endurance', 'duration'),
    'Лягушка (прыжковые приседания)': (['squat', 'locomotion'], 'power', 'sets_reps'),
    'Интервальный спринт 10×30м': (['locomotion'], 'power', 'sets_reps'),
    'Лестница для ног (agility ladder)': (['locomotion'], 'skill', 'duration'),
    'Ловля теннисного мяча на реакцию': ([], 'skill', 'duration'),
    'Жонглирование двумя мячами': ([], 'skill', 'duration'),
    'Присед на одной ноге (пистолетик)': (['squat'], 'strength', 'sets_reps'),
    'Планка на нестабильной поверхности': (['core'], 'strength', 'duration'),
    'Стойка на одной ноге с закрытыми глазами': ([], 'skill', 'duration'),
    'Комплекс суставной гимнастики': (['hip_mobility', 'shoulder_mobility'], 'mobility', 'duration'),
    'Растяжка на подвижность бедра': (['hip_mobility'], 'mobility', 'duration'),
    'Ведение теннисного мяча клюшкой на асфальте': ([], 'skill', 'duration'),
    'Ведение мяча между конусами': (['locomotion'], 'skill', 'duration'),
    'Подбрасывание шайбы на крюке клюшки': ([], 'skill', 'duration'),
    'Катание спиной вперёд': (['locomotion'], 'skill', 'duration'),
    'Слалом с шайбой между конусами': (['locomotion'], 'skill', 'duration'),
    'Малые игры 3х3 на льду': (['locomotion'], 'skill', 'duration'),
    'Суставная гимнастика': (['hip_mobility', 'shoulder_mobility'], 'mobility', 'duration'),
    'Бег на месте': (['locomotion'], 'endurance', 'duration'),
    'Динамическая растяжка (махи)': (['hip_mobility'], 'mobility', 'duration'),
    'Прыжки на скакалке (лёгкий темп)': (['locomotion'], 'endurance', 'duration'),
    'Активация плеч эспандером': (['shoulder_mobility'], 'mobility', 'sets_reps'),
    'Велотренажёр (лёгкая интенсивность)': (['locomotion'], 'endurance', 'duration'),
    'Гребной тренажёр (лёгкий темп)': (['pull'], 'endurance', 'duration'),
    'Работа с пустым грифом': (['squat'], 'strength', 'sets_reps'),
    'Динамическая растяжка на льду перед стартом': (['hip_mobility'], 'mobility', 'duration'),
    'Катание спиной вперёд в медленном темпе': (['locomotion'], 'skill', 'duration'),
    'Растяжка подколенных сухожилий стоя': (['hip_mobility'], 'mobility', 'duration'),
    'Растяжка квадрицепса стоя': (['hip_mobility'], 'mobility', 'duration'),
    'Кошка-корова': (['core'], 'mobility', 'duration'),
    'Складка сидя на коврике': (['hip_mobility'], 'mobility', 'duration'),
    'Растяжка голени у стены': (['ankle_mobility'], 'mobility', 'duration'),
    'Растяжка с полотенцем (подколенные)': (['hip_mobility'], 'mobility', 'duration'),
    'Растяжка на мате в зале': (['hip_mobility'], 'mobility', 'duration'),
    'Растяжка с использованием скамьи': (['hip_mobility'], 'mobility', 'duration'),
    'Растяжка у борта': (['hip_mobility'], 'mobility', 'duration'),
    'Растяжка': ([], 'mobility', 'duration'),
    'Приседания со штангой': (['squat'], 'strength', 'sets_reps'),
}


async def backfill() -> None:
    async with AsyncSessionLocal() as session:
        exercises = (await session.execute(select(Exercise))).scalars().all()
        by_name = {e.name: e for e in exercises}

        missing = set(CLASSIFICATION) - set(by_name)
        extra = set(by_name) - set(CLASSIFICATION)
        if missing:
            print(f"WARNING: {len(missing)} classified name(s) not found in DB, skipping: {sorted(missing)}")
        if extra:
            print(f"WARNING: {len(extra)} DB exercise(s) have no classification, left untouched: {sorted(extra)}")

        updated = 0
        pattern_rows_written = 0
        for name, (patterns, stimulus, etype) in CLASSIFICATION.items():
            exercise = by_name.get(name)
            if exercise is None:
                continue

            changed = (
                exercise.stimulus_type != StimulusType(stimulus)
                or exercise.exercise_type != ExerciseType(etype)
            )
            exercise.stimulus_type = StimulusType(stimulus)
            exercise.exercise_type = ExerciseType(etype)
            if changed:
                updated += 1

            # Full-replace, matching how ExerciseMovementPattern is documented
            # to be managed (see app/models/exercise.py) -- simpler than diffing
            # against whatever rows (if any) already exist, and this script only
            # ever runs against a catalog where the table starts empty or is
            # being deliberately re-synced to CLASSIFICATION.
            await session.execute(
                delete(ExerciseMovementPattern).where(
                    ExerciseMovementPattern.exercise_id == exercise.id
                )
            )
            for pattern in patterns:
                session.add(
                    ExerciseMovementPattern(
                        exercise_id=exercise.id,
                        movement_pattern=MovementPattern(pattern),
                    )
                )
                pattern_rows_written += 1

        await session.commit()
        print(f"Classified {len(CLASSIFICATION)} exercise(s), updated {updated} changed row(s).")
        print(f"Wrote {pattern_rows_written} movement_pattern row(s) (full replace).")


if __name__ == "__main__":
    asyncio.run(backfill())
