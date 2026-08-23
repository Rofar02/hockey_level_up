"""One-off seed script for the exercise catalog (Phase 1).

Not a migration -- run manually whenever the catalog needs (re)seeding:

    poetry run python scripts/seed_exercises.py

Idempotent: skips any exercise whose `name` already exists.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import (  # noqa: E402
    EquipmentItem,
    Exercise,
    ExerciseEquipmentItem,
    ExerciseTargetStat,
    TargetStat,
    TrainingPhase,
)

# Stage 2.2 (2026-08-20 planning session): equipment_type stopped being a
# real Exercise column, replaced by ExerciseEquipmentItem's per-item list --
# but every EXERCISES literal below still carries its old gym/home/
# bodyweight value, so this maps it to the same placeholder item the
# migration backfill used for existing rows (BARBELL for gym, DUMBBELLS for
# home, nothing for bodyweight), so a fresh seed and a migrated old DB stay
# behaviorally identical. Real per-exercise item accuracy is Stage 4's job.
_LEGACY_EQUIPMENT_ITEM: dict[str, EquipmentItem | None] = {
    "gym": EquipmentItem.BARBELL,
    "home": EquipmentItem.DUMBBELLS,
    "bodyweight": None,
}

# 2026-08-22: corrects the three stick_handling-pattern exercises below
# that _LEGACY_EQUIPMENT_ITEM's coarse home->DUMBBELLS mapping mistagged --
# applied by name in seed()'s own loop, after both the create and
# FIELD_UPDATES passes. See that loop's comment for why.
_EQUIPMENT_ITEM_OVERRIDES: dict[str, tuple[EquipmentItem, ...]] = {
    "Ведение мяча / шайбы клюшкой (off-ice)": (EquipmentItem.HOCKEY_STICK,),
    "Ведение теннисного мяча клюшкой на асфальте": (EquipmentItem.HOCKEY_STICK,),
    "Подбрасывание шайбы на крюке клюшки": (EquipmentItem.HOCKEY_STICK,),
}

# P3 item #8, 2026-08-23: the same three stick-handling exercises above,
# retagged from phase=MAIN to the new phase=PUCK (app.models.exercise.
# TrainingPhase.PUCK) -- ScheduleService._pick_puck_module_exercises picks
# its tail-on exclusively from phase=PUCK now, so these three (the only
# real puck-handling content that exists today) need to actually live
# there, not under MAIN, or the module would find nothing. Same
# name-keyed, idempotent, "fixes existing rows too" shape as
# _EQUIPMENT_ITEM_OVERRIDES right above -- deliberately not folded into
# one dict with it, since this corrects a different field via a different
# query/update shape.
_PHASE_OVERRIDES: dict[str, TrainingPhase] = {
    "Ведение мяча / шайбы клюшкой (off-ice)": TrainingPhase.PUCK,
    "Ведение теннисного мяча клюшкой на асфальте": TrainingPhase.PUCK,
    "Подбрасывание шайбы на крюке клюшки": TrainingPhase.PUCK,
}

PLACEHOLDER_DESCRIPTION = "Заглушка: описание будет добавлено позже."

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
    # -- Phase 7: off-ice main --
    {
        "name": "Прыжки в сторону (имитация конькобежного бега)",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "main",
        "target_stat": "agility",
        "difficulty_level": 3,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Жим гантелей от груди",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "main",
        "target_stat": "strength",
        "difficulty_level": 3,
        "equipment_type": "home",
    },
    {
        "name": "Бросок набивного мяча от груди",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "main",
        "target_stat": "strength",
        "difficulty_level": 3,
        "equipment_type": "gym",
    },
    {
        "name": "Отжимания с хлопком",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "main",
        "target_stat": "strength",
        "difficulty_level": 4,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Кросс (бег на длинную дистанцию)",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "main",
        "target_stat": "endurance",
        "difficulty_level": 3,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Лягушка (прыжковые приседания)",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "main",
        "target_stat": "endurance",
        "difficulty_level": 3,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Интервальный спринт 10×30м",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "main",
        "target_stat": "endurance",
        "difficulty_level": 4,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Бёрпи",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "main",
        "target_stat": "endurance",
        "difficulty_level": 3,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Лестница для ног (agility ladder)",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "main",
        "target_stat": "agility",
        "difficulty_level": 3,
        "equipment_type": "home",
    },
    {
        "name": "Ловля теннисного мяча на реакцию",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "main",
        "target_stat": "agility",
        "difficulty_level": 2,
        "equipment_type": "home",
    },
    {
        "name": "Жонглирование двумя мячами",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "main",
        "target_stat": "agility",
        "difficulty_level": 2,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Присед на одной ноге (пистолетик)",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "main",
        "target_stat": "agility",
        "difficulty_level": 4,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Планка на нестабильной поверхности",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "main",
        "target_stat": "strength",
        "difficulty_level": 3,
        "equipment_type": "home",
    },
    {
        "name": "Стойка на одной ноге с закрытыми глазами",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "main",
        "target_stat": "agility",
        "difficulty_level": 2,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Комплекс суставной гимнастики",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        # Was "main" -- a real, user-reported bug: this is joint-mobility
        # warmup content (same as its two siblings "Суставная гимнастика"/
        # "Суставная разминка (вращения)", both correctly "warmup"), not
        # MAIN accessory work, but it kept getting assembled into MAIN
        # blocks because _pick_main's role 4 has no filter beyond phase
        # itself. See scripts/fix_joint_gymnastics_phase.py for the
        # existing-DB fix and scripts/backfill_warmup_stages.py for the
        # matching warmup_stage classification.
        "phase": "warmup",
        "target_stat": "agility",
        "difficulty_level": 2,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Растяжка на подвижность бедра",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "main",
        "target_stat": "agility",
        "difficulty_level": 2,
        "equipment_type": "home",
    },
    {
        "name": "Ведение теннисного мяча клюшкой на асфальте",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "main",
        "target_stat": "agility",
        "difficulty_level": 3,
        "equipment_type": "home",
    },
    {
        "name": "Ведение мяча между конусами",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "main",
        "target_stat": "agility",
        "difficulty_level": 3,
        "equipment_type": "home",
    },
    {
        "name": "Подбрасывание шайбы на крюке клюшки",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "main",
        "target_stat": "agility",
        "difficulty_level": 2,
        "equipment_type": "bodyweight",
    },
    # -- Phase 7: on-ice main --
    {
        "name": "Катание спиной вперёд",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "on_ice",
        "phase": "main",
        "target_stat": "agility",
        "difficulty_level": 3,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Слалом с шайбой между конусами",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "on_ice",
        "phase": "main",
        "target_stat": "agility",
        "difficulty_level": 3,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Малые игры 3х3 на льду",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "on_ice",
        "phase": "main",
        "target_stat": "intellect",
        "difficulty_level": 3,
        "equipment_type": "bodyweight",
    },
    # -- Phase 7: warmup --
    {
        "name": "Суставная гимнастика",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "warmup",
        "target_stat": "agility",
        "difficulty_level": 1,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Бег на месте",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "warmup",
        "target_stat": "endurance",
        "difficulty_level": 1,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Динамическая растяжка (махи)",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "warmup",
        "target_stat": "agility",
        "difficulty_level": 1,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Прыжки на скакалке (лёгкий темп)",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "warmup",
        "target_stat": "endurance",
        "difficulty_level": 1,
        "equipment_type": "home",
    },
    {
        "name": "Активация плеч эспандером",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "warmup",
        "target_stat": "strength",
        "difficulty_level": 1,
        "equipment_type": "home",
    },
    {
        "name": "Велотренажёр (лёгкая интенсивность)",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "warmup",
        "target_stat": "endurance",
        "difficulty_level": 1,
        "equipment_type": "gym",
    },
    {
        "name": "Гребной тренажёр (лёгкий темп)",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "warmup",
        "target_stat": "endurance",
        "difficulty_level": 1,
        "equipment_type": "gym",
    },
    {
        "name": "Работа с пустым грифом",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "warmup",
        "target_stat": "strength",
        "difficulty_level": 1,
        "equipment_type": "gym",
    },
    {
        "name": "Динамическая растяжка на льду перед стартом",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "on_ice",
        "phase": "warmup",
        "target_stat": "agility",
        "difficulty_level": 1,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Катание спиной вперёд в медленном темпе",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "on_ice",
        "phase": "warmup",
        "target_stat": "agility",
        "difficulty_level": 1,
        "equipment_type": "bodyweight",
    },
    # -- Phase 7: cooldown (static stretching) --
    {
        "name": "Растяжка подколенных сухожилий стоя",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "cooldown",
        "target_stat": "agility",
        "difficulty_level": 1,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Растяжка квадрицепса стоя",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "cooldown",
        "target_stat": "agility",
        "difficulty_level": 1,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Кошка-корова",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "cooldown",
        "target_stat": "agility",
        "difficulty_level": 1,
        "equipment_type": "bodyweight",
    },
    {
        "name": "Складка сидя на коврике",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "cooldown",
        "target_stat": "agility",
        "difficulty_level": 1,
        "equipment_type": "home",
    },
    {
        "name": "Растяжка голени у стены",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "cooldown",
        "target_stat": "agility",
        "difficulty_level": 1,
        "equipment_type": "home",
    },
    {
        "name": "Растяжка с полотенцем (подколенные)",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "cooldown",
        "target_stat": "agility",
        "difficulty_level": 1,
        "equipment_type": "home",
    },
    {
        "name": "Растяжка на мате в зале",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "cooldown",
        "target_stat": "agility",
        "difficulty_level": 1,
        "equipment_type": "gym",
    },
    {
        "name": "Растяжка с использованием скамьи",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "off_ice",
        "phase": "cooldown",
        "target_stat": "agility",
        "difficulty_level": 1,
        "equipment_type": "gym",
    },
    {
        "name": "Растяжка у борта",
        "description": PLACEHOLDER_DESCRIPTION,
        "category": "on_ice",
        "phase": "cooldown",
        "target_stat": "agility",
        "difficulty_level": 1,
        "equipment_type": "bodyweight",
    },
    # -- SetCompletion end-to-end test content: weight suggestion, per-set
    # logging, feedback, and state recovery all need at least one
    # tracks_weight main exercise plus a non-weighted warmup/cooldown pair.
    {
        "name": "Жим гантелей лёжа",
        "description": (
            "Лягте на скамью, стопы плотно стоят на полу, лопатки сведены и "
            "прижаты к скамье. Гантели держите над грудью на прямых руках, "
            "локти направлены в стороны примерно под углом 45 градусов к "
            "корпусу. Опускайте гантели до уровня груди подконтрольно, не "
            "роняя вес рывком, и выжимайте обратно вверх, не сталкивая "
            "гантели друг с другом."
        ),
        "category": "off_ice",
        "phase": "main",
        "target_stat": "strength",
        "difficulty_level": 3,
        "equipment_type": "gym",
        "tracks_weight": True,
        "bodyweight_ratio": 0.35,
        "target_sets": 3,
        "rep_range_min": 8,
        "rep_range_max": 12,
    },
    {
        "name": "Планка",
        "description": (
            "Обопритесь на предплечья и носки стоп, локти строго под "
            "плечами. Тело образует прямую линию от головы до пяток — таз "
            "не проваливается вниз и не поднимается вверх. Напрягите пресс "
            "и ягодицы, чтобы удерживать поясницу в нейтральном положении, "
            "и дышите ровно, не задерживая дыхание."
        ),
        "category": "off_ice",
        "phase": "warmup",
        # target_stat=strength -- the request offered intellect/endurance as
        # options, but the one existing plank/core exercise in this catalog
        # ("Планка на нестабильной поверхности") uses strength, so matching
        # that rather than either suggested option.
        "target_stat": "strength",
        "difficulty_level": 1,
        "equipment_type": "bodyweight",
        "tracks_weight": False,
        "target_duration_seconds": 45,
    },
    {
        "name": "Растяжка",
        "description": (
            "Растягивайте в первую очередь мышцы, которые больше всего "
            "работали на тренировке, заходя в каждую позицию плавно, без "
            "рывков, до лёгкого натяжения — не до боли. Задержитесь "
            "20-30 секунд на каждой мышце, дыхание при этом остаётся "
            "спокойным. Цель заминки — снизить мышечный тонус и вернуть "
            "пульс к норме, а не увеличить гибкость."
        ),
        "category": "off_ice",
        "phase": "cooldown",
        # target_stat wasn't specified in the request -- every existing
        # cooldown stretch exercise in this catalog uses agility.
        "target_stat": "agility",
        "difficulty_level": 1,
        "equipment_type": "bodyweight",
        "tracks_weight": False,
        "target_duration_seconds": 300,
    },
    {
        "name": "Румынская тяга",
        "description": (
            "Держите штангу или гантели перед бёдрами, ноги слегка "
            "согнуты в коленях и остаются в этом положении на всём "
            "движении. Наклоняйтесь вперёд, отводя таз назад — это "
            "движение в тазобедренном суставе, а не сгибание спины, "
            "поясница остаётся прямой. Снаряд скользит близко вдоль ног "
            "до ощутимого растяжения задней поверхности бедра, обычно "
            "чуть ниже колена, после чего возвращайтесь наверх за счёт "
            "разгибания бёдер, а не рывком спины."
        ),
        "category": "off_ice",
        "phase": "main",
        "target_stat": "strength",
        "difficulty_level": 4,
        "equipment_type": "gym",
        "tracks_weight": True,
        "bodyweight_ratio": 1.0,
        "target_sets": 3,
        "rep_range_min": 8,
        "rep_range_max": 12,
    },
]

# "Приседания со штангой" was already seeded in Phase 1, before
# tracks_weight/bodyweight_ratio/target_sets/rep_range_min/rep_range_max
# existed on Exercise
# -- Exercise.name is unique, so it can't be re-created under the same name
# with the new fields the request asked for. Filled in here instead of
# inserting a near-duplicate row. difficulty_level is deliberately left at
# its existing seeded value (4, not the requested 3): changing it would
# retroactively change periodization-phase exercise selection
# (app/core/training_block.py) and any past session's display for an
# exercise that may already be in use, which is a bigger change than
# "add test content".
#
# The other four SetCompletion test exercises hit the same problem one
# level down: they were already created by an earlier run of this script
# (their dicts are up in EXERCISES above), so adding "description" to those
# dicts alone does nothing on a re-run -- the insert loop skips them by name
# before it ever looks at their fields. Routed through here too so the
# description actually lands on the existing rows.
FIELD_UPDATES: list[tuple[str, dict]] = [
    (
        "Приседания со штангой",
        {
            "tracks_weight": True,
            "bodyweight_ratio": 0.75,
            "target_sets": 3,
            "rep_range_min": 6,
            "rep_range_max": 10,
            "description": (
                "Штанга лежит на верхней части трапеций, ноги на ширине "
                "плеч, носки чуть развёрнуты наружу. Приседайте, отводя таз "
                "назад и сохраняя естественный прогиб поясницы — колени "
                "двигаются в направлении носков, спина не округляется. "
                "Опускайтесь до параллели бёдер с полом или чуть ниже, "
                "затем вставайте, толкаясь через всю стопу."
            ),
        },
    ),
    (
        "Жим гантелей лёжа",
        {
            "description": (
                "Лягте на скамью, стопы плотно стоят на полу, лопатки "
                "сведены и прижаты к скамье. Гантели держите над грудью на "
                "прямых руках, локти направлены в стороны примерно под "
                "углом 45 градусов к корпусу. Опускайте гантели до уровня "
                "груди подконтрольно, не роняя вес рывком, и выжимайте "
                "обратно вверх, не сталкивая гантели друг с другом."
            ),
        },
    ),
    (
        "Планка",
        {
            "description": (
                "Обопритесь на предплечья и носки стоп, локти строго под "
                "плечами. Тело образует прямую линию от головы до пяток — "
                "таз не проваливается вниз и не поднимается вверх. "
                "Напрягите пресс и ягодицы, чтобы удерживать поясницу в "
                "нейтральном положении, и дышите ровно, не задерживая "
                "дыхание."
            ),
        },
    ),
    (
        "Растяжка",
        {
            "description": (
                "Растягивайте в первую очередь мышцы, которые больше всего "
                "работали на тренировке, заходя в каждую позицию плавно, "
                "без рывков, до лёгкого натяжения — не до боли. "
                "Задержитесь 20-30 секунд на каждой мышце, дыхание при "
                "этом остаётся спокойным. Цель заминки — снизить мышечный "
                "тонус и вернуть пульс к норме, а не увеличить гибкость."
            ),
        },
    ),
    (
        "Румынская тяга",
        {
            "description": (
                "Держите штангу или гантели перед бёдрами, ноги слегка "
                "согнуты в коленях и остаются в этом положении на всём "
                "движении. Наклоняйтесь вперёд, отводя таз назад — это "
                "движение в тазобедренном суставе, а не сгибание спины, "
                "поясница остаётся прямой. Снаряд скользит близко вдоль "
                "ног до ощутимого растяжения задней поверхности бедра, "
                "обычно чуть ниже колена, после чего возвращайтесь наверх "
                "за счёт разгибания бёдер, а не рывком спины."
            ),
        },
    ),
]


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        existing_names = set(
            (await session.execute(select(Exercise.name))).scalars().all()
        )

        created = 0
        # target_stat/equipment_type are no longer Exercise columns (see
        # ExerciseTargetStat/ExerciseEquipmentItem) -- popped per-dict here
        # rather than editing every literal in EXERCISES, and inserted as
        # companion rows once flush() has assigned ids.
        new_exercise_stats: list[tuple[Exercise, str]] = []
        new_exercise_items: list[tuple[Exercise, EquipmentItem]] = []
        for data in EXERCISES:
            if data["name"] in existing_names:
                continue
            # Guard against a duplicate name later in EXERCISES itself, not
            # just ones already in the DB -- existing_names is a snapshot
            # taken once above, so without adding to it here two identical
            # entries in the same run both pass the check and the second
            # insert hits the unique constraint on flush.
            existing_names.add(data["name"])
            data = dict(data)
            target_stat = data.pop("target_stat")
            equipment_item = _LEGACY_EQUIPMENT_ITEM[data.pop("equipment_type")]
            exercise = Exercise(**data)
            session.add(exercise)
            new_exercise_stats.append((exercise, target_stat))
            if equipment_item is not None:
                new_exercise_items.append((exercise, equipment_item))
            created += 1

        if new_exercise_stats:
            await session.flush()
            for exercise, target_stat in new_exercise_stats:
                session.add(
                    ExerciseTargetStat(
                        exercise_id=exercise.id, target_stat=TargetStat(target_stat), order=0
                    )
                )
            for exercise, equipment_item in new_exercise_items:
                session.add(
                    ExerciseEquipmentItem(exercise_id=exercise.id, equipment_item=equipment_item)
                )

        updated = 0
        for name, fields in FIELD_UPDATES:
            exercise = (
                await session.execute(select(Exercise).where(Exercise.name == name))
            ).scalar_one_or_none()
            if exercise is None:
                continue
            changed = any(getattr(exercise, field) != value for field, value in fields.items())
            if not changed:
                continue
            for field, value in fields.items():
                setattr(exercise, field, value)
            updated += 1

        # 2026-08-22: _LEGACY_EQUIPMENT_ITEM's "home"->DUMBBELLS placeholder
        # (see its own comment above) mistagged these three stick_handling
        # exercises when they were first seeded -- a stick-handling drill
        # needs a hockey stick, not dumbbells. Real per-exercise item
        # accuracy is generally Stage 4's job, but this one is fixed here
        # since it's the exact bug the personal-gear split (PERSONAL_GEAR_ITEMS,
        # app/models/exercise.py) exists to close: without a real exercise
        # requiring HOCKEY_STICK, that split has nothing to demonstrate.
        # Applies to existing rows too (delete-then-insert, idempotent), not
        # just fresh seeds -- re-running this script against a live DB fixes
        # it there as well, same as FIELD_UPDATES above.
        retagged = 0
        for exercise_name in _EQUIPMENT_ITEM_OVERRIDES:
            exercise = (
                await session.execute(select(Exercise).where(Exercise.name == exercise_name))
            ).scalar_one_or_none()
            if exercise is None:
                continue
            existing_items = set(
                (
                    await session.execute(
                        select(ExerciseEquipmentItem.equipment_item).where(
                            ExerciseEquipmentItem.exercise_id == exercise.id
                        )
                    )
                ).scalars().all()
            )
            desired_items = set(_EQUIPMENT_ITEM_OVERRIDES[exercise_name])
            if existing_items == desired_items:
                continue
            await session.execute(
                delete(ExerciseEquipmentItem).where(ExerciseEquipmentItem.exercise_id == exercise.id)
            )
            for item in desired_items:
                session.add(ExerciseEquipmentItem(exercise_id=exercise.id, equipment_item=item))
            retagged += 1

        # See _PHASE_OVERRIDES' own comment above.
        rephased = 0
        for exercise_name, desired_phase in _PHASE_OVERRIDES.items():
            exercise = (
                await session.execute(select(Exercise).where(Exercise.name == exercise_name))
            ).scalar_one_or_none()
            if exercise is None or exercise.phase == desired_phase:
                continue
            exercise.phase = desired_phase
            rephased += 1

        await session.commit()
        print(f"Seeded {created} new exercise(s), skipped {len(EXERCISES) - created} existing.")
        print(f"Updated {updated} existing exercise(s) with new fields.")
        print(f"Retagged {retagged} exercise(s) with corrected equipment items.")
        print(f"Rephased {rephased} exercise(s) into the puck module.")


if __name__ == "__main__":
    asyncio.run(seed())
