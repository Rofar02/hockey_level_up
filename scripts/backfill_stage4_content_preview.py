"""Stage 4 (2026-08-20 planning session) content preview backfill -- NOT
final content. Product owner explicitly asked for a fast, template-based
pass across the whole catalog to preview how the new muscle-group tagging
and a filled-in "Техника" tab will actually look in the app, before doing
real per-exercise content work by hand.

Two things this does, both idempotent (safe to re-run):

1. Muscle groups: assigns a weighted ExerciseMuscleGroup set to every
   exercise, derived from its already-tagged MovementPattern(s) via
   _MUSCLE_WEIGHTS_BY_PATTERN below (real anatomical mapping, not
   per-exercise -- multi-pattern exercises get an equal-weighted average
   across their patterns, always summing to <=1.0). Overwrites any
   existing muscle-group tags -- there were none anywhere in the real
   catalog as of 2026-08-20, so this can't clobber real data.

2. Description/technique text: ONLY overwrites the 40 real "Заглушка:
   описание будет добавлено позже" stub rows, via _TECHNIQUE_BY_PATTERN's
   generic per-pattern cues. Deliberately does NOT touch the 170 exercises
   that already have real authored descriptions -- checked before writing
   this, those are genuine content, not filler, and overwriting them with
   a generic template would be a real content loss, not a preview.

Video is intentionally left alone -- ExerciseTechnique.tsx now shows a
placeholder screen client-side whenever no video is set, no DB change
needed for that part.

Run: docker compose exec backend python scripts/backfill_stage4_content_preview.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import (  # noqa: E402
    Exercise,
    ExerciseMovementPattern,
    ExerciseMuscleGroup,
    MovementPattern,
    MuscleGroup,
)

_STUB_PREFIX = "Заглушка"

# Each pattern's own weights sum to 1.0 -- a multi-pattern exercise
# averages its patterns' dicts equally, which also sums to 1.0 (no
# renormalization needed). WRIST_MOBILITY has no real forearm/wrist entry
# in MuscleGroup's 8 anatomical values -- SHOULDERS is the nearest
# modeled group, not a precise match.
_MUSCLE_WEIGHTS_BY_PATTERN: dict[MovementPattern, dict[MuscleGroup, float]] = {
    MovementPattern.SQUAT: {MuscleGroup.QUADS: 0.5, MuscleGroup.GLUTES: 0.3, MuscleGroup.CORE: 0.2},
    MovementPattern.HIP_HINGE: {
        MuscleGroup.HAMSTRINGS: 0.4, MuscleGroup.GLUTES: 0.4, MuscleGroup.BACK: 0.2,
    },
    MovementPattern.PUSH: {MuscleGroup.CHEST: 0.5, MuscleGroup.SHOULDERS: 0.4, MuscleGroup.CORE: 0.1},
    MovementPattern.PULL: {MuscleGroup.BACK: 0.6, MuscleGroup.SHOULDERS: 0.2, MuscleGroup.CORE: 0.2},
    MovementPattern.ROTATION: {MuscleGroup.CORE: 1.0},
    MovementPattern.CORE: {MuscleGroup.CORE: 1.0},
    MovementPattern.ANKLE_MOBILITY: {MuscleGroup.CALVES: 1.0},
    MovementPattern.HIP_MOBILITY: {
        MuscleGroup.GLUTES: 0.5, MuscleGroup.HAMSTRINGS: 0.3, MuscleGroup.QUADS: 0.2,
    },
    MovementPattern.SHOULDER_MOBILITY: {MuscleGroup.SHOULDERS: 1.0},
    MovementPattern.WRIST_MOBILITY: {MuscleGroup.SHOULDERS: 1.0},
    MovementPattern.LOCOMOTION: {
        MuscleGroup.QUADS: 0.4, MuscleGroup.GLUTES: 0.3, MuscleGroup.CALVES: 0.3,
    },
    MovementPattern.STICK_HANDLING: {MuscleGroup.SHOULDERS: 0.5, MuscleGroup.CORE: 0.5},
    MovementPattern.COORDINATION: {
        MuscleGroup.CORE: 0.5, MuscleGroup.QUADS: 0.25, MuscleGroup.CALVES: 0.25,
    },
}

_TECHNIQUE_BY_PATTERN: dict[MovementPattern, str] = {
    MovementPattern.SQUAT: (
        "Базовое упражнение на паттерн приседа — развивает силу квадрицепсов и "
        "ягодичных мышц.\n\nТехника: стопы на ширине плеч, носки слегка развёрнуты "
        "наружу, спина прямая на всём протяжении движения. Опускайтесь до "
        "комфортной глубины, колени двигаются в одном направлении с носками. "
        "Вставайте, отталкиваясь пятками, полностью выпрямляя корпус в верхней точке."
    ),
    MovementPattern.HIP_HINGE: (
        "Упражнение на паттерн тазобедренного шарнира — развивает заднюю "
        "поверхность бедра, ягодицы и поясницу.\n\nТехника: спина прямая на всём "
        "протяжении, движение начинается с отведения таза назад, колени слегка "
        "согнуты и почти неподвижны. Возврат в исходное положение — за счёт "
        "ягодиц и задней поверхности бедра, не поясницы."
    ),
    MovementPattern.PUSH: (
        "Толчковое упражнение — развивает грудные мышцы, плечи и трицепс.\n\n"
        "Техника: сохраняйте стабильное положение корпуса и лопаток на всём "
        "протяжении движения. Двигайтесь в полной, контролируемой амплитуде, "
        "без рывков. Дыхание — выдох на усилии."
    ),
    MovementPattern.PULL: (
        "Тяговое упражнение — развивает мышцы спины и плечевого пояса.\n\n"
        "Техника: начинайте движение со сведения лопаток, затем подключайте "
        "руки. Корпус стабилен, без раскачивания. Контролируйте как рабочую, "
        "так и обратную фазу движения."
    ),
    MovementPattern.ROTATION: (
        "Ротационное упражнение на корпус — развивает косые мышцы живота и "
        "контроль вращения таза относительно плечевого пояса.\n\nТехника: "
        "движение идёт от таза и корпуса, а не только от рук. Сохраняйте "
        "контроль на всей амплитуде, избегайте резких рывковых движений."
    ),
    MovementPattern.CORE: (
        "Упражнение на мышцы кора — развивает статическую и динамическую "
        "стабильность корпуса.\n\nТехника: сохраняйте нейтральное положение "
        "позвоночника, не прогибайтесь и не округляйте поясницу. Дыхание "
        "ровное, без задержки."
    ),
    MovementPattern.ANKLE_MOBILITY: (
        "Упражнение на подвижность голеностопа — важно для устойчивости в "
        "коньке и амортизации при приземлениях.\n\nТехника: выполняйте движение "
        "в голеностопном суставе плавно, до появления лёгкого натяжения, без "
        "боли. Колено и бедро остаются стабильными."
    ),
    MovementPattern.HIP_MOBILITY: (
        "Упражнение на подвижность тазобедренного сустава — важно для глубины "
        "и амплитуды хоккейного катания.\n\nТехника: движение выполняется плавно "
        "и подконтрольно, в пределах комфортной амплитуды. Таз и поясница "
        "остаются стабильными, движение изолировано в тазобедренном суставе."
    ),
    MovementPattern.SHOULDER_MOBILITY: (
        "Упражнение на подвижность плечевого пояса — снижает риск травм при "
        "бросках и силовой борьбе.\n\nТехника: выполняйте движение плавно, без "
        "рывков, постепенно увеличивая амплитуду. При появлении боли — "
        "уменьшите амплитуду."
    ),
    MovementPattern.WRIST_MOBILITY: (
        "Упражнение на подвижность и стабильность запястья — важно для хвата "
        "клюшки и контроля шайбы.\n\nТехника: движение выполняется в медленном "
        "темпе, с полным контролем. Предплечье остаётся неподвижным, работает "
        "только кисть/запястье."
    ),
    MovementPattern.LOCOMOTION: (
        "Упражнение на общую локомоцию — развивает скорость и взрывную силу "
        "ног.\n\nТехника: сохраняйте контроль положения корпуса на протяжении "
        "всего движения. Работайте в максимально доступном, но контролируемом "
        "темпе."
    ),
    MovementPattern.STICK_HANDLING: (
        "Упражнение на владение клюшкой и шайбой — развивает контроль, "
        "мягкость кисти и периферийное зрение.\n\nТехника: держите голову "
        "поднятой, контролируйте шайбу мягкими движениями кистей, а не всей "
        "рукой. Постепенно увеличивайте темп по мере уверенного выполнения."
    ),
    MovementPattern.COORDINATION: (
        "Упражнение на координацию и равновесие — развивает общую "
        "двигательную координацию и устойчивость.\n\nТехника: выполняйте "
        "движение подконтрольно, сохраняя стабильное положение корпуса. При "
        "потере равновесия — сделайте паузу и восстановите положение, не "
        "форсируйте темп."
    ),
}

# Deterministic "primary pattern" pick for a multi-tagged exercise's
# technique text (muscle groups above already handle multi-pattern by
# averaging -- text can't sensibly blend two templates, so it picks one).
# Strength patterns first (most content-bearing), then mobility, then
# skill/locomotion -- matches _pick_main's own role ordering intuition.
_PATTERN_PRIORITY: list[MovementPattern] = [
    MovementPattern.SQUAT, MovementPattern.HIP_HINGE, MovementPattern.PUSH, MovementPattern.PULL,
    MovementPattern.ROTATION, MovementPattern.CORE,
    MovementPattern.HIP_MOBILITY, MovementPattern.SHOULDER_MOBILITY,
    MovementPattern.ANKLE_MOBILITY, MovementPattern.WRIST_MOBILITY,
    MovementPattern.LOCOMOTION, MovementPattern.STICK_HANDLING, MovementPattern.COORDINATION,
]


def _combine_muscle_weights(patterns: list[MovementPattern]) -> dict[MuscleGroup, float]:
    relevant = [p for p in patterns if p in _MUSCLE_WEIGHTS_BY_PATTERN]
    if not relevant:
        return {}
    combined: dict[MuscleGroup, float] = {}
    share = 1.0 / len(relevant)
    for pattern in relevant:
        for group, weight in _MUSCLE_WEIGHTS_BY_PATTERN[pattern].items():
            combined[group] = combined.get(group, 0.0) + weight * share
    return {group: round(weight, 4) for group, weight in combined.items()}


def _primary_pattern(patterns: list[MovementPattern]) -> MovementPattern | None:
    for candidate in _PATTERN_PRIORITY:
        if candidate in patterns:
            return candidate
    return patterns[0] if patterns else None


async def main() -> None:
    async with AsyncSessionLocal() as session:
        exercises = (await session.execute(select(Exercise))).scalars().all()
        pattern_rows = (await session.execute(select(ExerciseMovementPattern))).scalars().all()
        patterns_by_exercise: dict = {}
        for row in pattern_rows:
            patterns_by_exercise.setdefault(row.exercise_id, []).append(row.movement_pattern)

        muscle_updates = 0
        text_updates = 0
        skipped_no_pattern = 0

        for exercise in exercises:
            patterns = patterns_by_exercise.get(exercise.id, [])

            weights = _combine_muscle_weights(patterns)
            if weights:
                await session.execute(
                    ExerciseMuscleGroup.__table__.delete().where(
                        ExerciseMuscleGroup.exercise_id == exercise.id
                    )
                )
                for group, weight in weights.items():
                    session.add(
                        ExerciseMuscleGroup(exercise_id=exercise.id, muscle_group=group, weight=weight)
                    )
                muscle_updates += 1
            else:
                skipped_no_pattern += 1

            if exercise.description is not None and exercise.description.startswith(_STUB_PREFIX):
                primary = _primary_pattern(patterns)
                if primary is not None:
                    exercise.description = _TECHNIQUE_BY_PATTERN[primary]
                    text_updates += 1

        await session.commit()
        print(f"exercises processed: {len(exercises)}")
        print(f"muscle groups assigned/updated: {muscle_updates}")
        print(f"skipped (no movement pattern tagged): {skipped_no_pattern}")
        print(f"stub descriptions replaced: {text_updates}")


if __name__ == "__main__":
    asyncio.run(main())
