"""One-off seed script: new off-ice exercises reviewed and classified in the
2026-08-18 planning session (see scripts/new_exercises_draft.md for the
reviewed classification this script implements).

Not a migration -- matches scripts/seed_exercises.py's own convention for
data, as opposed to schema, changes. Run manually:

    poetry run python scripts/seed_offseason_catalog_additions.py

Idempotent: skips any exercise whose `name` already exists (checked once at
start, same convention as seed_exercises.py -- a duplicate name later in
EXERCISES also gets skipped rather than hitting the unique constraint).

Classification (movement_pattern/stimulus_type/target_stat/difficulty/
equipment/exercise_type/volume) is Claude's first pass, requested explicitly
by the product owner to unblock local dev -- not a methodology-reviewed
final answer. Flagged near-duplicates from new_exercises_draft.md (e.g. the
three 90/90-family cooldown stretches, the extra Pallof variant, the
split-stance med ball throw) are included as-is rather than silently merged
with existing rows -- deleting/merging is a separate, deliberate decision.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import (  # noqa: E402
    EquipmentItem,
    Exercise,
    ExerciseEquipmentItem,
    ExerciseMovementPattern,
    ExerciseTargetStat,
    MovementPattern,
    StimulusType,
    TargetStat,
)

# Stage 2.2 (2026-08-20 planning session): equipment_type stopped being a
# real Exercise column, replaced by ExerciseEquipmentItem's per-item list --
# see seed_exercises.py's own copy of this mapping for the full rationale.
_LEGACY_EQUIPMENT_ITEM: dict[str, EquipmentItem | None] = {
    "gym": EquipmentItem.BARBELL,
    "home": EquipmentItem.DUMBBELLS,
    "bodyweight": None,
}

# Each entry: name -> dict of Exercise fields + "movement_patterns" (list)
# + "target_stat" + "equipment_type" (all popped before Exercise(**fields),
# same as seed_exercises.py). exercise_type "duration" entries carry
# target_duration_seconds; "sets_reps" entries carry target_sets/
# rep_range_min/rep_range_max.
EXERCISES: dict[str, dict] = {
    # -- 1. Работа с мягкими тканями (roller/ball), все warmup --
    "Передняя поверхность бедра (квадрицепс) - ролл": {
        "description": "Лечь на ролик животом вниз, опора на предплечья. Медленно прокатать переднюю поверхность бедра от таза до колена, 8-10 проходов. При болезненной точке остановиться и подышать спокойно, пока напряжение не спадёт.",
        "phase": "warmup", "movement_patterns": ["squat"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "home",
        "exercise_type": "duration", "target_duration_seconds": 60,
    },
    "Боковая поверхность бедра - ролл": {
        "description": "Лечь на бок на ролик, опора на предплечье. Медленно прокатать боковую поверхность бедра (илиотибиальный тракт) от таза до колена, 8-10 проходов на каждую сторону.",
        "phase": "warmup", "movement_patterns": ["squat"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "home",
        "exercise_type": "duration", "target_duration_seconds": 60,
    },
    "Задняя поверхность бедра (бицепс бедра) - ролл": {
        "description": "Сидя на полу, ролик под задней поверхностью бедра, руки в упоре сзади. Медленно прокатать от ягодицы до подколенной ямки, 8-10 проходов на каждую ногу.",
        "phase": "warmup", "movement_patterns": ["hip_hinge"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "home",
        "exercise_type": "duration", "target_duration_seconds": 60,
    },
    "Приводящие мышцы - ролл": {
        "description": "Лечь на живот, согнуть ногу в колене и развернуть в сторону, ролик под внутренней поверхностью бедра. Медленно прокатать приводящие мышцы, 8-10 проходов на каждую ногу.",
        "phase": "warmup", "movement_patterns": ["hip_mobility"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "home",
        "exercise_type": "duration", "target_duration_seconds": 60,
    },
    "Ягодицы - ролл": {
        "description": "Сидя на ролике, закинуть одну ногу лодыжкой на колено другой, слегка завалиться в сторону рабочей ягодицы. Медленно прокатать, 8-10 проходов на каждую сторону.",
        "phase": "warmup", "movement_patterns": ["hip_hinge"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "home",
        "exercise_type": "duration", "target_duration_seconds": 60,
    },
    "Поясница - ролл": {
        "description": "Лечь на ролик поперёк поясницы, колени согнуты, стопы на полу. Очень медленно и аккуратно прокатать зону чуть выше таза, избегая давления прямо на позвоночник. 8-10 медленных проходов.",
        "phase": "warmup", "movement_patterns": ["core"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "home",
        "exercise_type": "duration", "target_duration_seconds": 60,
    },
    "Внутренняя часть лопатки - ролл": {
        "description": "Лечь на ролик так, чтобы он проходил вдоль внутреннего края лопатки, руки скрещены на груди. Медленно прокатать зону между позвоночником и лопаткой, 8-10 проходов на каждую сторону.",
        "phase": "warmup", "movement_patterns": ["pull"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "home",
        "exercise_type": "duration", "target_duration_seconds": 45,
    },
    "Наружная часть лопатки - ролл": {
        "description": "Лечь на бок, ролик под наружным краем лопатки. Медленно прокатать зону, 8-10 проходов на каждую сторону.",
        "phase": "warmup", "movement_patterns": ["pull"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "home",
        "exercise_type": "duration", "target_duration_seconds": 45,
    },
    "Стопа - мяч": {
        "description": "Встать, наступить сводом стопы на маленький мяч (теннисный или баскетбольный жёсткости). Медленно прокатать свод стопы, 8-10 проходов на каждую ногу, вес тела регулировать по ощущениям.",
        "phase": "warmup", "movement_patterns": ["ankle_mobility"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "home",
        "exercise_type": "duration", "target_duration_seconds": 45,
    },
    "Боковая часть голени - мяч": {
        "description": "Сидя, положить мяч под боковую часть голени (малоберцовая мышца), медленно прокатать от колена к лодыжке, 8-10 проходов на каждую ногу.",
        "phase": "warmup", "movement_patterns": ["ankle_mobility"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "home",
        "exercise_type": "duration", "target_duration_seconds": 45,
    },
    "Грудь у стены - мяч": {
        "description": "Прижать мяч к стене грудной мышцей чуть ниже ключицы, медленно перемещать вес тела, катая мяч по груди, 8-10 проходов на каждую сторону.",
        "phase": "warmup", "movement_patterns": ["shoulder_mobility"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "home",
        "exercise_type": "duration", "target_duration_seconds": 45,
    },
    "Задняя часть приводящих на тумбе": {
        "description": "Положить бедро на тумбу или скамью, мяч под задней частью приводящих у паха. Медленно прокатать, 8-10 проходов на каждую ногу.",
        "phase": "warmup", "movement_patterns": ["hip_mobility"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "home",
        "exercise_type": "duration", "target_duration_seconds": 45,
    },

    # -- 2. Мобильность --
    "Мобильность голеностопа у стены": {
        "description": "Встать лицом к стене, пальцы стопы на расстоянии ладони от стены. Не отрывая пятку от пола, подать колено вперёд к стене. Плавные повторяющиеся движения, 45 секунд на каждую ногу.",
        "phase": "warmup", "movement_patterns": ["ankle_mobility"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "bodyweight",
        "exercise_type": "duration", "target_duration_seconds": 45,
    },
    "Мобилизация квадрицепса в полуприседе на одном колене": {
        "description": "Встать в полуприсед на одно колено (задняя нога сзади согнута), подать таз вперёд, слегка отклоняя корпус назад для растяжения передней поверхности бедра задней ноги. Плавно покачиваться в этом положении.",
        "phase": "warmup", "movement_patterns": ["squat"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 2, "equipment_type": "bodyweight",
        "exercise_type": "duration", "target_duration_seconds": 45,
    },
    "Диагональное раскачивание таза с выходом в шаг": {
        "description": "Из основной стойки плавно раскачивать таз по диагонали вперёд-в сторону, с плавным переходом в шаг вперёд. Повторять поочерёдно на обе стороны в динамике, не останавливаясь в крайних точках.",
        "phase": "warmup", "movement_patterns": ["hip_mobility"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 2, "equipment_type": "bodyweight",
        "exercise_type": "duration", "target_duration_seconds": 45,
    },
    "Диагональная дуга рукой лёжа на боку": {
        "description": "Лечь на бок, колени согнуты. Верхней рукой описать дугу от бедра вперёд, вверх и назад за спину, следя взглядом за кистью и раскрывая грудной отдел. Плавно, в темпе дыхания.",
        "phase": "warmup", "movement_patterns": ["rotation"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "bodyweight",
        "exercise_type": "duration", "target_duration_seconds": 45,
    },
    "Йога-отжимание": {
        "description": "Из планки на прямых руках плавно перейти через позу собаки мордой вниз в позу собаки мордой вверх и обратно, сохраняя контроль в пояснице. Медленный, непрерывный переход.",
        "phase": "warmup", "movement_patterns": ["push"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 2, "equipment_type": "bodyweight",
        "exercise_type": "duration", "target_duration_seconds": 45,
    },
    "Боковой присед с касанием внутренней части стопы": {
        "description": "Широкая стойка, вес переносится в глубокий боковой присед на одну ногу, другая нога прямая. В нижней точке коснуться рукой внутренней части опорной стопы. Плавно, поочерёдно в обе стороны.",
        "phase": "warmup", "movement_patterns": ["squat"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 2, "equipment_type": "bodyweight",
        "exercise_type": "duration", "target_duration_seconds": 45,
    },
    "Перевёрнутый reach (перевёрнутая тяга)": {
        "description": "Из глубокого выпада с опорой рукой на пол, развернуть корпус и потянуться свободной рукой вверх и назад по диагонали, раскрывая грудной отдел. Плавно, поочерёдно в обе стороны.",
        "phase": "warmup", "movement_patterns": ["rotation"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 2, "equipment_type": "bodyweight",
        "exercise_type": "duration", "target_duration_seconds": 45,
    },
    "Голубь с рукой по диагонали": {
        "description": "Классическая поза голубя (передняя нога согнута под корпусом, задняя прямая назад), с диагональным вытягиванием разноимённой руки вперёд для усиления растяжения. Держать без резких движений.",
        "phase": "cooldown", "movement_patterns": ["hip_mobility"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 2, "equipment_type": "home",
        "exercise_type": "duration", "target_duration_seconds": 30,
    },
    "Квадрицепс на тумбе с руками вверх": {
        "description": "Задняя нога стопой на тумбе позади, передняя согнута в выпаде. Поднять руки вверх и слегка отклонить корпус назад для усиления растяжения передней поверхности бедра задней ноги.",
        "phase": "cooldown", "movement_patterns": ["squat"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 2, "equipment_type": "home",
        "exercise_type": "duration", "target_duration_seconds": 30,
    },
    "Боковой выпад на колене + наружная ротация": {
        "description": "Из бокового выпада на одном колене плавно раскрыть таз наружной ротацией бедра в сторону задней ноги, удерживая корпус вертикально. Плавно, поочерёдно в обе стороны.",
        "phase": "warmup", "movement_patterns": ["hip_mobility"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 2, "equipment_type": "bodyweight",
        "exercise_type": "duration", "target_duration_seconds": 45,
    },
    "Spiderman + ротация грудного отдела": {
        "description": "Из положения планки шагнуть стопой к одноимённой руке (поза паука), затем развернуть корпус и потянуться внутренней рукой вверх, раскрывая грудной отдел. Плавно, поочерёдно в обе стороны.",
        "phase": "warmup", "movement_patterns": ["rotation"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 2, "equipment_type": "bodyweight",
        "exercise_type": "duration", "target_duration_seconds": 45,
    },
    "Широчайшая + рука под себя": {
        "description": "На четвереньках, одну руку просунуть под корпус ладонью вверх, опуская плечо и висок к полу для растяжения широчайшей мышцы и грудного отдела. Держать без резких движений.",
        "phase": "cooldown", "movement_patterns": ["shoulder_mobility"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "bodyweight",
        "exercise_type": "duration", "target_duration_seconds": 30,
    },
    "Голеностоп у стены (ПНФ)": {
        "description": "Из положения мобильности голеностопа у стены: подать колено к стене до лёгкого натяжения, надавить стопой в пол на 5-6 секунд без движения (изометрия), расслабиться и на выдохе подать колено чуть дальше. Повторить 2-3 раза на каждую ногу.",
        "phase": "warmup", "movement_patterns": ["ankle_mobility"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 2, "equipment_type": "bodyweight",
        "exercise_type": "duration", "target_duration_seconds": 45,
    },
    "Полусгибатель у стены (ПНФ)": {
        "description": "Лечь на спину у стены, одну ногу поднять прямой к стене до лёгкого натяжения задней поверхности бедра. Надавить пяткой в воображаемую точку на 5-6 секунд (изометрия), расслабиться, на выдохе поднять ногу чуть выше. Повторить 2-3 раза на каждую ногу.",
        "phase": "cooldown", "movement_patterns": ["hip_hinge"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 2, "equipment_type": "bodyweight",
        "exercise_type": "duration", "target_duration_seconds": 30,
    },
    "Голубь (ПНФ)": {
        "description": "В позе голубя: на лёгком натяжении напрячь ягодичную мышцу передней ноги на 5-6 секунд без движения, расслабиться и на выдохе мягко углубить позу. Повторить 2-3 раза на каждую сторону.",
        "phase": "cooldown", "movement_patterns": ["hip_mobility"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 2, "equipment_type": "home",
        "exercise_type": "duration", "target_duration_seconds": 30,
    },
    "Приводящие в длинной позиции (ПНФ)": {
        "description": "Широкая стойка ноги врозь, наклон в сторону одной ноги до лёгкого натяжения приводящих. Напрячь приводящую мышцу на 5-6 секунд без движения, расслабиться, на выдохе углубить наклон. Повторить 2-3 раза на каждую сторону.",
        "phase": "cooldown", "movement_patterns": ["hip_mobility"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 2, "equipment_type": "bodyweight",
        "exercise_type": "duration", "target_duration_seconds": 30,
    },

    # -- 3. Активация (2 круга) --
    "Жук (Dead Bug)": {
        "description": "Лечь на спину, руки вверх, колени согнуты под 90 градусов. Медленно опустить разноимённые руку и ногу к полу, не отрывая поясницу от пола, вернуться и повторить на другую сторону. Базовый вариант без анти-ротационного сопротивления -- проще, чем существующий Dead Bug + антиротация.",
        "phase": "warmup", "movement_patterns": ["core"], "stimulus_type": "strength",
        "target_stat": "strength", "difficulty_level": 1, "equipment_type": "bodyweight",
        "exercise_type": "sets_reps", "target_sets": 2, "rep_range_min": 10, "rep_range_max": 12,
    },
    "Боковая ходьба с мини-бэндом": {
        "description": "Мини-резинка на голенях выше щиколоток, полуприсед, спина прямая. Приставными шагами двигаться в сторону, сохраняя натяжение резинки постоянным, не сводя колени. 10-12 шагов в каждую сторону.",
        "phase": "warmup", "movement_patterns": ["hip_mobility"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "home",
        "exercise_type": "sets_reps", "target_sets": 2, "rep_range_min": 10, "rep_range_max": 12,
    },
    "Лежачее подтягивание поясничной мышцы с мини-бэндом": {
        "description": "Лёжа на спине, резинка закреплена на стопе. Подтянуть согнутое колено к груди против сопротивления резинки, контролируя возврат. 10-12 повторений на каждую ногу.",
        "phase": "warmup", "movement_patterns": ["hip_hinge"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 2, "equipment_type": "home",
        "exercise_type": "sets_reps", "target_sets": 2, "rep_range_min": 10, "rep_range_max": 12,
    },
    "Марш ягодицами у стены с мини-бэндом + изометрия": {
        "description": "Спина прижата к стене, мини-резинка на бёдрах, полуприсед. Поочерёдно поднимать колено к груди (марш), удерживая таз ровно, каждые несколько повторений добавлять изометрическую паузу 2-3 секунды в верхней точке. 10 повторений на каждую ногу.",
        "phase": "warmup", "movement_patterns": ["hip_hinge"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 2, "equipment_type": "home",
        "exercise_type": "sets_reps", "target_sets": 2, "rep_range_min": 8, "rep_range_max": 10,
    },

    # -- 4. Сила и контроль: ноги и задняя цепь --
    "Эксцентрическое сгибание ног с полотенцем (5 сек вниз)": {
        "description": "Стоя на одной ноге, полотенце под стопой на скользком полу. Медленно, за 5 секунд, разогнуть колено, скользя стопой вперёд, контролируя эксцентрическую фазу задней поверхности бедра. Вернуться в исходное и повторить.",
        "phase": "main", "movement_patterns": ["hip_hinge"], "stimulus_type": "strength",
        "target_stat": "strength", "difficulty_level": 3, "equipment_type": "bodyweight",
        "exercise_type": "sets_reps", "target_sets": 3, "rep_range_min": 6, "rep_range_max": 8,
    },
    "Сгибание ног на фитболе (эксцентрика)": {
        "description": "Лёжа на спине, пятки на фитболе, таз приподнят (ягодичный мост). Подкатить мяч к себе сгибанием ног, затем медленно, за 3-4 секунды, раскатить мяч обратно, контролируя эксцентрическую фазу.",
        "phase": "main", "movement_patterns": ["hip_hinge"], "stimulus_type": "strength",
        "target_stat": "strength", "difficulty_level": 3, "equipment_type": "home",
        "exercise_type": "sets_reps", "target_sets": 3, "rep_range_min": 8, "rep_range_max": 12,
    },
    "Трёхпозиционное сжатие приводящих (статика)": {
        "description": "Лёжа на спине, мяч или подушка между коленями. Сжимать мяч изометрически в трёх позициях: колени согнуты под 90°, полусогнуты, почти прямые -- по 15-20 секунд в каждой позиции.",
        "phase": "main", "movement_patterns": ["hip_mobility"], "stimulus_type": "strength",
        "target_stat": "strength", "difficulty_level": 2, "equipment_type": "bodyweight",
        "exercise_type": "duration", "target_duration_seconds": 20,
    },
    "Сжатие приводящих с прямыми ногами в среднем диапазоне": {
        "description": "Лёжа на спине, ноги прямые, мяч между стопами или голенями в среднем диапазоне амплитуды. Изометрическое сжатие мяча ногами, 20 секунд удержания.",
        "phase": "main", "movement_patterns": ["hip_mobility"], "stimulus_type": "strength",
        "target_stat": "strength", "difficulty_level": 2, "equipment_type": "bodyweight",
        "exercise_type": "duration", "target_duration_seconds": 20,
    },
    "Подъём на носок на одной ноге с гантелью (медленный темп)": {
        "description": "Стоя на одной ноге с гантелью в одноимённой руке, медленно подняться на носок (2 секунды вверх, 2 секунды вниз), сохраняя баланс. Свободной рукой можно слегка придерживаться опоры.",
        "phase": "main", "movement_patterns": ["ankle_mobility"], "stimulus_type": "strength",
        "target_stat": "strength", "difficulty_level": 3, "equipment_type": "home",
        "exercise_type": "sets_reps", "target_sets": 3, "rep_range_min": 8, "rep_range_max": 12,
        "tracks_weight": True, "bodyweight_ratio": 0.15,
    },
    "Разгибание голеностопа с опорой о стену": {
        "description": "Сидя или стоя с опорой на стену, пятка на полу, носок тянуть вверх на себя (тыльное сгибание) против лёгкого сопротивления стопы другой ноги или без него. Контролируемый темп.",
        "phase": "warmup", "movement_patterns": ["ankle_mobility"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "bodyweight",
        "exercise_type": "sets_reps", "target_sets": 2, "rep_range_min": 12, "rep_range_max": 15,
    },

    # -- 4. Сила и контроль: верх тела и плечи --
    "Жим сидя на одном колене (горизонтальный)": {
        "description": "Полуприсед на одном колене (разноимённая рука с задней ногой работает), корпус вертикально. Жим гантели или рукояти блока вперёд на уровне груди, без раскачивания корпуса.",
        "phase": "main", "movement_patterns": ["push"], "stimulus_type": "strength",
        "target_stat": "strength", "difficulty_level": 3, "equipment_type": "gym",
        "exercise_type": "sets_reps", "target_sets": 3, "rep_range_min": 8, "rep_range_max": 12,
    },
    "Тяга сидя на одном колене (горизонтальная)": {
        "description": "Полуприсед на одном колене, корпус вертикально. Тяга рукояти блока или резины к поясу, сводя лопатку, без раскачивания корпуса и без ротации таза.",
        "phase": "main", "movement_patterns": ["pull"], "stimulus_type": "strength",
        "target_stat": "strength", "difficulty_level": 3, "equipment_type": "gym",
        "exercise_type": "sets_reps", "target_sets": 3, "rep_range_min": 8, "rep_range_max": 12,
    },
    "Отведение гантели лёжа на боку": {
        "description": "Лечь на бок, гантель в верхней руке. Отвести прямую руку вверх до уровня плеча, контролируя темп, не раскачивая корпус. Лёгкий вес, акцент на среднюю дельту.",
        "phase": "main", "movement_patterns": ["push"], "stimulus_type": "strength",
        "target_stat": "strength", "difficulty_level": 2, "equipment_type": "home",
        "exercise_type": "sets_reps", "target_sets": 3, "rep_range_min": 10, "rep_range_max": 15,
        "tracks_weight": True, "bodyweight_ratio": 0.03,
    },
    "Наружная ротация гантели сидя": {
        "description": "Сидя, локоть прижат к боку и согнут под 90 градусов, лёгкая гантель в руке. Развернуть предплечье наружу, не отрывая локоть от корпуса, вернуться в исходное. Медленный контролируемый темп.",
        "phase": "main", "movement_patterns": ["pull"], "stimulus_type": "strength",
        "target_stat": "strength", "difficulty_level": 2, "equipment_type": "home",
        "exercise_type": "sets_reps", "target_sets": 3, "rep_range_min": 10, "rep_range_max": 15,
        "tracks_weight": True, "bodyweight_ratio": 0.02,
    },
    "Сведение лопаток с резиной в полуприседе на колене": {
        "description": "Полуприсед на одном колене, резинка натянута перед собой на уровне груди. Свести лопатки, разводя руки в стороны, без прогиба в пояснице. Контролируемый темп.",
        "phase": "warmup", "movement_patterns": ["pull"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "home",
        "exercise_type": "sets_reps", "target_sets": 2, "rep_range_min": 12, "rep_range_max": 15,
    },

    # -- 4. Сила и контроль: корпус --
    "Планка с вытягиванием рук вперёд": {
        "description": "Планка на прямых руках. Поочерёдно вытягивать прямую руку вперёд, удерживая таз и плечи неподвижными и ровными, без ротации корпуса. 8-10 повторений на каждую сторону.",
        "phase": "main", "movement_patterns": ["core"], "stimulus_type": "strength",
        "target_stat": "strength", "difficulty_level": 2, "equipment_type": "bodyweight",
        "exercise_type": "sets_reps", "target_sets": 3, "rep_range_min": 8, "rep_range_max": 10,
    },
    "Антиротационный жим на одном колене (изометрия)": {
        "description": "Полуприсед на одном колене боком к резине/блоку. Вытянуть рукоять вперёд от груди и удерживать 20 секунд, сопротивляясь ротации таза и корпуса. Более сложная (полуколенная) прогрессия, дополняющая существующие варианты Pallof-жима.",
        "phase": "main", "movement_patterns": ["core"], "stimulus_type": "strength",
        "target_stat": "strength", "difficulty_level": 3, "equipment_type": "home",
        "exercise_type": "duration", "target_duration_seconds": 20,
    },
    "Планка в позе медведя (Bear Crawl Plank)": {
        "description": "Стойка на руках и стопах, колени приподняты на пару сантиметров над полом, спина ровная. Удерживать позицию, не давая тазу подниматься или проваливаться.",
        "phase": "main", "movement_patterns": ["core"], "stimulus_type": "strength",
        "target_stat": "strength", "difficulty_level": 3, "equipment_type": "bodyweight",
        "exercise_type": "duration", "target_duration_seconds": 25,
    },
    "Изометрические удержания в отжимании": {
        "description": "Удержание в отжимании на середине амплитуды (локти согнуты примерно на 90 градусов), тело ровной линией от плеч до стоп. Держать без прогиба в пояснице.",
        "phase": "main", "movement_patterns": ["push"], "stimulus_type": "strength",
        "target_stat": "strength", "difficulty_level": 2, "equipment_type": "bodyweight",
        "exercise_type": "duration", "target_duration_seconds": 18,
    },

    # -- 5. Мощность и скорость --
    "Спринт из положения полуколена": {
        "description": "Старт из полуприседа на одном колене. По команде резко подняться и выполнить короткий спринт с максимальным ускорением на 10-15 метров. Полное восстановление между повторениями.",
        "phase": "main", "movement_patterns": ["locomotion"], "stimulus_type": "power",
        "target_stat": "agility", "difficulty_level": 3, "equipment_type": "bodyweight",
        "exercise_type": "sets_reps", "target_sets": 4, "rep_range_min": 1, "rep_range_max": 1,
    },
    "Латеральный спринт из положения полуколена": {
        "description": "Старт из полуприседа на одном колене, боком к направлению движения. По команде резко подняться и выполнить короткий боковой спринт на 5-10 метров. Полное восстановление между повторениями.",
        "phase": "main", "movement_patterns": ["locomotion"], "stimulus_type": "power",
        "target_stat": "agility", "difficulty_level": 3, "equipment_type": "bodyweight",
        "exercise_type": "sets_reps", "target_sets": 4, "rep_range_min": 1, "rep_range_max": 1,
    },
    "Ротационный бросок медбола из сплита": {
        "description": "Сплит-стойка (одна нога впереди), медбол у бедра сзади. С разворотом таза и корпуса резко выбросить мяч в стену по диагонали вперёд. Вариант существующего ротационного броска медбола с фиксированной сплит-стойкой вместо свободной. Полное восстановление между повторениями.",
        "phase": "main", "movement_patterns": ["rotation"], "stimulus_type": "power",
        "target_stat": "agility", "difficulty_level": 3, "equipment_type": "home",
        "exercise_type": "sets_reps", "target_sets": 3, "rep_range_min": 3, "rep_range_max": 5,
    },

    # -- 6. Заминка (30 секунд каждое) --
    "Растяжка сгибателя бедра в полуприседе на колене": {
        "description": "Полуприсед на одном колене, таз подать вперёд без прогиба в пояснице, до ощущения растяжения передней поверхности бедра задней ноги. Держать спокойно, дышать ровно.",
        "phase": "cooldown", "movement_patterns": ["hip_mobility"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "bodyweight",
        "exercise_type": "duration", "target_duration_seconds": 30,
    },
    "Квадрицепс с задней ногой на возвышении": {
        "description": "Стопа задней ноги на невысокой скамье позади, передняя нога в выпаде впереди. Слегка присесть, ощущая растяжение передней поверхности бедра задней ноги. Держать спокойно.",
        "phase": "cooldown", "movement_patterns": ["squat"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "home",
        "exercise_type": "duration", "target_duration_seconds": 30,
    },
    "Задняя поверхность бедра на четвереньках": {
        "description": "На четвереньках, выпрямить одну ногу вперёд пяткой в пол, таз отвести назад до ощущения растяжения задней поверхности бедра. Держать спокойно, дышать ровно.",
        "phase": "cooldown", "movement_patterns": ["hip_hinge"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "bodyweight",
        "exercise_type": "duration", "target_duration_seconds": 30,
    },
    "Боковое раскачивание на четвереньках": {
        "description": "На четвереньках плавно перекатывать таз влево-вправо, слегка садясь к пяткам, растягивая поясницу и бок. Медленно, без резких движений.",
        "phase": "cooldown", "movement_patterns": ["hip_mobility"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "bodyweight",
        "exercise_type": "duration", "target_duration_seconds": 30,
    },
    "Колено к колену лёжа": {
        "description": "Лёжа на спине, одна нога согнута под 90 градусов над тазом, другая скрещена лодыжкой на колене. Мягко подтянуть колено к груди руками до ощущения растяжения ягодицы. Держать спокойно.",
        "phase": "cooldown", "movement_patterns": ["hip_mobility"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "bodyweight",
        "exercise_type": "duration", "target_duration_seconds": 30,
    },
    "Ягодица крест-накрест лёжа": {
        "description": "Лёжа на спине, лодыжка одной ноги на колене другой (фигура четыре). Обхватить бедро опорной ноги руками и подтянуть к груди до ощущения растяжения ягодицы скрещённой ноги. Держать спокойно.",
        "phase": "cooldown", "movement_patterns": ["hip_mobility"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "bodyweight",
        "exercise_type": "duration", "target_duration_seconds": 30,
    },
    "Обхват колена в позиции 90/90 лёжа": {
        "description": "Лёжа на спине, обе ноги согнуты под 90 градусов в стороны (положение 90/90). Обхватить ближнее колено руками и подтянуть к груди, сохраняя таз на полу. Держать спокойно, затем сменить сторону.",
        "phase": "cooldown", "movement_patterns": ["hip_mobility"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "bodyweight",
        "exercise_type": "duration", "target_duration_seconds": 30,
    },
    "Растяжка груди под 90 градусов": {
        "description": "Стоя боком у стены или дверного проёма, рука согнута под 90 градусов (локоть на уровне плеча), предплечье на опоре. Плавно развернуть корпус в противоположную сторону до растяжения груди. Держать спокойно.",
        "phase": "cooldown", "movement_patterns": ["shoulder_mobility"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "bodyweight",
        "exercise_type": "duration", "target_duration_seconds": 30,
    },
    "Широчайшая крест-накрест": {
        "description": "Стоя, взяться рукой за неподвижную опору на уровне таза, отвести таз в сторону от опоры, вытягивая бок и широчайшую мышцу. Держать спокойно, затем сменить сторону.",
        "phase": "cooldown", "movement_patterns": ["shoulder_mobility"], "stimulus_type": "mobility",
        "target_stat": "agility", "difficulty_level": 1, "equipment_type": "bodyweight",
        "exercise_type": "duration", "target_duration_seconds": 30,
    },
}


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        existing_names = set(
            (await session.execute(select(Exercise.name))).scalars().all()
        )

        created = 0
        new_rows: list[tuple[Exercise, list[str], str, EquipmentItem | None]] = []
        for name, data in EXERCISES.items():
            if name in existing_names:
                continue
            existing_names.add(name)

            fields = dict(data)
            patterns = fields.pop("movement_patterns")
            target_stat = fields.pop("target_stat")
            equipment_item = _LEGACY_EQUIPMENT_ITEM[fields.pop("equipment_type")]
            fields.setdefault("category", "off_ice")
            fields.setdefault("tracks_weight", False)

            exercise = Exercise(name=name, **fields)
            session.add(exercise)
            new_rows.append((exercise, patterns, target_stat, equipment_item))
            created += 1

        if new_rows:
            await session.flush()
            for exercise, patterns, target_stat, equipment_item in new_rows:
                session.add(
                    ExerciseTargetStat(
                        exercise_id=exercise.id, target_stat=TargetStat(target_stat), order=0
                    )
                )
                for pattern in patterns:
                    session.add(
                        ExerciseMovementPattern(
                            exercise_id=exercise.id,
                            movement_pattern=MovementPattern(pattern),
                        )
                    )
                if equipment_item is not None:
                    session.add(
                        ExerciseEquipmentItem(
                            exercise_id=exercise.id, equipment_item=equipment_item
                        )
                    )

        await session.commit()
        print(f"Seeded {created} new exercise(s), skipped {len(EXERCISES) - created} existing.")


if __name__ == "__main__":
    asyncio.run(seed())
