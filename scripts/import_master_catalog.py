"""One-off bulk import of icelevel_master_catalog.md into a freshly-zeroed
exercises table (2026-08-31: full catalog wipe + rebuild from the new
master list). Not idempotent-safe against partial re-runs the way
import_exercise_catalog.py is -- this assumes an empty (or at least
non-conflicting) `exercises` table and SKIPS a name that already exists
rather than updating it, so re-running after a partial failure just picks
up where it left off instead of duplicating.

Classification follows the in-app admin guide (ExerciseGuideModal.tsx)
exactly: every off_ice exercise gets a primary target_stat, every
exercise gets >=1 movement_pattern, every warmup-phase exercise gets a
warmup_stage, every tracks_weight exercise gets equipment. Everything in
this catalog is off_ice (the source doc's "hockey ice-specific" sections
are explicitly off-ice skating/shooting *simulation*, never real on-ice
content -- see icelevel_master_catalog.md Part N/Q headers).

Entries explicitly marked УДАЛЕНО in the source doc (Part R's
bodybuilding-isolation revision) are not included here at all.

Numeric set/rep/duration values are starting points for the double-
progression system, not literal prescriptions -- same convention as every
other hand-authored catalog entry (see ExerciseGuideModal section 5).
The source doc's "5-level" conditioning entries (Parts K/S) are modeled
as one catalog row each at a level-1-ish starting volume, since the app's
real personalization mechanism is per-user suggestion growth over time,
not discrete unlockable levels -- the level breakdown is preserved in the
description text instead.

Usage:

    poetry run python scripts/import_master_catalog.py
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
    MovementPattern,
    TargetStat,
)
from app.schemas.exercise import ExerciseCreate, MuscleGroupWeight  # noqa: E402
from app.services.exercise_service import ExerciseService  # noqa: E402


# ---- muscle-weight templates, reused across near-identical movements ----
SQUAT_M = {"quads": 0.5, "glutes": 0.3, "core": 0.2}
LUNGE_M = {"quads": 0.4, "glutes": 0.4, "core": 0.2}
HINGE_M = {"hamstrings": 0.4, "glutes": 0.4, "back": 0.2}
GLUTE_M = {"glutes": 0.6, "hamstrings": 0.2, "core": 0.2}
CALF_M = {"calves": 0.7, "quads": 0.3}
PUSH_M = {"chest": 0.5, "shoulders": 0.3, "core": 0.2}
PULL_M = {"back": 0.6, "shoulders": 0.2, "core": 0.2}
PULL_GRIP_M = {"back": 0.4, "forearms": 0.4, "core": 0.2}
CORE_M = {"core": 0.7, "back": 0.3}
CORE_ROT_M = {"core": 0.6, "shoulders": 0.2, "back": 0.2}
SHOULDER_M = {"shoulders": 0.6, "back": 0.2, "core": 0.2}
FOREARM_M = {"forearms": 0.8, "back": 0.2}
GRIP_HANG_M = {"forearms": 0.6, "back": 0.4}
FULLBODY_POWER_M = {"quads": 0.3, "glutes": 0.3, "core": 0.2, "shoulders": 0.2}
LOCOMOTION_M = {"quads": 0.3, "hamstrings": 0.2, "glutes": 0.2, "calves": 0.2, "core": 0.1}
ANKLE_M = {"calves": 0.6, "quads": 0.2, "core": 0.2}
HIP_FLEXOR_M = {"quads": 0.4, "glutes": 0.3, "core": 0.3}
ADDUCTOR_M = {"glutes": 0.3, "hamstrings": 0.3, "core": 0.4}
CHEST_MOBILITY_M = {"chest": 0.5, "shoulders": 0.3, "back": 0.2}
LAT_MOBILITY_M = {"back": 0.6, "shoulders": 0.4}
THORACIC_M = {"back": 0.5, "core": 0.3, "shoulders": 0.2}
NECK_M = {"back": 0.6, "core": 0.4}
WRIST_M = {"forearms": 0.8, "back": 0.2}


def E(
    name,
    desc,
    phase="main",
    stage=None,
    diff=2,
    vtype="sr",
    vol=(3, 8, 12),
    stimulus="strength",
    stats=("strength",),
    patterns=(),
    muscles=None,
    equip=(),
    uni=None,
    tw=False,
    bwr=None,
    game=False,
):
    if vtype == "sr":
        sets, rmin, rmax = vol
        target_sets, rep_min, rep_max, duration = sets, rmin, rmax, None
    else:
        target_sets, rep_min, rep_max, duration = None, None, None, vol
    return {
        "name": name,
        "description": desc,
        "category": "off_ice",
        "phase": phase,
        "warmup_stage": stage,
        "difficulty_level": diff,
        "exercise_type": "sets_reps" if vtype == "sr" else "duration",
        "target_sets": target_sets,
        "rep_range_min": rep_min,
        "rep_range_max": rep_max,
        "target_duration_seconds": duration,
        "tracks_weight": tw,
        "bodyweight_ratio": bwr,
        "suitable_for_game_day": game,
        "is_unilateral": uni,
        "stimulus_type": stimulus,
        "target_stats": list(stats),
        "movement_patterns": list(patterns),
        "muscle_groups": muscles or {},
        "equipment_items": list(equip),
    }


EXERCISES = []

# =========================================================================
# PART A -- mobility/rolling (warmup: joint_mobility, soft_tissue for
# roller/ball work)
# =========================================================================
EXERCISES += [
    E("Голеностоп у стены", "Стопа у стены, колено тянется к стене без отрыва пятки — раскачка тыльного сгибания голеностопа.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["ankle_mobility"], muscles=ANKLE_M, vtype="dur", vol=30, diff=1),
    E("Голеностоп 3 направления", "Наклон колена вперёд, затем по диагонали в обе стороны, стопа неподвижна — амплитуда голеностопа в трёх плоскостях.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["ankle_mobility"], muscles=ANKLE_M, vtype="dur", vol=30, diff=1),
    E("Круг голеностоп", "Стоя на одной ноге, круговые движения свободной стопой в обе стороны.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["ankle_mobility"], muscles=ANKLE_M, vtype="sr", vol=(2, 10, 10), diff=1),
    E("Голеностоп ПНФ", "Партнёр/резина создаёт сопротивление в конце амплитуды, короткое изометрическое напряжение, затем пассивное увеличение амплитуды.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["ankle_mobility"], muscles=ANKLE_M, equip=["resistance_band"], vtype="dur", vol=20, diff=1),
    E("Сгибатель бедра у стены", "Заднее колено у стены, таз подаётся вперёд без прогиба поясницы — растяжка сгибателя бедра.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["hip_mobility"], muscles=HIP_FLEXOR_M, vtype="dur", vol=30, diff=1),
    E("Сгибатель + резина боком", "Резина фиксирована сзади на уровне таза, выпадное положение с боковым натяжением резины усиливает растяжку сгибателя бедра.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["hip_mobility"], muscles=HIP_FLEXOR_M, equip=["resistance_band"], vtype="dur", vol=30, diff=1),
    E("Сгибатель + резина лицом", "Та же растяжка, резина фиксирована спереди — тракция сустава в другом направлении.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["hip_mobility"], muscles=HIP_FLEXOR_M, equip=["resistance_band"], vtype="dur", vol=30, diff=1),
    E("Сгибатель + лавочка + рука в потолок", "Заднее колено на скамье, рука на той же стороне тянется в потолок с лёгкой боковой наклонностью — растяжка сгибателя и косых мышц одновременно.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["hip_mobility"], muscles=HIP_FLEXOR_M, equip=["step_platform"], vtype="dur", vol=30, diff=1),
    E("Сгибатель ПНФ", "Контракт-релакс: короткое напряжение сгибателя против сопротивления партнёра, затем пассивное углубление растяжки.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["hip_mobility"], muscles=HIP_FLEXOR_M, vtype="dur", vol=20, diff=1),
    E("Голубь + лавочка", "Голень передней ноги на скамье, таз опускается вперёд-вниз — растяжка ягодичной и внешней ротации бедра.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["hip_mobility"], muscles=GLUTE_M, equip=["step_platform"], vtype="dur", vol=30, diff=1),
    E("Голубь ПНФ", "Поза голубя с контракт-релакс циклом для более глубокой растяжки наружных ротаторов бедра.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["hip_mobility"], muscles=GLUTE_M, vtype="dur", vol=20, diff=1),
    E("Привод в длинной позиции (гиря/резина)", "Широкая стойка, вес удерживается на согнутой ноге, растяжка приводящих в глубокой позиции.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["hip_mobility"], muscles=ADDUCTOR_M, equip=["kettlebell"], vtype="dur", vol=30, diff=1),
    E("Привод + вращение с весом", "Из широкой стойки лёгкое вращение таза с удержанием веса усиливает растяжку приводящих в динамике.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["hip_mobility"], muscles=ADDUCTOR_M, equip=["kettlebell"], vtype="sr", vol=(2, 8, 8), diff=1),
    E("Привод ПНФ", "Контракт-релакс цикл для приводящих мышц в широкой стойке.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["hip_mobility"], muscles=ADDUCTOR_M, vtype="dur", vol=20, diff=1),
    E("Грудной + резина", "Резина на уровне груди, разведение рук в стороны с раскрытием грудного отдела.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["shoulder_mobility"], muscles=CHEST_MOBILITY_M, equip=["resistance_band"], vtype="sr", vol=(2, 10, 10), diff=1),
    E("Грудной стоя в V-позиции", "Руки разведены вверх в форме V у дверного проёма, шаг вперёд растягивает грудные мышцы.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["shoulder_mobility"], muscles=CHEST_MOBILITY_M, vtype="dur", vol=30, diff=1),
    E("Грудной ПНФ", "Контракт-релакс растяжка грудных мышц у опоры.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["shoulder_mobility"], muscles=CHEST_MOBILITY_M, vtype="dur", vol=20, diff=1),
    E("Широчайшая + ротация", "Рука на возвышении, таз отводится назад с лёгкой ротацией корпуса — растяжка широчайшей.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["shoulder_mobility"], muscles=LAT_MOBILITY_M, vtype="dur", vol=30, diff=1),
    E("Широчайшая в висе", "Пассивный вис на перекладине с расслаблением плечевого пояса растягивает широчайшую мышцу.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["shoulder_mobility"], muscles=LAT_MOBILITY_M, equip=["pull_up_bar"], vtype="dur", vol=20, diff=1),
    E("90/90 наружная ротация", "Сидя в позиции 90/90, наклон корпуса к передней голени с сохранением вертикального таза.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["hip_mobility"], muscles=GLUTE_M, vtype="sr", vol=(2, 6, 6), diff=1),
    E("90/90 + вращение", "Переходы между сторонами позиции 90/90 через центр без помощи рук.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["hip_mobility"], muscles=GLUTE_M, vtype="sr", vol=(2, 6, 6), diff=1),
    E("Спайдермен + рука", "Глубокий выпад с опорой руки на пол, вторая рука тянется в потолок с ротацией грудного отдела.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["hip_mobility"], muscles=HIP_FLEXOR_M, vtype="sr", vol=(2, 6, 6), diff=1),
    E("Шаг барьер + палка в потолок", "Шаг через барьер с одновременным подъёмом палки над головой — мобильность бедра и плеча вместе.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["hip_mobility"], muscles=HIP_FLEXOR_M, vtype="sr", vol=(2, 8, 8), diff=1),
    E("Шаг барьер + подлезть под барьер", "Чередование шага через барьер и подныривания под него — мобильность бедра в обоих направлениях.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["hip_mobility"], muscles=HIP_FLEXOR_M, vtype="sr", vol=(2, 6, 6), diff=1),
    E("Раскатка роллом", "Медленный перекат проблемных зон (квадрицепс, задняя поверхность бедра, приводящие, ягодицы, поясница, лопатка) на валике, задержка на болезненных точках.", phase="warmup", stage="soft_tissue", stats=("agility",), patterns=["hip_mobility"], muscles={"quads": 0.3, "glutes": 0.3, "back": 0.2, "hamstrings": 0.2}, equip=["foam_roller"], vtype="dur", vol=60, diff=1),
    E("Раскатка мячом", "Точечная раскатка мячом (стопа, икры, грудь у стены, задний привод на тумбе) для локальных зажатых зон.", phase="warmup", stage="soft_tissue", stats=("agility",), patterns=["hip_mobility"], muscles={"calves": 0.4, "chest": 0.3, "glutes": 0.3}, vtype="dur", vol=60, diff=1),
]

# Part A -- activation/stability (warmup: activation)
EXERCISES += [
    E("Ягодичный мост 1 нога", "Лёжа на спине, одна стопа на полу, подъём таза за счёт ягодицы опорной ноги, вторая нога прямая в воздухе.", phase="warmup", stage="activation", stats=("agility",), patterns=["hip_hinge"], muscles=GLUTE_M, uni=True, vtype="sr", vol=(2, 10, 10)),
    E("Ягодичный мост 2 ноги + гантели/гриф", "Мост двумя ногами с отягощением на тазу для усиленной активации ягодиц.", phase="warmup", stage="activation", stats=("agility",), patterns=["hip_hinge"], muscles=GLUTE_M, equip=["dumbbells"], uni=False, vtype="sr", vol=(2, 12, 15)),
    E("Жук + антиротация", "Мёртвый жук с сохранением прижатой поясницы, попеременное разгибание противоположных руки и ноги.", phase="warmup", stage="activation", stats=("agility",), patterns=["core"], muscles=CORE_M, vtype="sr", vol=(2, 8, 8)),
    E("Жук + резина", "Та же схема мёртвого жука с резиной в руках для дополнительного антиротационного сопротивления.", phase="warmup", stage="activation", stats=("agility",), patterns=["core"], muscles=CORE_M, equip=["resistance_band"], vtype="sr", vol=(2, 8, 8)),
    E("Жук + рол статика", "Валик зажат между стопами в положении мёртвого жука, статическое удержание с дыханием.", phase="warmup", stage="activation", stats=("agility",), patterns=["core"], muscles=CORE_M, equip=["foam_roller"], vtype="dur", vol=20),
    E("Бёрдог", "На четвереньках, одновременное разгибание противоположных руки и ноги с неподвижным тазом.", phase="warmup", stage="activation", stats=("agility",), patterns=["core"], muscles=CORE_M, vtype="sr", vol=(2, 8, 8)),
    E("Бёрдог (нога на возвышенности)", "Та же схема, но опорная нога стоит на невысокой платформе — усложнённый баланс.", phase="warmup", stage="activation", stats=("agility",), patterns=["core"], muscles=CORE_M, equip=["step_platform"], vtype="sr", vol=(2, 8, 8)),
    E("Отведение бедра на четвереньках + минибенд", "На четвереньках, резина выше коленей, отведение согнутой ноги в сторону без разворота таза.", phase="warmup", stage="activation", stats=("agility",), patterns=["hip_mobility"], muscles=GLUTE_M, equip=["resistance_band"], uni=True, vtype="sr", vol=(2, 12, 12)),
    E("Отведение бедра лёжа", "Лёжа на боку, подъём верхней прямой ноги вверх без разворота таза назад.", phase="warmup", stage="activation", stats=("agility",), patterns=["hip_mobility"], muscles=GLUTE_M, uni=True, vtype="sr", vol=(2, 12, 12)),
    E("Отведение бедра стоя с резиной", "Резина на уровне лодыжек, стоя отведение прямой ноги в сторону с сохранением вертикального корпуса.", phase="warmup", stage="activation", stats=("agility",), patterns=["hip_mobility"], muscles=GLUTE_M, equip=["resistance_band"], uni=True, vtype="sr", vol=(2, 12, 12)),
    E("Раскрытие бедра с резиной + поворот", "Резина выше колена, из выпада раскрытие колена в сторону с ротацией корпуса вслед за движением.", phase="warmup", stage="activation", stats=("agility",), patterns=["hip_mobility"], muscles=GLUTE_M, equip=["resistance_band"], uni=True, vtype="sr", vol=(2, 10, 10)),
    E("Боковая планка (базовая)", "Упор на предплечье сбоку, тело прямой линией от плеча до стоп, таз не провисает.", phase="warmup", stage="activation", stats=("agility",), patterns=["core"], muscles=CORE_M, uni=True, vtype="dur", vol=30),
    E("Боковая планка (нога на лавочке)", "Боковая планка с верхней ногой на возвышении — усложнённый рычаг стабилизации.", phase="warmup", stage="activation", stats=("agility",), patterns=["core"], muscles=CORE_M, equip=["step_platform"], uni=True, vtype="dur", vol=30, diff=3),
    E("Боковая планка + ягодица", "Боковая планка с дополнительным подъёмом-опусканием верхней ноги для включения средней ягодичной.", phase="warmup", stage="activation", stats=("agility",), patterns=["core"], muscles={"core": 0.5, "glutes": 0.5}, uni=True, vtype="sr", vol=(2, 10, 10)),
    E("Боковая планка + привод", "Боковая планка с подтягиванием нижней ноги к верхней (зажатой на возвышении) — акцент на приводящие.", phase="warmup", stage="activation", stats=("agility",), patterns=["core"], muscles={"core": 0.5, "glutes": 0.3, "hamstrings": 0.2}, equip=["step_platform"], uni=True, diff=3, vtype="sr", vol=(2, 10, 10)),
    E("Прямая планка", "Упор на предплечьях, тело прямой линией, таз не поднят и не провисает.", phase="warmup", stage="activation", stats=("agility",), patterns=["core"], muscles=CORE_M, vtype="dur", vol=30),
    E("Ходьба лопатками по стене", "Спина у стены, руки скользят вверх-вниз по стене с сохранением контакта поясницы и лопаток.", phase="warmup", stage="activation", stats=("agility",), patterns=["shoulder_mobility"], muscles=SHOULDER_M, vtype="sr", vol=(2, 10, 10)),
    E("Слайд лопаток у стены", "Руки в позиции W у стены, скольжение вверх в Y с сохранением контакта локтей и запястий со стеной.", phase="warmup", stage="activation", stats=("agility",), patterns=["shoulder_mobility"], muscles=SHOULDER_M, vtype="sr", vol=(2, 10, 10)),
    E("Круг лопатки в упоре лежа", "В упоре лёжа на прямых руках, круговые протракции-ретракции лопаток без сгибания локтей.", phase="warmup", stage="activation", stats=("agility",), patterns=["shoulder_mobility"], muscles=SHOULDER_M, vtype="sr", vol=(2, 10, 10)),
    E("Антиротационный жим стоя", "Резина сбоку на уровне груди, жим вперёд прямыми руками с сопротивлением развороту корпуса.", phase="warmup", stage="activation", stats=("agility",), patterns=["core"], muscles=CORE_ROT_M, equip=["resistance_band"], vtype="sr", vol=(2, 10, 10)),
    E("Антиротационный жим сидя на коленях", "Та же схема жима сидя на одном/двух коленях — снижена компенсация ногами, выше требование к кору.", phase="warmup", stage="activation", stats=("agility",), patterns=["core"], muscles=CORE_ROT_M, equip=["resistance_band"], vtype="sr", vol=(2, 10, 10)),
    E("Антиротационный жим half-kneeling", "Половинное коленопреклонённое положение, жим резины вперёд с сопротивлением ротации таза.", phase="warmup", stage="activation", stats=("agility",), patterns=["core"], muscles=CORE_ROT_M, equip=["resistance_band"], uni=True, vtype="sr", vol=(2, 10, 10)),
    E("Lateral band walk", "Резина выше колен или на лодыжках, приставные шаги в сторону в полуприседе с сохранением натяжения резины.", phase="warmup", stage="activation", stats=("agility",), patterns=["hip_mobility"], muscles=GLUTE_M, equip=["resistance_band"], vtype="sr", vol=(2, 10, 10)),
    E("Наружная ротация гантели сидя", "Локоть прижат к боку, наружная ротация предплечья с лёгкой гантелью — активация ротаторной манжеты.", phase="warmup", stage="activation", stats=("agility",), patterns=["shoulder_mobility"], muscles=SHOULDER_M, equip=["dumbbells"], vtype="sr", vol=(2, 12, 15)),
    E("Наружная ротация гантели лёжа", "Лёжа на боку, та же наружная ротация плеча с гантелью для более изолированной активации.", phase="warmup", stage="activation", stats=("agility",), patterns=["shoulder_mobility"], muscles=SHOULDER_M, equip=["dumbbells"], vtype="sr", vol=(2, 12, 15)),
]

# Part A -- dynamic warmup (warmup: dynamic)
_dyn = [
    ("A-скип", "Скип с высоким подъёмом бедра и активной работой рук, короткое время контакта с полом."),
    ("N-скип", "Скип с акцентом на разгибание голени вперёд после подъёма колена, N-образная траектория стопы."),
    ("Мощный скип", "Скип с максимально высоким подъёмом колена и мощным отталкиванием, продвинутая версия A-скипа."),
    ("Боковой скип", "Скип боком, колено поднимается в сторону движения."),
    ("Боковой кроссовер скип", "Боковой скип с заведением маховой ноги крестом перед опорной."),
    ("Захлёст", "Бег на месте/вперёд с захлёстом голени назад к ягодице."),
    ("Высокие бёдра", "Бег на месте/вперёд с максимально высоким подъёмом колена."),
    ("Спиной вперёд", "Бег спиной вперёд с сохранением низкой стойки и контролем шага."),
    ("Кариока", "Приставной шаг с попеременным заведением ноги вперёд и назад скрестно."),
    ("Приставной шаг", "Боковое перемещение приставным шагом в невысокой стойке."),
    ("Скрестный шаг", "Боковое перемещение с шагом одной ногой скрестно перед другой."),
    ("Кроссовер", "Боковое перемещение с заведением одной ноги крестом перед другой в динамике."),
    ("Обратный кроссовер", "То же движение с заведением ноги крестом позади опорной."),
    ("Ходьба через барьеры лицом", "Шаг через невысокие барьеры лицом вперёд с высоким подъёмом колена."),
    ("Ходьба через барьеры спиной", "То же упражнение, движение спиной вперёд."),
    ("Выпад назад + открыть бедро", "Выпад назад с последующим раскрытием колена в сторону — мобильность и активация одновременно."),
    ("Выпад вперёд + закрыть бедро", "Выпад вперёд с последующим приведением колена к центру."),
    ("Боковой выпад + перекат", "Боковой выпад с переносом веса и перекатом на другую ногу без остановки."),
    ("Ходьба руки+ноги", "Инчворм в динамике: наклон, проход руками вперёд, подтягивание ног, подъём в шаг."),
    ("Бег прямые ноги", "Бег с прямыми ногами и минимальным сгибом колена, акцент на работу от бедра."),
    ("Линейный марш", "Марш с высоким подъёмом колена по прямой линии, контролируемый темп."),
    ("Марш с прямой ногой", "Марш с махом прямой ногой вперёд к разноимённой руке."),
]
EXERCISES += [
    E(name, desc, phase="warmup", stage="dynamic", stats=("agility",), patterns=["locomotion"], muscles=LOCOMOTION_M, vtype="dur", vol=30)
    for name, desc in _dyn
]

# Part A -- lower body strength (main)
EXERCISES += [
    E("Сплит-присед с гантелями", "Задняя нога на подставке или на полу, гантели в руках, глубокий присед с вертикальным корпусом.", stats=("strength",), patterns=["squat"], muscles=LUNGE_M, equip=["dumbbells"], uni=True, diff=2, vtype="sr", vol=(3, 8, 12)),
    E("Сплит-присед на подставке", "Та же схема с задней ногой приподнятой на невысокой опоре для увеличения амплитуды.", stats=("strength",), patterns=["squat"], muscles=LUNGE_M, uni=True, diff=2, vtype="sr", vol=(3, 8, 12)),
    E("Сплит-присед изометрический", "Удержание нижней точки сплит-приседа с максимальным произвольным усилием несколько секунд.", stats=("strength",), patterns=["squat"], muscles=LUNGE_M, uni=True, diff=3, vtype="dur", vol=20),
    E("Фронтальный/гоблет присед", "Гантель/гиря у груди, присед с вертикальным корпусом и глубокой амплитудой.", stats=("strength",), patterns=["squat"], muscles=SQUAT_M, equip=["dumbbells"], tw=True, bwr=0.3, diff=2, vtype="sr", vol=(3, 8, 12)),
    E("Трэп-гриф присед", "Присед со штангой в трэп-грифе, нейтральный хват снижает нагрузку на поясницу при том же весе.", stats=("strength",), patterns=["squat"], muscles=SQUAT_M, equip=["barbell"], tw=True, bwr=0.6, diff=3, vtype="sr", vol=(4, 6, 10)),
    E("Румынская тяга 1 нога 2 гантели", "Стоя на одной ноге, гантели в обеих руках, наклон корпуса вперёд с прямой линией от головы до пятки свободной ноги.", stats=("strength",), patterns=["hip_hinge"], muscles=HINGE_M, equip=["dumbbells"], tw=True, bwr=0.3, uni=True, diff=3, vtype="sr", vol=(3, 8, 10)),
    E("Румынская тяга гриф/гантели", "Минимальный сгиб колена, отведение таза назад, гриф/гантели скользят вдоль ног.", stats=("strength",), patterns=["hip_hinge"], muscles=HINGE_M, equip=["barbell"], tw=True, bwr=0.5, diff=2, vtype="sr", vol=(3, 8, 12)),
    E("Ягодичный мост 1 нога + гриф", "Мост на одной ноге с грифом на тазу для увеличения нагрузки на ягодицу.", stats=("strength",), patterns=["hip_hinge"], muscles=GLUTE_M, equip=["barbell"], tw=True, bwr=0.3, uni=True, diff=3, vtype="sr", vol=(3, 8, 12)),
    E("Болгарский присед", "Задняя нога на скамье, глубокий присед на передней ноге с гантелями в руках.", stats=("strength",), patterns=["squat"], muscles=LUNGE_M, equip=["dumbbells", "step_platform"], tw=True, bwr=0.3, uni=True, diff=3, vtype="sr", vol=(3, 8, 12)),
    E("Степ-ап прыжок", "Взрывной подъём на возвышение с последующим лёгким отрывом от платформы вверху.", stats=("strength", "agility"), patterns=["squat"], muscles=LUNGE_M, equip=["step_platform"], stimulus="power", uni=True, diff=3, vtype="sr", vol=(3, 6, 8)),
    E("Спрыгивание с тумбы 1 нога", "Шаг с тумбы, мягкое приземление на одну ногу с полным контролем колена.", stats=("agility",), patterns=["squat"], muscles=LUNGE_M, equip=["step_platform"], stimulus="power", uni=True, diff=3, vtype="sr", vol=(3, 5, 5)),
    E("Прыжок тумба 1 нога", "Отталкивание одной ногой с места, запрыгивание на тумбу той же ногой.", stats=("agility",), patterns=["squat"], muscles=LUNGE_M, equip=["step_platform"], stimulus="power", uni=True, diff=3, vtype="sr", vol=(3, 5, 5)),
    E("Выпад назад с грифом", "Шаг назад в выпад со штангой на спине, возврат в исходное положение через переднюю ногу.", stats=("strength",), patterns=["squat"], muscles=LUNGE_M, equip=["barbell"], tw=True, bwr=0.4, uni=True, diff=2, vtype="sr", vol=(3, 8, 10)),
    E("Выпад назад с гантелями", "Та же схема выпада назад с гантелями в руках вместо штанги на спине.", stats=("strength",), patterns=["squat"], muscles=LUNGE_M, equip=["dumbbells"], tw=True, bwr=0.3, uni=True, diff=2, vtype="sr", vol=(3, 8, 10)),
    E("Боковой выпад лендмайн", "Один конец штанги зафиксирован в углу, боковой выпад с удержанием грифа у груди для противовеса.", stats=("strength",), patterns=["squat"], muscles=LUNGE_M, equip=["barbell"], tw=True, bwr=0.3, uni=True, diff=3, vtype="sr", vol=(3, 8, 10)),
    E("Боковой выпад на слайдах + резина", "Опорная нога на слайд-диске, скользящий боковой выпад с резиной вокруг таза для дополнительного сопротивления.", stats=("strength",), patterns=["squat"], muscles=LUNGE_M, equip=["resistance_band"], uni=True, diff=3, vtype="sr", vol=(3, 8, 10)),
    E("Латеральный выпад с гантелью на слайде", "Гантель у груди, скользящий боковой выпад на слайд-диске с контролируемым возвратом.", stats=("strength",), patterns=["squat"], muscles=LUNGE_M, equip=["dumbbells"], tw=True, bwr=0.2, uni=True, diff=3, vtype="sr", vol=(3, 8, 10)),
    E("Внутренний выпад + слайд", "Скользящий шаг внутрь скрестно с приведением бедра, акцент на приводящие мышцы.", stats=("strength",), patterns=["squat"], muscles={"quads": 0.3, "glutes": 0.3, "hamstrings": 0.2, "core": 0.2}, uni=True, diff=3, vtype="sr", vol=(3, 8, 10)),
    E("Сгибание ног на мяче", "Лёжа на спине, пятки на фитболе, подъём таза и подкат мяча сгибанием голени.", stats=("strength",), patterns=["hip_hinge"], muscles=HINGE_M, diff=2, vtype="sr", vol=(3, 10, 12)),
    E("Сгибание ног на тренажёре", "Изолированное сгибание голени лёжа на животе в тренажёре, акцент на заднюю поверхность бедра.", stats=("strength",), patterns=["hip_hinge"], muscles=HINGE_M, equip=["dumbbells"], diff=2, vtype="sr", vol=(3, 10, 12)),
    E("Приведение бедра с резиной", "Резина фиксирована сбоку на уровне лодыжки, приведение прямой ноги к центру против сопротивления.", stats=("strength",), patterns=["hip_mobility"], muscles=ADDUCTOR_M, equip=["resistance_band"], uni=True, diff=2, vtype="sr", vol=(3, 12, 15)),
    E("Разгибание голеностопа с резиной сидя", "Сидя, резина на стопе, разгибание (тыльное сгибание) стопы против сопротивления резины.", stats=("strength",), patterns=["ankle_mobility"], muscles=ANKLE_M, equip=["resistance_band"], diff=1, vtype="sr", vol=(3, 12, 15)),
]

# Part A -- upper body strength (main)
EXERCISES += [
    E("Жим лёжа гантели", "Гантели опускаются к груди, жим вверх до почти полного разгибания рук.", stats=("strength",), patterns=["push"], muscles=PUSH_M, equip=["dumbbells"], tw=True, bwr=0.4, diff=2, vtype="sr", vol=(3, 8, 12)),
    E("Жим лёжа гриф", "Штанга опускается к нижней части груди, локти под ~45°, подъём до полного разгибания.", stats=("strength",), patterns=["push"], muscles=PUSH_M, equip=["barbell"], tw=True, bwr=0.6, diff=3, vtype="sr", vol=(3, 6, 10)),
    E("Жим гантелей на наклонной скамье", "Угол скамьи 30-45°, жим гантелей вверх с акцентом на верхнюю часть груди.", stats=("strength",), patterns=["push"], muscles=PUSH_M, equip=["dumbbells"], tw=True, bwr=0.4, diff=2, vtype="sr", vol=(3, 8, 12)),
    E("Жим лендмайн стоя", "Один конец штанги в углу, жим свободного конца от плеча вперёд-вверх стоя.", stats=("strength",), patterns=["push"], muscles=PUSH_M, equip=["barbell"], tw=True, bwr=0.3, uni=True, diff=2, vtype="sr", vol=(3, 8, 12)),
    E("Горизонтальная тяга с опорой груди на лавочку", "Грудь опирается на наклонную скамью, тяга гантелей к корпусу без читинга поясницей.", stats=("strength",), patterns=["pull"], muscles=PULL_M, equip=["dumbbells"], tw=True, bwr=0.3, diff=2, vtype="sr", vol=(3, 8, 12)),
    E("Горизонтальный жим сидя на 1 колене", "Half-kneeling позиция, жим резины/гантели вперёд одной рукой с антиротационным контролем корпуса.", stats=("strength",), patterns=["push"], muscles=PUSH_M, equip=["resistance_band"], uni=True, diff=2, vtype="sr", vol=(3, 10, 12)),
    E("Горизонтальная тяга сидя на 1 колене", "Half-kneeling позиция, тяга резины к корпусу одной рукой с контролем ротации таза.", stats=("strength",), patterns=["pull"], muscles=PULL_M, equip=["resistance_band"], uni=True, diff=2, vtype="sr", vol=(3, 10, 12)),
    E("Тяга гантели в наклоне", "Наклон корпуса вперёд, тяга гантели к бедру, лопатка сводится в конце движения.", stats=("strength",), patterns=["pull"], muscles=PULL_M, equip=["dumbbells"], tw=True, bwr=0.3, uni=True, diff=2, vtype="sr", vol=(3, 8, 12)),
    E("TRX-подтягивания", "Тело под наклоном, петли TRX в руках, подтягивание корпуса к рукам с прямой линией тела.", stats=("strength",), patterns=["pull"], muscles=PULL_M, diff=2, vtype="sr", vol=(3, 8, 12)),
    E("Подтягивания нейтральный хват", "Хват ладонями друг к другу, подтягивание подбородком к перекладине.", stats=("strength",), patterns=["pull"], muscles=PULL_GRIP_M, equip=["pull_up_bar"], diff=3, vtype="sr", vol=(3, 5, 10)),
    E("Отжимания классические", "Упор лёжа, руки чуть шире плеч, сгибание локтей до касания грудью пола, тело прямой линией.", stats=("strength",), patterns=["push"], muscles=PUSH_M, diff=1, vtype="sr", vol=(3, 10, 15)),
    E("Отжимания с прыжком", "Взрывное отжимание с отрывом рук от пола, мягкое приземление под контролем.", stats=("strength", "agility"), patterns=["push"], muscles=PUSH_M, stimulus="power", diff=3, vtype="sr", vol=(3, 6, 10)),
    E("Y-сгибания с гантелями", "Лёжа грудью на наклонной скамье, подъём лёгких гантелей по траектории буквы Y.", stats=("strength",), patterns=["pull"], muscles=SHOULDER_M, equip=["dumbbells"], diff=2, vtype="sr", vol=(3, 10, 15)),
    E("Отведение гантели лёжа на боку", "Лёжа на боку, отведение прямой руки с лёгкой гантелью вверх-назад — акцент на заднюю дельту.", stats=("strength",), patterns=["pull"], muscles=SHOULDER_M, equip=["dumbbells"], uni=True, diff=1, vtype="sr", vol=(3, 12, 15)),
    E("Наружная ротация с резиной+Y", "Комбинация наружной ротации плеча и подъёма в Y с резиной для полной активации ротаторной манжеты.", stats=("strength",), patterns=["pull"], muscles=SHOULDER_M, equip=["resistance_band"], diff=1, vtype="sr", vol=(3, 10, 12)),
    E("Прогулка фермера 1 рука", "Груз в одной руке, ходьба с сохранением строго вертикального корпуса без наклона в сторону груза.", stats=("strength",), patterns=["pull"], muscles=FOREARM_M, equip=["dumbbells"], tw=True, bwr=0.5, uni=True, diff=2, vtype="sr", vol=(3, 20, 20)),
    E("Прогулка фермера 2 руки", "Груз в обеих руках, ходьба с сохранением осанки и напряжённого кора на дистанцию.", stats=("strength",), patterns=["pull"], muscles=FOREARM_M, equip=["dumbbells"], tw=True, bwr=0.6, diff=2, vtype="sr", vol=(3, 20, 20)),
    E("Прогулка вайтера 1 рука", "Груз удерживается прямой рукой над головой, ходьба с сохранением вертикального корпуса.", stats=("strength",), patterns=["core"], muscles={"shoulders": 0.4, "core": 0.4, "forearms": 0.2}, equip=["dumbbells"], tw=True, bwr=0.3, uni=True, diff=3, vtype="sr", vol=(3, 15, 15)),
]

# Part A -- power/speed (main)
EXERCISES += [
    E("Спринт 2 точки", "Короткий максимальный спринт между двумя фиксированными точками с полным разгоном.", stats=("agility", "on_ice_skating"), patterns=["locomotion"], muscles=FULLBODY_POWER_M, stimulus="power", diff=2, vtype="sr", vol=(4, 1, 1)),
    E("Спринт 1/2 с колена", "Старт с одного/двух колен, мощное первое отталкивание в спринт на короткую дистанцию.", stats=("agility", "on_ice_skating"), patterns=["locomotion"], muscles=FULLBODY_POWER_M, stimulus="power", diff=2, vtype="sr", vol=(4, 1, 1)),
    E("Спринт 5-10-5", "Спринт 5 метров, разворот, 10 метров в другую сторону, разворот, 5 метров на старт.", stats=("agility",), patterns=["locomotion"], muscles=FULLBODY_POWER_M, stimulus="power", diff=3, vtype="sr", vol=(4, 1, 1)),
    E("Спринт с боковым стартом", "Старт из бокового положения тела относительно направления бега, разворот и ускорение.", stats=("agility", "on_ice_skating"), patterns=["locomotion"], muscles=FULLBODY_POWER_M, stimulus="power", diff=2, vtype="sr", vol=(4, 1, 1)),
    E("Прыжок через барьер 1 нога лицом", "Серия прыжков через невысокие барьеры на одной ноге лицом вперёд, минимальное время контакта.", stats=("agility",), patterns=["squat"], muscles=LUNGE_M, stimulus="power", uni=True, diff=3, vtype="sr", vol=(3, 5, 5)),
    E("Прыжок через барьер 1 нога боком", "Та же серия прыжков боком относительно барьеров.", stats=("agility",), patterns=["squat"], muscles=LUNGE_M, stimulus="power", uni=True, diff=3, vtype="sr", vol=(3, 5, 5)),
    E("Прыжок в длину с паузой", "Прыжок вперёд с двух ног, полная остановка и удержание баланса в точке приземления 2-3 сек.", stats=("agility",), patterns=["squat"], muscles=FULLBODY_POWER_M, stimulus="power", diff=2, vtype="sr", vol=(3, 5, 5)),
    E("Прыжок на тумбу 1 нога лицом", "Отталкивание одной ногой лицом к тумбе, запрыгивание с мягким приземлением на ту же ногу.", stats=("agility",), patterns=["squat"], muscles=LUNGE_M, equip=["step_platform"], stimulus="power", uni=True, diff=3, vtype="sr", vol=(3, 5, 5)),
    E("Прыжок на тумбу 1 нога боком", "Та же схема с боковым расположением относительно тумбы.", stats=("agility",), patterns=["squat"], muscles=LUNGE_M, equip=["step_platform"], stimulus="power", uni=True, diff=3, vtype="sr", vol=(3, 5, 5)),
    E("Боковой скачок через барьер", "Прыжок вбок через ряд невысоких барьеров, приземление под контролем на каждый.", stats=("agility",), patterns=["squat"], muscles=FULLBODY_POWER_M, stimulus="power", diff=3, vtype="sr", vol=(3, 6, 6)),
    E("Боковой скачок 45°+пауза", "Прыжок по диагонали 45° с полной остановкой в точке приземления перед следующим повторением.", stats=("agility",), patterns=["squat"], muscles=FULLBODY_POWER_M, stimulus="power", diff=2, vtype="sr", vol=(3, 5, 5)),
    E("Ротационный бросок мяча стоя", "Стоя боком к стене, ротационный бросок мяча за счёт вращения корпуса и переноса веса.", stats=("agility", "strength"), patterns=["rotation"], muscles=CORE_ROT_M, equip=["medicine_ball"], stimulus="power", diff=2, vtype="sr", vol=(3, 6, 8)),
    E("Ротационный бросок мяча в сплит-позиции", "Та же схема броска из выпадной стойки — добавляет включение ног в ротацию.", stats=("agility", "strength"), patterns=["rotation"], muscles=CORE_ROT_M, equip=["medicine_ball"], stimulus="power", diff=3, vtype="sr", vol=(3, 6, 8)),
    E("Ротационный бросок мяча латерально", "Бросок мяча сбоку с широкой стойкой, акцент на боковую мощность бёдер.", stats=("agility", "strength"), patterns=["rotation"], muscles=CORE_ROT_M, equip=["medicine_ball"], stimulus="power", diff=3, vtype="sr", vol=(3, 6, 8)),
    E("Бросок мяча от груди стоя", "Мяч выталкивается двумя руками от груди максимально далеко/сильно.", stats=("strength", "agility"), patterns=["push"], muscles=PUSH_M, equip=["medicine_ball"], stimulus="power", diff=2, vtype="sr", vol=(3, 6, 8)),
    E("Бросок мяча от груди + шаг", "Тот же бросок с предварительным шагом вперёд для добавления мощности ног.", stats=("strength", "agility"), patterns=["push"], muscles=PUSH_M, equip=["medicine_ball"], stimulus="power", diff=2, vtype="sr", vol=(3, 6, 8)),
    E("Слэм мяча в пол", "Мяч поднимается над головой и максимально резко швыряется в пол.", stats=("strength", "agility"), patterns=["core"], muscles=CORE_M, equip=["medicine_ball"], stimulus="power", diff=2, vtype="sr", vol=(3, 8, 10)),
    E("Слэм мяча с полукругом", "Слэм мяча с предварительным заведением по дуге в сторону для добавления ротации.", stats=("strength", "agility"), patterns=["rotation"], muscles=CORE_ROT_M, equip=["medicine_ball"], stimulus="power", diff=3, vtype="sr", vol=(3, 8, 10)),
    E("Свинг гирей", "Мах гири двумя руками от бёдер до уровня груди за счёт взрывного разгибания таза, руки — просто рычаг.", stats=("strength", "agility"), patterns=["hip_hinge"], muscles=HINGE_M, equip=["kettlebell"], tw=True, bwr=0.3, stimulus="power", diff=2, vtype="sr", vol=(3, 12, 15)),
    E("Толкание саней", "Сани толкаются вперёд руками из наклонного положения корпуса на дистанцию.", stats=("strength", "agility"), patterns=["squat"], muscles=FULLBODY_POWER_M, stimulus="power", diff=2, vtype="sr", vol=(4, 1, 1)),
    E("Тяга саней", "Сани тянутся на ремне/верёвке шагом назад или вперёд на дистанцию.", stats=("strength", "agility"), patterns=["hip_hinge"], muscles=FULLBODY_POWER_M, stimulus="power", diff=2, vtype="sr", vol=(4, 1, 1)),
]

# Part A -- core/anti-rotation (main)
EXERCISES += [
    E("Дровосек с нижней позиции", "Тяга резины/блока по диагонали снизу вверх через корпус с ротацией и разгибанием.", stats=("strength",), patterns=["rotation"], muscles=CORE_ROT_M, equip=["resistance_band"], diff=2, vtype="sr", vol=(3, 10, 12)),
    E("Дровосек с верхней позиции", "Та же тяга по диагонали, но сверху вниз — имитация рубящего движения.", stats=("strength",), patterns=["rotation"], muscles=CORE_ROT_M, equip=["resistance_band"], diff=2, vtype="sr", vol=(3, 10, 12)),
    E("Роллаут+кольца", "Из колен, кольца выкатываются вперёд с сохранением прямой линии тела и напряжённого пресса.", stats=("strength",), patterns=["core"], muscles=CORE_M, diff=3, vtype="sr", vol=(3, 8, 10)),
    E("Ноумани в сплит-позиции по диагонали", "Из выпадной стойки, планка на кистях с попеременным подъёмом противоположной руки/ноги по диагонали.", stats=("strength",), patterns=["core"], muscles=CORE_M, diff=3, vtype="sr", vol=(3, 6, 6)),
    E("Ноумани прямые руки", "Планка на прямых руках с попеременным подъёмом-опусканием противоположных конечностей.", stats=("strength",), patterns=["core"], muscles=CORE_M, diff=2, vtype="sr", vol=(3, 6, 6)),
    E("Копенгаген-планка короткий рычаг", "Боковая планка с верхней ногой на скамье, нижняя нога согнута — сильная нагрузка на приводящие.", stats=("strength",), patterns=["core"], muscles={"core": 0.4, "hamstrings": 0.3, "glutes": 0.3}, equip=["step_platform"], uni=True, diff=3, vtype="dur", vol=20),
    E("Антиротационный жим+3 шага", "Резина зафиксирована сбоку, три шага в сторону от точки крепления с удержанием жима перед грудью без разворота.", stats=("strength",), patterns=["core"], muscles=CORE_ROT_M, equip=["resistance_band"], diff=2, vtype="sr", vol=(3, 6, 6)),
    E("Боковая планка+лавочка+жим блина", "Боковая планка с ногами на скамье, свободная рука выжимает блин вверх без потери положения таза.", stats=("strength",), patterns=["core"], muscles=CORE_M, equip=["step_platform", "dumbbells"], uni=True, diff=3, vtype="sr", vol=(3, 8, 8)),
]

# Part A -- ankle/wrist rehab (cooldown -- low intensity, restorative slot)
EXERCISES += [
    E("Спринг-анкл уровни 1-5", "Прогрессия упражнений на упругость голеностопа от простого удержания баланса до реактивных прыжков — сложность растёт вместе с игроком.", phase="cooldown", stats=("agility",), patterns=["ankle_mobility"], muscles=ANKLE_M, diff=1, vtype="dur", vol=30),
    E("Присед 1 нога у стены+палец в пол", "У стены для баланса, присед на одной ноге с касанием пальцами свободной руки пола.", phase="cooldown", stats=("agility",), patterns=["squat"], muscles=LUNGE_M, uni=True, diff=2, vtype="sr", vol=(2, 8, 8)),
    E("Повороты голеностопа", "Медленные контролируемые повороты стопы во всех направлениях для реабилитации после травмы.", phase="cooldown", stats=("agility",), patterns=["ankle_mobility"], muscles=ANKLE_M, diff=1, vtype="dur", vol=30),
    E("Пальцы вверх+носки к себе", "Сидя, попеременный подъём пальцев стопы и всей стопы на себя — активация переднего отдела голени.", phase="cooldown", stats=("agility",), patterns=["ankle_mobility"], muscles=ANKLE_M, diff=1, vtype="sr", vol=(2, 15, 15)),
    E("Ходьба с носками", "Ходьба на пальцах ног короткими шагами для укрепления переднего свода стопы.", phase="cooldown", stats=("agility",), patterns=["ankle_mobility"], muscles=ANKLE_M, diff=1, vtype="dur", vol=30),
    E("Пронация кисти", "Предплечье на опоре, поворот кисти ладонью вниз против лёгкого сопротивления — реабилитация после силовой на хват.", phase="cooldown", stats=("strength",), patterns=["wrist_mobility"], muscles=WRIST_M, diff=1, vtype="sr", vol=(2, 12, 15)),
    E("Супинация кисти", "То же движение в обратную сторону, ладонью вверх.", phase="cooldown", stats=("strength",), patterns=["wrist_mobility"], muscles=WRIST_M, diff=1, vtype="sr", vol=(2, 12, 15)),
]

# =========================================================================
# PART B -- new package (already reasonably specific in the source doc)
# =========================================================================
EXERCISES += [
    E("Присед со штангой на спине", "Штанга на трапециях, приседание с отведением таза назад до параллели бёдер полу, подъём через пятки.", stats=("strength",), patterns=["squat"], muscles=SQUAT_M, equip=["barbell"], tw=True, bwr=0.7, diff=3, vtype="sr", vol=(4, 6, 10)),
    E("Присед со штангой на груди", "Гриф на передних дельтах, локти высоко, корпус вертикальный на всей амплитуде.", stats=("strength",), patterns=["squat"], muscles=SQUAT_M, equip=["barbell"], tw=True, bwr=0.6, diff=3, vtype="sr", vol=(4, 6, 10)),
    E("Становая тяга классическая", "Гриф над серединой стопы, нейтральная спина, подъём одновременным разгибанием таза и колена.", stats=("strength",), patterns=["hip_hinge"], muscles=HINGE_M, equip=["barbell"], tw=True, bwr=0.8, diff=4, vtype="sr", vol=(4, 4, 8)),
    E("Становая тяга сумо", "Широкая постановка ног, носки развёрнуты, хват уже стойки ног, акцент на приводящих и ягодицах.", stats=("strength",), patterns=["hip_hinge"], muscles=HINGE_M, equip=["barbell"], tw=True, bwr=0.8, diff=4, vtype="sr", vol=(4, 4, 8)),
    E("Пистолетик", "Опорная нога приседает максимально глубоко, вторая нога вытянута вперёд, руки для баланса.", stats=("strength", "agility"), patterns=["squat"], muscles=LUNGE_M, uni=True, diff=4, vtype="sr", vol=(3, 5, 8)),
    E("Приседания с выпрыгиванием", "Присед до параллели, взрывной прыжок вверх, мягкое приземление.", stats=("agility", "strength"), patterns=["squat"], muscles=SQUAT_M, stimulus="power", diff=2, vtype="sr", vol=(3, 8, 10)),
    E("Берпи", "Присед-упор-выброс ног-отжимание-возврат-прыжок, максимальный темп.", stats=("endurance", "agility"), patterns=["core"], muscles=FULLBODY_POWER_M, stimulus="power", diff=2, vtype="dur", vol=30),
    E("Скалолаз", "Упор лёжа, попеременное подтягивание колена к груди в быстром темпе.", stats=("endurance", "agility"), patterns=["core"], muscles=CORE_M, diff=1, vtype="dur", vol=30),
    E("Приседания сумо с гантелью", "Широкая стойка, гантель между ног, глубокий присед с вертикальным корпусом.", stats=("strength",), patterns=["squat"], muscles=SQUAT_M, equip=["dumbbells"], tw=True, bwr=0.3, diff=2, vtype="sr", vol=(3, 10, 12)),
    E("Обратные отжимания от скамьи", "Руки на краю скамьи за спиной, сгибание локтей до 90°, подъём через трицепс.", stats=("strength",), patterns=["push"], muscles=PUSH_M, equip=["step_platform"], diff=2, vtype="sr", vol=(3, 10, 15)),
    E("Депт-джамп с тумбы", "Шаг с тумбы, мгновенное реактивное отталкивание при касании пола.", stats=("agility",), patterns=["squat"], muscles=LUNGE_M, equip=["step_platform"], stimulus="power", diff=4, vtype="sr", vol=(3, 5, 5)),
    E("Бокс-джамп", "Прыжок на возвышение с мягким приземлением на согнутые колени.", stats=("agility",), patterns=["squat"], muscles=SQUAT_M, equip=["step_platform"], stimulus="power", diff=2, vtype="sr", vol=(3, 6, 8)),
    E("Латеральный бокс-джамп", "Прыжок вбок на тумбу, контроль приземления.", stats=("agility",), patterns=["squat"], muscles=SQUAT_M, equip=["step_platform"], stimulus="power", diff=3, vtype="sr", vol=(3, 6, 8)),
    E("Двойные прыжки на скакалке", "Скакалка проходит под ногами дважды за один прыжок, требует высокой координации.", stats=("agility", "endurance"), patterns=["coordination"], muscles=CALF_M, equip=["jump_rope"], diff=3, vtype="dur", vol=30),
    E("Split jump", "Выпад, взрывная смена ног в прыжке, мягкое приземление в выпад на другую ногу.", stats=("agility",), patterns=["squat"], muscles=LUNGE_M, stimulus="power", diff=3, vtype="sr", vol=(3, 8, 10)),
    E("Отжимания на кольцах", "Упор на кольцах, стабилизация в стороны, сгибание рук до ~90°.", stats=("strength",), patterns=["push"], muscles=PUSH_M, diff=4, vtype="sr", vol=(3, 6, 10)),
    E("Тяга блока к груди широким хватом", "Хват шире плеч, тяга к верху груди, лопатки сводятся в конце движения.", stats=("strength",), patterns=["pull"], muscles=PULL_M, equip=["dumbbells"], diff=2, vtype="sr", vol=(3, 8, 12)),
    E("Жим гантелей сидя на наклонной скамье под углом", "Угол скамьи 30-45°, жим вверх без полного запирания локтя.", stats=("strength",), patterns=["push"], muscles=PUSH_M, equip=["dumbbells", "step_platform"], tw=True, bwr=0.4, diff=2, vtype="sr", vol=(3, 8, 12)),
    E("Тяга гантели одной рукой в упоре на скамью", "Упор коленом и рукой на скамью, тяга гантели к бедру, локоть идёт вдоль корпуса.", stats=("strength",), patterns=["pull"], muscles=PULL_M, equip=["dumbbells", "step_platform"], tw=True, bwr=0.3, uni=True, diff=2, vtype="sr", vol=(3, 8, 12)),
    E("Face pull", "Тяга к лицу с разведением локтей в стороны, акцент на заднюю дельту и ротаторы.", stats=("strength",), patterns=["pull"], muscles=SHOULDER_M, equip=["resistance_band"], diff=1, vtype="sr", vol=(3, 12, 15)),
    E("Wall slides", "Спина и руки прижаты к стене, скольжение руками вверх-вниз с сохранением контакта с поверхностью.", phase="warmup", stage="activation", stats=("agility",), patterns=["shoulder_mobility"], muscles=SHOULDER_M, diff=1, vtype="sr", vol=(2, 10, 10)),
    E("Изометрическое сжатие мяча между коленями", "Лёжа, колени согнуты, умеренное сжатие мяча коленями — реабилитация паха.", phase="cooldown", stats=("strength",), patterns=["hip_mobility"], muscles=ADDUCTOR_M, equip=["medicine_ball"], diff=1, vtype="dur", vol=20),
    E("Sliding adductor", "Одна нога на слайд-диске, скользящее приведение к опорной ноге и обратно — реабилитация паха.", phase="cooldown", stats=("strength",), patterns=["hip_mobility"], muscles=ADDUCTOR_M, uni=True, diff=2, vtype="sr", vol=(3, 10, 12)),
    E("Terminal knee extension с резиной", "Небольшой сгиб колена, разгибание в последних градусах амплитуды под контролем — реабилитация колена.", phase="cooldown", stats=("strength",), patterns=["squat"], muscles={"quads": 0.8, "core": 0.2}, equip=["resistance_band"], uni=True, diff=1, vtype="sr", vol=(3, 12, 15)),
    E("Степ-даун с контролем", "Медленный контролируемый спуск с возвышения на одной ноге, колено не заваливается внутрь — реабилитация колена.", phase="cooldown", stats=("strength",), patterns=["squat"], muscles=LUNGE_M, equip=["step_platform"], uni=True, diff=2, vtype="sr", vol=(3, 8, 10)),
    E("Настенный присед (wall sit)", "Спина к стене, бёдра параллельно полу, удержание позиции.", stats=("strength",), patterns=["squat"], muscles=SQUAT_M, diff=1, vtype="dur", vol=30),
    E("Гребной тренажёр интервалы", "Интервальная работа с акцентом на технику (ноги-спина-руки в тяге).", stats=("endurance",), patterns=["locomotion"], muscles=LOCOMOTION_M, equip=["dumbbells"], stimulus="endurance", diff=2, vtype="dur", vol=120),
    E("Ассальт-байк интервалы", "Короткие максимальные интервалы с полным восстановлением между подходами.", stats=("endurance",), patterns=["locomotion"], muscles=LOCOMOTION_M, stimulus="endurance", diff=2, vtype="dur", vol=60),
    E("Скакалка на выносливость интервалы", "Интервальная работа со скакалкой, короткие раунды с отдыхом.", stats=("endurance", "agility"), patterns=["coordination"], muscles=CALF_M, equip=["jump_rope"], stimulus="endurance", diff=2, vtype="dur", vol=60),
]

# =========================================================================
# PART C -- mobility/rolling, round 2
# =========================================================================
EXERCISES += [
    E("Мобилизация грудного отдела на валике", "Лёжа на валике поперёк грудного отдела, руки за головой, лёгкое разгибание спины назад через валик.", phase="warmup", stage="soft_tissue", stats=("agility",), patterns=["shoulder_mobility"], muscles=THORACIC_M, equip=["foam_roller"], diff=1, vtype="sr", vol=(2, 8, 8)),
    E("Ротация грудного отдела сидя", "Сидя, руки скрещены на груди, ротация верхней части тела в сторону с фиксацией таза.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["shoulder_mobility"], muscles=THORACIC_M, uni=True, diff=1, vtype="sr", vol=(2, 8, 8)),
    E("Мобилизация ТБС 90/90 переходы", "Сидя в позиции 90/90, переход между сторонами через центр без помощи рук.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["hip_mobility"], muscles=GLUTE_M, diff=1, vtype="sr", vol=(2, 6, 6)),
    E("Растяжка икроножной у стены", "Упор руками в стену, задняя нога прямая, пятка на полу, наклон вперёд для растяжения икры.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["ankle_mobility"], muscles=ANKLE_M, diff=1, vtype="dur", vol=30),
    E("Растяжка камбаловидной у стены", "Как предыдущее, но заднее колено слегка согнуто — акцент смещается на камбаловидную мышцу.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["ankle_mobility"], muscles=ANKLE_M, diff=1, vtype="dur", vol=30),
    E("Мобилизация запястья", "Круговые движения кистью в обе стороны, для профилактики после силовой работы с гантелями/грифом.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["wrist_mobility"], muscles=WRIST_M, diff=1, vtype="dur", vol=20),
    E("Растяжка широчайшей в висе на 1 руке", "Вис на одной руке, тело слегка провисает в сторону противоположную руке для растяжения широчайшей.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["shoulder_mobility"], muscles=LAT_MOBILITY_M, equip=["pull_up_bar"], uni=True, diff=2, vtype="dur", vol=20),
    E("Нитка через иголку", "В упоре на четвереньках, одна рука проходит под корпусом с ротацией грудного отдела, другая тянется в потолок.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["shoulder_mobility"], muscles=THORACIC_M, diff=1, vtype="sr", vol=(2, 8, 8)),
    E("Растяжка сгибателей пальцев", "Разгибание пальцев и запястья с лёгким давлением второй рукой — для хвата после подтягиваний.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["wrist_mobility"], muscles=WRIST_M, diff=1, vtype="dur", vol=20),
    E("Мобилизация голеностопа с лентой", "Лента фиксирует голеностоп сзади, приседания в выпаде с усиленной тракцией сустава для увеличения амплитуды тыльного сгибания.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["ankle_mobility"], muscles=ANKLE_M, equip=["resistance_band"], diff=2, vtype="sr", vol=(2, 8, 8)),
    E("Растяжка передней поверхности бедра стоя", "Стоя на одной ноге, вторая нога сгибается назад, стопа к ягодице рукой.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["hip_mobility"], muscles=HIP_FLEXOR_M, uni=True, diff=1, vtype="dur", vol=30),
    E("Ротация шейного отдела активная", "Плавные повороты головы в стороны с полным контролем амплитуды, без рывков.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["shoulder_mobility"], muscles=NECK_M, diff=1, vtype="sr", vol=(2, 8, 8)),
    E("Растяжка задней поверхности бедра на возвышении", "Прямая нога на возвышении, наклон корпуса вперёд к стопе с прямой спиной.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["hip_mobility"], muscles={"hamstrings": 0.7, "back": 0.3}, equip=["step_platform"], uni=True, diff=1, vtype="dur", vol=30),
    E("Мобилизация грудного отдела с роликом под лопатками", "Валик под лопатками, руки за головой, плавные перекаты для мобилизации сегментов грудного отдела.", phase="warmup", stage="soft_tissue", stats=("agility",), patterns=["shoulder_mobility"], muscles=THORACIC_M, equip=["foam_roller"], diff=1, vtype="dur", vol=30),
    E("Растяжка приводящих в широкой стойке стоя", "Широкая стойка, перенос веса на одну сторону со сгибанием этого колена, вторая нога остаётся прямой.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["hip_mobility"], muscles=ADDUCTOR_M, uni=True, diff=1, vtype="dur", vol=30),
]

# =========================================================================
# PART D -- activation/stability, round 2
# =========================================================================
EXERCISES += [
    E("Ягодичный мостик с резиной над коленями", "Лёжа на спине, резина над коленями, мост с одновременным разведением коленей в стороны против сопротивления резины.", phase="warmup", stage="activation", stats=("agility",), patterns=["hip_hinge"], muscles=GLUTE_M, equip=["resistance_band"], diff=1, vtype="sr", vol=(2, 12, 15)),
    E("Клэмшелл", "Лёжа на боку, колени согнуты, стопы вместе, подъём верхнего колена вверх без разворота таза назад.", phase="warmup", stage="activation", stats=("agility",), patterns=["hip_mobility"], muscles=GLUTE_M, uni=True, diff=1, vtype="sr", vol=(2, 12, 15)),
    E("Мёртвый жук с резиной в руках", "Резина натянута между руками, попеременное разгибание противоположных руки и ноги с сохранением прижатой к полу поясницы.", phase="warmup", stage="activation", stats=("agility",), patterns=["core"], muscles=CORE_M, equip=["resistance_band"], diff=1, vtype="sr", vol=(2, 8, 8)),
    E("Планка с попеременным подъёмом руки и ноги", "Упор лёжа, одновременный подъём противоположной руки и ноги с удержанием стабильного таза.", phase="warmup", stage="activation", stats=("agility",), patterns=["core"], muscles=CORE_M, diff=2, vtype="sr", vol=(2, 8, 8)),
    E("Боковая планка с подъёмом верхней ноги", "Боковая планка, дополнительный подъём-опускание верхней ноги без потери прямой линии тела.", phase="warmup", stage="activation", stats=("agility",), patterns=["core"], muscles={"core": 0.5, "glutes": 0.5}, uni=True, diff=2, vtype="dur", vol=20),
    E("Ходьба на ягодицах", "Сидя на полу, ноги прямые, передвижение вперёд/назад только за счёт сокращения ягодичных мышц, без помощи рук.", phase="warmup", stage="activation", stats=("agility",), patterns=["core"], muscles=GLUTE_M, diff=1, vtype="dur", vol=30),
    E("Прогулка с гантелью над головой", "Гантель зафиксирована прямой рукой над головой, ходьба с сохранением вертикального положения корпуса.", phase="warmup", stage="activation", stats=("agility", "strength"), patterns=["core"], muscles={"shoulders": 0.4, "core": 0.4, "forearms": 0.2}, equip=["dumbbells"], tw=True, bwr=0.2, uni=True, diff=2, vtype="sr", vol=(2, 15, 15)),
    E("Изометрическая стабилизация лопатки в упоре на 1 руке", "Упор лёжа на одной руке (планка), удержание стабильного положения лопатки без провисания.", phase="warmup", stage="activation", stats=("agility",), patterns=["core"], muscles=CORE_M, uni=True, diff=3, vtype="dur", vol=20),
    E("Активация ягодичной лёжа на животе", "Лёжа на животе, подъём прямой ноги вверх за счёт сокращения ягодицы, без прогиба поясницы.", phase="warmup", stage="activation", stats=("agility",), patterns=["hip_hinge"], muscles=GLUTE_M, uni=True, diff=1, vtype="sr", vol=(2, 12, 15)),
    E("Полумостик с удержанием на 1 ноге", "Мостик на одной ноге, вторая нога вытянута вперёд, удержание позиции.", phase="warmup", stage="activation", stats=("agility",), patterns=["hip_hinge"], muscles=GLUTE_M, uni=True, diff=2, vtype="dur", vol=20),
    E("Активация передней зубчатой мышцы", "Упор лёжа, без сгибания локтей — только протракция/ретракция лопаток.", phase="warmup", stage="activation", stats=("agility",), patterns=["shoulder_mobility"], muscles=SHOULDER_M, diff=1, vtype="sr", vol=(2, 10, 10)),
]

# =========================================================================
# PART E -- dynamic warmup, round 2
# =========================================================================
_dyn_e = [
    ("Выпад в сторону с ротацией корпуса", "Боковой выпад с одновременным поворотом корпуса в сторону согнутой ноги."),
    ("Обратный выпад с подъёмом колена", "Шаг назад в выпад, возврат вперёд с одновременным подъёмом колена той же ноги вверх."),
    ("Инчворм", "Наклон вперёд, руки идут по полу вперёд до упора лёжа, затем ноги подтягиваются к рукам."),
    ("Раскрытие грудного отдела в шаге", "Шаг вперёд в лёгкий выпад с одновременной ротацией корпуса и раскрытием руки в сторону."),
    ("Высокий шаг с захватом колена", "Шаг вперёд, подтягивание колена к груди руками, следующий шаг на другую ногу."),
    ("Динамический выпад с касанием пола", "Шагающий выпад с касанием пола рукой у передней стопы в нижней точке."),
    ("Скип с высоким подъёмом бедра и захлёстом", "Чередование высокого подъёма бедра и захлёста голени в скиповом темпе."),
    ("Боковой шаг с прыжком", "Прыжок вбок с одной ноги на другую с полной остановкой и контролем приземления."),
    ("Приставные шаги с изменением направления", "Приставной шаг в одну сторону, резкая смена направления по сигналу/счёту."),
    ("Марш на месте с высоким коленом и паузой", "Подъём колена до уровня бедра с короткой изометрической паузой перед сменой ноги."),
]
EXERCISES += [
    E(name, desc, phase="warmup", stage="dynamic", stats=("agility",), patterns=["locomotion"], muscles=LOCOMOTION_M, vtype="dur", vol=30)
    for name, desc in _dyn_e
]

# =========================================================================
# PART F -- lower body strength, round 2
# =========================================================================
EXERCISES += [
    E("Присед в тренажёре Смита", "Фиксированная траектория штанги, позволяет безопасно работать с большим весом при контроле глубины.", stats=("strength",), patterns=["squat"], muscles=SQUAT_M, equip=["barbell"], tw=True, bwr=0.6, diff=2, vtype="sr", vol=(3, 8, 12)),
    E("Жим ногами в тренажёре", "Ноги на платформе на ширине плеч, сгибание коленей до ~90°, разгибание без полного запирания сустава.", stats=("strength",), patterns=["squat"], muscles=SQUAT_M, diff=2, vtype="sr", vol=(3, 10, 12)),
    E("Гакк-присед в тренажёре", "Спина фиксирована на подушке тренажёра, акцент на квадрицепс при сниженной нагрузке на поясницу.", stats=("strength",), patterns=["squat"], muscles=SQUAT_M, diff=2, vtype="sr", vol=(3, 8, 12)),
    E("Становая тяга на прямых ногах", "Минимальный сгиб колена, акцент на растяжении задней поверхности бедра через движение от таза.", stats=("strength",), patterns=["hip_hinge"], muscles=HINGE_M, equip=["barbell"], tw=True, bwr=0.5, diff=3, vtype="sr", vol=(3, 8, 10)),
    E("Тяга сумо с гирей", "Широкая стойка, гиря между ног, подъём через разгибание бёдер и колен одновременно.", stats=("strength",), patterns=["hip_hinge"], muscles=HINGE_M, equip=["kettlebell"], tw=True, bwr=0.5, diff=2, vtype="sr", vol=(3, 10, 12)),
    E("Присед с паузой в нижней точке", "Обычный присед с остановкой на 2-3 секунды в нижней точке перед подъёмом — убирает реактивный отскок.", stats=("strength",), patterns=["squat"], muscles=SQUAT_M, equip=["barbell"], tw=True, bwr=0.5, diff=3, vtype="sr", vol=(3, 6, 8)),
    E("Присед на 1 ноге с опорой", "Пистолетик с лёгкой опорой руками на подвесную петлю для баланса — переходная ступень к полному пистолетику.", stats=("strength", "agility"), patterns=["squat"], muscles=LUNGE_M, uni=True, diff=3, vtype="sr", vol=(3, 6, 8)),
    E("Латеральный выпад с гантелями", "Широкий шаг в сторону, сгибание одного колена, вторая нога остаётся прямой, вес переносится в сторону согнутой ноги.", stats=("strength",), patterns=["squat"], muscles=LUNGE_M, equip=["dumbbells"], tw=True, bwr=0.3, uni=True, diff=2, vtype="sr", vol=(3, 8, 10)),
    E("Кёрцевой выпад", "Шаг по диагонали назад-накрест, акцент на среднюю ягодичную мышцу и стабилизацию таза.", stats=("strength",), patterns=["squat"], muscles=LUNGE_M, uni=True, diff=2, vtype="sr", vol=(3, 8, 10)),
    E("Ягодичный мостик со штангой", "Верхняя часть спины на скамье, штанга на бёдрах, подъём таза до полного разгибания через сокращение ягодиц.", stats=("strength",), patterns=["hip_hinge"], muscles=GLUTE_M, equip=["barbell", "step_platform"], tw=True, bwr=0.6, diff=2, vtype="sr", vol=(3, 8, 12)),
    E("Подъём на носки стоя", "Подъём на переднюю часть стопы с полной амплитудой, пауза в верхней точке.", stats=("strength",), patterns=["ankle_mobility"], muscles=CALF_M, equip=["dumbbells"], tw=True, bwr=0.3, diff=1, vtype="sr", vol=(3, 12, 15)),
    E("Подъём на носки сидя", "Тот же подъём, но в положении сидя — смещает акцент на камбаловидную мышцу.", stats=("strength",), patterns=["ankle_mobility"], muscles=CALF_M, equip=["dumbbells"], diff=1, vtype="sr", vol=(3, 12, 15)),
    E("Ходьба выпадами с гантелями", "Непрерывное чередование выпадов вперёд с продвижением по прямой.", stats=("strength",), patterns=["squat"], muscles=LUNGE_M, equip=["dumbbells"], tw=True, bwr=0.3, diff=2, vtype="sr", vol=(3, 12, 12)),
    E("Присед с лентой над коленями", "Обычный присед с постоянным сопротивлением резины, не позволяющей коленям заваливаться внутрь.", stats=("strength",), patterns=["squat"], muscles=SQUAT_M, equip=["resistance_band"], diff=1, vtype="sr", vol=(3, 10, 12)),
]

# =========================================================================
# PART G -- upper body strength, round 2 (post-revision keepers only)
# =========================================================================
EXERCISES += [
    E("Жим штанги лёжа классический", "Хват чуть шире плеч, штанга опускается к нижней части груди, локти под ~45° к корпусу, подъём до полного разгибания.", stats=("strength",), patterns=["push"], muscles=PUSH_M, equip=["barbell"], tw=True, bwr=0.7, diff=3, vtype="sr", vol=(3, 6, 10)),
    E("Жим штанги на наклонной скамье", "Угол 30-45°, акцент смещается на верхнюю часть груди и передние дельты.", stats=("strength",), patterns=["push"], muscles=PUSH_M, equip=["barbell"], tw=True, bwr=0.6, diff=3, vtype="sr", vol=(3, 6, 10)),
    E("Жим узким хватом", "Хват на ширине плеч или чуть уже, локти идут вдоль корпуса, акцент на трицепс.", stats=("strength",), patterns=["push"], muscles=PUSH_M, equip=["barbell"], tw=True, bwr=0.5, diff=2, vtype="sr", vol=(3, 8, 12)),
    E("Жим штанги стоя", "Штанга от уровня ключиц, жим вертикально вверх без прогиба в пояснице, корпус напряжён.", stats=("strength",), patterns=["push"], muscles=PUSH_M, equip=["barbell"], tw=True, bwr=0.4, diff=3, vtype="sr", vol=(3, 6, 10)),
    E("Жим Арнольда", "Начало с гантелями у плеч ладонями к себе, жим вверх с одновременным разворотом ладоней наружу.", stats=("strength",), patterns=["push"], muscles=PUSH_M, equip=["dumbbells"], tw=True, bwr=0.3, diff=2, vtype="sr", vol=(3, 8, 12)),
    E("Тяга верхнего блока широким хватом", "Хват шире плеч, тяга к верху груди, лопатки сводятся в конце.", stats=("strength",), patterns=["pull"], muscles=PULL_M, equip=["dumbbells"], diff=2, vtype="sr", vol=(3, 8, 12)),
    E("Тяга верхнего блока обратным хватом", "Узкий обратный хват, тяга к груди с акцентом на нижнюю часть широчайших.", stats=("strength",), patterns=["pull"], muscles=PULL_M, diff=2, vtype="sr", vol=(3, 8, 12)),
    E("Тяга нижнего блока сидя", "Сидя, тяга рукояти к животу с сохранением нейтральной спины, лопатки сводятся в конце.", stats=("strength",), patterns=["pull"], muscles=PULL_M, diff=2, vtype="sr", vol=(3, 8, 12)),
    E("Разведение гантелей лёжа", "Дуговое разведение гантелей на скамье с лёгким сгибом локтей, растяжка и сведение груди.", stats=("strength",), patterns=["push"], muscles=PUSH_M, equip=["dumbbells"], tw=True, bwr=0.2, diff=2, vtype="sr", vol=(3, 10, 12)),
    E("Отжимания на брусьях (грудь)", "Корпус наклонён вперёд, локти слегка в стороны, глубокое опускание с акцентом на нижнюю часть груди.", stats=("strength",), patterns=["push"], muscles=PUSH_M, diff=3, vtype="sr", vol=(3, 6, 10)),
    E("Отжимания на брусьях (трицепс)", "Корпус вертикальный, локти вдоль корпуса, короткая амплитуда с акцентом на трицепс.", stats=("strength",), patterns=["push"], muscles=PUSH_M, diff=3, vtype="sr", vol=(3, 6, 10)),
    E("Жим гантелей нейтральным хватом на наклонной", "Ладони друг к другу, снижает нагрузку на плечо по сравнению с классическим жимом.", stats=("strength",), patterns=["push"], muscles=PUSH_M, equip=["dumbbells"], tw=True, bwr=0.4, diff=2, vtype="sr", vol=(3, 8, 12)),
    E("Тяга гантели в упоре на наклонной скамье", "Грудь опирается на наклонную скамью, тяга гантелей к корпусу без нагрузки на поясницу.", stats=("strength",), patterns=["pull"], muscles=PULL_M, equip=["dumbbells"], tw=True, bwr=0.3, diff=2, vtype="sr", vol=(3, 8, 12)),
    E("Отжимания с широкой постановкой рук", "Руки заметно шире плеч, акцент на грудные мышцы.", stats=("strength",), patterns=["push"], muscles=PUSH_M, diff=1, vtype="sr", vol=(3, 10, 15)),
    E("Отжимания алмазные", "Руки под грудью, ладони и большие пальцы соприкасаются, акцент на трицепс.", stats=("strength",), patterns=["push"], muscles=PUSH_M, diff=2, vtype="sr", vol=(3, 8, 12)),
]

# =========================================================================
# PART H -- power/speed, round 2
# =========================================================================
EXERCISES += [
    E("Т-дрилл", "Забег вперёд к центральному конусу, приставные шаги вправо/влево к боковым конусам, бег спиной назад на старт.", stats=("agility",), patterns=["locomotion"], muscles=FULLBODY_POWER_M, stimulus="power", diff=3, vtype="sr", vol=(3, 1, 1)),
    E("L-дрилл", "Забег по L-образной траектории с резкими поворотами на 180°, тест на скорость смены направления.", stats=("agility",), patterns=["locomotion"], muscles=FULLBODY_POWER_M, stimulus="power", diff=3, vtype="sr", vol=(3, 1, 1)),
    E("5-10-5 шаттл", "Спринт 5 метров в одну сторону, разворот, 10 метров в другую, разворот, 5 метров обратно на старт.", stats=("agility",), patterns=["locomotion"], muscles=FULLBODY_POWER_M, stimulus="power", diff=3, vtype="sr", vol=(3, 1, 1)),
    E("Спринт с сопротивлением партнёра", "Партнёр сзади создаёт сопротивление через резину, атлет выполняет стартовое ускорение.", stats=("agility", "on_ice_skating"), patterns=["locomotion"], muscles=FULLBODY_POWER_M, equip=["resistance_band"], stimulus="power", diff=3, vtype="sr", vol=(4, 1, 1)),
    E("Спринт с ускоряющим высвобождением", "Резина натягивается, отпускание создаёт ускоряющий импульс — тренировка максимальной скорости выше обычной.", stats=("agility", "on_ice_skating"), patterns=["locomotion"], muscles=FULLBODY_POWER_M, equip=["resistance_band"], stimulus="power", diff=4, vtype="sr", vol=(4, 1, 1)),
    E("Прыжок в глубину с последующим спринтом", "Спрыгивание с тумбы, реактивное отталкивание, немедленный переход в спринт на 5-10 метров.", stats=("agility", "on_ice_skating"), patterns=["squat"], muscles=FULLBODY_POWER_M, equip=["step_platform"], stimulus="power", diff=4, vtype="sr", vol=(3, 1, 1)),
    E("Хлопок в отжимании", "Взрывное отжимание с отрывом рук от пола и хлопком, приземление под контролем.", stats=("strength", "agility"), patterns=["push"], muscles=PUSH_M, stimulus="power", diff=3, vtype="sr", vol=(3, 5, 8)),
    E("Прыжок с поворотом на 180°", "Прыжок вверх с одновременным разворотом корпуса на 180°, приземление лицом в противоположную сторону.", stats=("agility",), patterns=["squat"], muscles=FULLBODY_POWER_M, stimulus="power", diff=3, vtype="sr", vol=(3, 6, 8)),
    E("Реактивные прыжки на месте", "Быстрые невысокие прыжки на прямых ногах за счёт голеностопа, минимальное время контакта с полом.", stats=("agility",), patterns=["ankle_mobility"], muscles=CALF_M, stimulus="power", diff=2, vtype="dur", vol=20),
    E("Бросок мяча через голову назад", "Мяч поднимается над головой и резко выбрасывается назад через голову за счёт разгибания всего тела.", stats=("strength", "agility"), patterns=["hip_hinge"], muscles=FULLBODY_POWER_M, equip=["medicine_ball"], stimulus="power", diff=2, vtype="sr", vol=(3, 6, 8)),
    E("Бросок мяча в стену на скорость", "Быстрый повторяющийся бросок мяча в стену на уровне груди с ловлей на отскоке.", stats=("agility", "strength"), patterns=["push"], muscles=PUSH_M, equip=["medicine_ball"], stimulus="power", diff=2, vtype="dur", vol=20),
    E("Ротационный бросок мяча с шагом", "Бросок мяча сбоку с одновременным шагом вперёд, добавляет включение ног в ротационное усилие.", stats=("agility", "strength"), patterns=["rotation"], muscles=CORE_ROT_M, equip=["medicine_ball"], stimulus="power", diff=3, vtype="sr", vol=(3, 6, 8)),
    E("Прыжок через барьеры сериями", "Серия из 4-6 барьеров подряд, минимальное время контакта с землёй между прыжками.", stats=("agility",), patterns=["squat"], muscles=LUNGE_M, stimulus="power", diff=3, vtype="sr", vol=(3, 5, 6)),
    E("Боковой прыжок через линию", "Быстрые прыжки на двух ногах из стороны в сторону через линию/палку на полу.", stats=("agility",), patterns=["squat"], muscles=FULLBODY_POWER_M, stimulus="power", diff=2, vtype="dur", vol=20),
    E("Прыжок с тумбы на тумбу", "Прыжок с одной возвышенности сразу на другую без остановки на полу между ними.", stats=("agility",), patterns=["squat"], muscles=FULLBODY_POWER_M, equip=["step_platform"], stimulus="power", diff=4, vtype="sr", vol=(3, 5, 5)),
    E("Спринт в гору", "Спринт вверх по наклону — усиленная нагрузка на отталкивание без излишней ударной нагрузки при торможении.", stats=("agility", "on_ice_skating"), patterns=["locomotion"], muscles=FULLBODY_POWER_M, stimulus="power", diff=3, vtype="sr", vol=(4, 1, 1)),
    E("Тяга саней спиной вперёд", "Движение спиной вперёд с сопротивлением саней, акцент на квадрицепс и контроль торможения.", stats=("strength", "agility"), patterns=["squat"], muscles=SQUAT_M, stimulus="power", diff=3, vtype="sr", vol=(4, 1, 1)),
    E("Свинг гири одной рукой", "Мах гири одной рукой от бёдер до уровня груди/головы за счёт взрывного разгибания таза.", stats=("strength", "agility"), patterns=["hip_hinge"], muscles=HINGE_M, equip=["kettlebell"], tw=True, bwr=0.2, uni=True, stimulus="power", diff=3, vtype="sr", vol=(3, 10, 12)),
    E("Рывок гири", "Взрывное движение гири от пола/маха до фиксации над головой одним слитным движением.", stats=("strength", "agility"), patterns=["hip_hinge"], muscles=HINGE_M, equip=["kettlebell"], tw=True, bwr=0.2, uni=True, stimulus="power", diff=4, vtype="sr", vol=(3, 6, 8)),
    E("Прыжок в полуприсед с фиксацией", "Прыжок из полуприседа вверх с обязательной мягкой фиксацией приземления без дополнительных подскоков.", stats=("agility",), patterns=["squat"], muscles=SQUAT_M, stimulus="power", diff=2, vtype="sr", vol=(3, 6, 8)),
    E("Спринт с низкого старта из положения лёжа", "Старт из положения лёжа на животе, быстрый подъём и ускорение — тренировка стартовой реакции.", stats=("agility", "on_ice_skating"), patterns=["locomotion"], muscles=FULLBODY_POWER_M, stimulus="power", diff=3, vtype="sr", vol=(4, 1, 1)),
    E("Метание набивного мяча ногами", "Лёжа на спине, мяч зажат между стопами, взрывное разгибание ног с выбросом мяча вверх/партнёру.", stats=("strength", "agility"), patterns=["hip_hinge"], muscles={"quads": 0.3, "glutes": 0.3, "core": 0.4}, equip=["medicine_ball"], stimulus="power", diff=2, vtype="sr", vol=(3, 8, 10)),
]

# =========================================================================
# PART I -- core/anti-rotation, round 2
# =========================================================================
EXERCISES += [
    E("Пресс Паллофа", "Стоя боком к точке крепления, вытягивание рукояти прямо перед грудью и обратно, сопротивляясь скручиванию корпуса.", stats=("strength",), patterns=["core"], muscles=CORE_ROT_M, equip=["resistance_band"], diff=2, vtype="sr", vol=(3, 10, 12)),
    E("Пресс Паллофа с удержанием", "Та же позиция, но руки полностью вытянуты вперёд и удерживаются статично максимально долго без разворота корпуса.", stats=("strength",), patterns=["core"], muscles=CORE_ROT_M, equip=["resistance_band"], diff=2, vtype="dur", vol=20),
    E("Чемоданная переноска", "Груз в одной руке сбоку, ходьба с сохранением строго вертикального корпуса, без наклона в сторону груза.", stats=("strength",), patterns=["core"], muscles={"core": 0.6, "forearms": 0.4}, equip=["dumbbells"], tw=True, bwr=0.3, uni=True, diff=2, vtype="sr", vol=(3, 20, 20)),
    E("Смещённая переноска", "Разный вес в каждой руке, усиленная антиротационная и антилатерально-флексионная нагрузка на кор.", stats=("strength",), patterns=["core"], muscles={"core": 0.6, "forearms": 0.4}, equip=["dumbbells"], tw=True, bwr=0.3, diff=3, vtype="sr", vol=(3, 20, 20)),
    E("Бёрдог с резиной на руке", "Классический бёрдог с дополнительным сопротивлением резины, зафиксированной на вытянутой руке.", stats=("strength",), patterns=["core"], muscles=CORE_M, equip=["resistance_band"], diff=2, vtype="sr", vol=(3, 8, 8)),
    E("Мешай в котле", "Упор предплечьями на фитбол в планке, круговые движения предплечьями, сохраняя стабильный таз.", stats=("strength",), patterns=["core"], muscles=CORE_M, diff=3, vtype="sr", vol=(3, 6, 6)),
    E("Подъём ног в висе", "Вис на турнике, подъём прямых/согнутых ног до параллели с полом или выше, без раскачивания корпуса.", stats=("strength",), patterns=["core"], muscles=CORE_M, equip=["pull_up_bar"], diff=3, vtype="sr", vol=(3, 8, 12)),
    E("Дворники лёжа", "Лёжа на спине, ноги подняты вертикально, попеременные наклоны ног в стороны с фиксацией лопаток на полу.", stats=("strength",), patterns=["rotation"], muscles=CORE_ROT_M, diff=3, vtype="sr", vol=(3, 8, 10)),
    E("Русский твист", "Сидя с приподнятыми ногами, повороты корпуса в стороны с касанием груза об пол по бокам.", stats=("strength",), patterns=["rotation"], muscles=CORE_ROT_M, equip=["medicine_ball"], diff=2, vtype="sr", vol=(3, 12, 16)),
    E("Колесо для пресса стоя", "Продвинутая версия роллаута — старт из положения стоя, а не с колен, требует значительно большего контроля кора.", stats=("strength",), patterns=["core"], muscles=CORE_M, diff=4, vtype="sr", vol=(3, 5, 8)),
    E("Боковая планка с ротацией", "Из боковой планки — проведение верхней руки под корпусом с ротацией, затем возврат в раскрытое положение.", stats=("strength",), patterns=["core"], muscles=CORE_ROT_M, uni=True, diff=3, vtype="sr", vol=(3, 8, 8)),
    E("Планка на фитболе с перекатом", "Упор предплечьями на фитбол, прокат мяча вперёд-назад с сохранением прямой линии тела.", stats=("strength",), patterns=["core"], muscles=CORE_M, diff=3, vtype="sr", vol=(3, 8, 10)),
    E("Скручивание на блоке стоя", "Стоя боком к блоку, тяга рукояти по диагонали сверху вниз одной рукой с ротацией корпуса.", stats=("strength",), patterns=["rotation"], muscles=CORE_ROT_M, uni=True, diff=2, vtype="sr", vol=(3, 10, 12)),
    E("Антиротационная тяга в выпаде", "Стойка в выпаде, тяга резины одной рукой к корпусу с сопротивлением развороту таза.", stats=("strength",), patterns=["core"], muscles=CORE_ROT_M, equip=["resistance_band"], uni=True, diff=2, vtype="sr", vol=(3, 10, 12)),
]

# =========================================================================
# PART J -- rehab by zone (cooldown)
# =========================================================================
EXERCISES += [
    E("Маятник Кодмана", "Наклон корпуса вперёд, рука свободно свисает, лёгкие раскачивающие движения по кругу и вперёд-назад для снятия острого напряжения плеча.", phase="cooldown", stats=("agility",), patterns=["shoulder_mobility"], muscles=SHOULDER_M, uni=True, diff=1, vtype="dur", vol=30),
    E("Изометрическое сгибание плеча в стену", "Кулак/предплечье упирается в стену на уровне плеча, статическое давление вперёд без движения в суставе.", phase="cooldown", stats=("strength",), patterns=["shoulder_mobility"], muscles=SHOULDER_M, uni=True, diff=1, vtype="dur", vol=20),
    E("Растяжка спящего", "Лёжа на боку, рука согнута под 90°, лёгкое давление второй рукой на предплечье для мягкой внутренней ротации плеча.", phase="cooldown", stats=("agility",), patterns=["shoulder_mobility"], muscles=SHOULDER_M, uni=True, diff=1, vtype="dur", vol=30),
    E("Тяга резины на разведение лопаток", "Руки вытянуты перед собой, разведение резины в стороны до сведения лопаток, без сгибания локтей.", phase="cooldown", stats=("strength",), patterns=["pull"], muscles=SHOULDER_M, equip=["resistance_band"], diff=1, vtype="sr", vol=(2, 12, 15)),
    E("Упражнение Брюггера", "Сидя на краю стула, разворот ладоней наружу с одновременным сведением лопаток и лёгким разгибанием грудного отдела.", phase="cooldown", stats=("agility",), patterns=["shoulder_mobility"], muscles=THORACIC_M, diff=1, vtype="sr", vol=(2, 10, 10)),
    E("Эксцентрическое приведение бедра на слайд-диске", "Медленное скольжение ноги в сторону от опорной с контролируемым возвратом за счёт приводящих мышц.", phase="cooldown", stats=("strength",), patterns=["hip_mobility"], muscles=ADDUCTOR_M, uni=True, diff=2, vtype="sr", vol=(3, 8, 10)),
    E("Раскачивание бедра лёжа", "В широкой стойке на коленях, раскачивание таза назад с растяжением приводящих без потери контакта коленей с полом.", phase="cooldown", stats=("agility",), patterns=["hip_mobility"], muscles=ADDUCTOR_M, diff=1, vtype="dur", vol=30),
    E("Изометрическое приведение бедра стоя", "Стоя, мяч зажат между ногой и стеной, статическое давление внутрь.", phase="cooldown", stats=("strength",), patterns=["hip_mobility"], muscles=ADDUCTOR_M, diff=1, vtype="dur", vol=20),
    E("Изометрическое напряжение квадрицепса", "Лёжа, валик под коленом, надавливание задней поверхностью колена на валик с напряжением квадрицепса, без движения в суставе.", phase="cooldown", stats=("strength",), patterns=["squat"], muscles={"quads": 1.0}, equip=["foam_roller"], diff=1, vtype="dur", vol=15),
    E("Подъём прямой ноги лёжа", "Лёжа на спине, одна нога согнута, вторая прямая поднимается до уровня согнутого колена, квадрицепс напряжён на всей амплитуде.", phase="cooldown", stats=("strength",), patterns=["squat"], muscles={"quads": 0.8, "core": 0.2}, uni=True, diff=1, vtype="sr", vol=(3, 12, 15)),
    E("Активация VMO со сжатием мяча", "Мяч между коленями, сжатие мяча с одновременным лёгким разгибанием колена — акцент на внутреннюю головку квадрицепса.", phase="cooldown", stats=("strength",), patterns=["squat"], muscles={"quads": 1.0}, equip=["medicine_ball"], diff=1, vtype="sr", vol=(3, 12, 15)),
    E("Контролируемый спуск со ступеньки", "Медленный спуск одной ногой со ступеньки с контролем колена, не допуская заваливания внутрь.", phase="cooldown", stats=("strength",), patterns=["squat"], muscles=LUNGE_M, equip=["step_platform"], uni=True, diff=2, vtype="sr", vol=(3, 8, 10)),
    E("Алфавит голеностопом", "Рисование стопой в воздухе букв алфавита для полной проработки амплитуды голеностопа во всех направлениях.", phase="cooldown", stats=("agility",), patterns=["ankle_mobility"], muscles=ANKLE_M, diff=1, vtype="sr", vol=(1, 1, 1)),
    E("Сопротивление во всех направлениях с резиной", "Резина фиксирована на стопе, сопротивление тыльному/подошвенному сгибанию, инверсии и эверсии по очереди.", phase="cooldown", stats=("strength",), patterns=["ankle_mobility"], muscles=ANKLE_M, equip=["resistance_band"], diff=1, vtype="sr", vol=(2, 12, 15)),
    E("Баланс на нестабильной поверхности", "Стойка на одной ноге на нестабильной поверхности, дополнительно можно закрыть глаза для усложнения.", phase="cooldown", stats=("agility",), patterns=["coordination"], muscles=ANKLE_M, uni=True, diff=2, vtype="dur", vol=30),
    E("Шея 4 направления изометрия", "Давление ладонью на голову в 4 направлениях (вперёд/назад/вбок с обеих сторон) без движения головы, статическое удержание.", phase="cooldown", stats=("strength",), patterns=["shoulder_mobility"], muscles=NECK_M, diff=1, vtype="dur", vol=15),
    E("Сгибание запястья с лёгкой гантелью", "Предплечье на опоре, сгибание кисти вверх с лёгким весом для укрепления сухожилий сгибателей.", phase="cooldown", stats=("strength",), patterns=["wrist_mobility"], muscles=WRIST_M, equip=["dumbbells"], diff=1, vtype="sr", vol=(2, 12, 15)),
    E("Разгибание запястья с лёгкой гантелью", "То же движение в обратную сторону, акцент на разгибатели предплечья.", phase="cooldown", stats=("strength",), patterns=["wrist_mobility"], muscles=WRIST_M, equip=["dumbbells"], diff=1, vtype="sr", vol=(2, 12, 15)),
]

# =========================================================================
# PART K -- conditioning, one row per modality (5-level progression from
# the source doc folded into the description; the app's own suggestion
# system personalizes growth per user instead of discrete levels)
# =========================================================================
EXERCISES += [
    E("Бег на выносливость", "Непрерывный бег в разговорном темпе. Прогрессия по дистанции: 6 км → 8 → 10 → 12 → 15 км по мере роста выносливости.", stats=("endurance",), patterns=["locomotion"], muscles=LOCOMOTION_M, stimulus="endurance", diff=2, vtype="dur", vol=1800),
    E("Темповый бег", "Бег на ~70% усилия, на грани разговорного темпа. Прогрессия по времени: 15 → 20 → 25 → 30 → 35 мин.", stats=("endurance",), patterns=["locomotion"], muscles=LOCOMOTION_M, stimulus="endurance", diff=3, vtype="dur", vol=900),
    E("Велосипед интервалы", "Интервалы работа/отдых до восстановления пульса. Прогрессия: 6×1 мин → 7×1:30 → 8×2 → 8×2:30 → 10×3 мин.", stats=("endurance",), patterns=["locomotion"], muscles=LOCOMOTION_M, stimulus="endurance", diff=2, vtype="dur", vol=600),
    E("Гребной тренажёр на дистанцию", "Гребля на фиксированную дистанцию с акцентом на технику. Прогрессия: 1000 → 1500 → 2000 → 3000 → 5000 м.", stats=("endurance",), patterns=["pull"], muscles={"back": 0.4, "quads": 0.3, "core": 0.3}, stimulus="endurance", diff=2, vtype="dur", vol=300),
    E("Плавание на выносливость", "Непрерывное плавание любым стилем. Прогрессия по дистанции: 400 → 600 → 800 → 1000 → 1500 м.", stats=("endurance",), patterns=["pull"], muscles=LOCOMOTION_M, stimulus="endurance", diff=2, vtype="dur", vol=600),
    E("Скоростные подъёмы по лестнице", "Непрерывный подъём по лестнице в быстром темпе. Прогрессия: 5 → 8 → 12 → 16 → 20 этажей.", stats=("endurance",), patterns=["locomotion"], muscles=LOCOMOTION_M, stimulus="endurance", diff=3, vtype="dur", vol=300),
    E("Шаттл-раны на выносливость", "Отрезки по 20 м с нарастающим темпом (в духе beep-теста). Прогрессия: 10 → 15 → 20 → 25 → 30 отрезков.", stats=("endurance", "agility"), patterns=["locomotion"], muscles=LOCOMOTION_M, stimulus="endurance", diff=3, vtype="dur", vol=600),
    E("Боевые канаты", "Волны канатами заданное время с отдыхом между раундами. Прогрессия: 5×20 сек → 6×25 → 6×30 → 8×30 → 8×40 сек.", stats=("endurance", "strength"), patterns=["core"], muscles={"shoulders": 0.4, "core": 0.4, "forearms": 0.2}, stimulus="endurance", diff=2, vtype="dur", vol=300),
    E("Круговая работа с санями", "Толкание+тяга саней раундами на дистанцию с отдыхом. Прогрессия: 4×20 м/90 сек → ... → 8×30 м/45 сек.", stats=("endurance", "strength"), patterns=["squat"], muscles=FULLBODY_POWER_M, stimulus="endurance", diff=3, vtype="dur", vol=480),
    E("Скакалка на выносливость непрерывная", "Непрерывная низкоинтенсивная работа скакалкой. Прогрессия по времени: 5 → 8 → 12 → 16 → 20 мин.", stats=("endurance", "agility"), patterns=["coordination"], muscles=CALF_M, equip=["jump_rope"], stimulus="endurance", diff=2, vtype="dur", vol=300),
]

# =========================================================================
# PART L -- lower body strength, round 3 (post-revision keepers only)
# =========================================================================
EXERCISES += [
    E("Присед Зерхера", "Штанга удерживается в сгибах локтей перед корпусом, приседание с вертикальным торсом — сильная нагрузка на кор и заднюю цепь.", stats=("strength",), patterns=["squat"], muscles={"quads": 0.4, "glutes": 0.3, "core": 0.3}, equip=["barbell"], tw=True, bwr=0.4, diff=4, vtype="sr", vol=(3, 6, 8)),
    E("Присед со штангой над головой", "Штанга зафиксирована прямыми руками над головой на всей амплитуде приседа — высокие требования к мобильности плеч и стабильности кора.", stats=("strength",), patterns=["squat"], muscles={"quads": 0.4, "shoulders": 0.3, "core": 0.3}, equip=["barbell"], tw=True, bwr=0.3, diff=4, vtype="sr", vol=(3, 5, 8)),
    E("Румынская тяга на 1 ноге со штангой", "Как гантельная версия, но со штангой — выше требования к балансу и хвату.", stats=("strength",), patterns=["hip_hinge"], muscles=HINGE_M, equip=["barbell"], tw=True, bwr=0.4, uni=True, diff=4, vtype="sr", vol=(3, 6, 8)),
    E("Казачий присед", "Глубокий боковой присед с полным переносом веса на одну ногу, вторая — прямая с опорой на пятку.", stats=("strength", "agility"), patterns=["squat"], muscles=LUNGE_M, equip=["kettlebell"], tw=True, bwr=0.2, uni=True, diff=3, vtype="sr", vol=(3, 6, 8)),
    E("Нордическое сгибание голени", "Колени зафиксированы, медленное контролируемое опускание корпуса вперёд за счёт эксцентрической работы задней поверхности бедра.", stats=("strength",), patterns=["hip_hinge"], muscles={"hamstrings": 0.8, "glutes": 0.2}, diff=4, vtype="sr", vol=(3, 4, 6)),
    E("Гиперэкстензия на тренажёре", "Бёдра зафиксированы на подушке, разгибание корпуса из наклона вверх за счёт ягодиц и задней поверхности бедра.", stats=("strength",), patterns=["hip_hinge"], muscles=HINGE_M, diff=2, vtype="sr", vol=(3, 10, 12)),
    E("Обратная гиперэкстензия", "Корпус зафиксирован, разгибание прямых ног назад-вверх за счёт ягодичных мышц.", stats=("strength",), patterns=["hip_hinge"], muscles=GLUTE_M, diff=2, vtype="sr", vol=(3, 10, 12)),
    E("Протяжка на прямых ногах", "Трос между ног, наклон вперёд с отведением таза назад, разгибание через ягодицы, тяга троса вперёд-вверх.", stats=("strength",), patterns=["hip_hinge"], muscles=HINGE_M, diff=2, vtype="sr", vol=(3, 10, 12)),
    E("Присед с ходьбой через шаг", "Выпадный шаг вперёд с гантелями, поочерёдно через шаг на разные ноги, без остановки.", stats=("strength",), patterns=["squat"], muscles=LUNGE_M, equip=["dumbbells"], tw=True, bwr=0.3, diff=2, vtype="sr", vol=(3, 10, 10)),
    E("Жим ногами одной ногой в тренажёре", "Платформа прорабатывается одной ногой за подход — устраняет компенсацию сильной ногой.", stats=("strength",), patterns=["squat"], muscles=SQUAT_M, uni=True, diff=3, vtype="sr", vol=(3, 8, 10)),
    E("Приведение бедра в тренажёре", "Сидя, сведение бёдер против сопротивления тренажёра — здоровье паха напрямую значимо для хоккея.", stats=("strength",), patterns=["hip_mobility"], muscles=ADDUCTOR_M, diff=1, vtype="sr", vol=(3, 12, 15)),
    E("Отведение бедра в тренажёре", "Сидя, разведение бёдер против сопротивления тренажёра.", stats=("strength",), patterns=["hip_mobility"], muscles=GLUTE_M, diff=1, vtype="sr", vol=(3, 12, 15)),
    E("Подъём на носок одной ногой стоя", "Подъём на переднюю часть стопы одной ногой с гантелью — напрямую связано с отталкиванием при катании.", stats=("strength", "on_ice_skating"), patterns=["ankle_mobility"], muscles=CALF_M, equip=["dumbbells"], tw=True, bwr=0.2, uni=True, diff=2, vtype="sr", vol=(3, 12, 15)),
    E("Подъём голени с резиной", "Резина на передней части стопы, подъём стопы на себя против сопротивления — профилактика переднего отдела голени.", stats=("strength", "on_ice_skating"), patterns=["ankle_mobility"], muscles=ANKLE_M, equip=["resistance_band"], diff=1, vtype="sr", vol=(3, 15, 20)),
]

# =========================================================================
# PART M -- upper body strength, round 3 (post-revision keepers only)
# =========================================================================
EXERCISES += [
    E("Жим гантелей стоя одна рука поочерёдно", "Стоя, попеременный жим гантели вверх одной рукой — функциональная антиротационная нагрузка.", stats=("strength",), patterns=["push"], muscles=PUSH_M, equip=["dumbbells"], tw=True, bwr=0.2, uni=True, diff=2, vtype="sr", vol=(3, 8, 12)),
    E("Тяга Т-грифа", "Гриф в угле, наклон корпуса вперёд, тяга к нижней части груди с сохранением нейтральной спины.", stats=("strength",), patterns=["pull"], muscles=PULL_M, equip=["barbell"], tw=True, bwr=0.4, diff=3, vtype="sr", vol=(3, 8, 10)),
    E("Жим гантелей лёжа с паузой в нижней точке", "Пауза 2 сек в нижней точке жима лёжа убирает реактивный отскок, увеличивает время под нагрузкой.", stats=("strength",), patterns=["push"], muscles=PUSH_M, equip=["dumbbells"], tw=True, bwr=0.3, diff=3, vtype="sr", vol=(3, 6, 10)),
    E("Тяга гантели в наклоне двумя руками", "Наклон корпуса вперёд, синхронная тяга двух гантелей к корпусу, лопатки сводятся в конце.", stats=("strength",), patterns=["pull"], muscles=PULL_M, equip=["dumbbells"], tw=True, bwr=0.4, diff=2, vtype="sr", vol=(3, 8, 12)),
    E("Отжимания с возвышения под ноги", "Стопы на скамье/степе, классические отжимания под наклоном — усиленная нагрузка на верх груди и плечи.", stats=("strength",), patterns=["push"], muscles=PUSH_M, equip=["step_platform"], diff=2, vtype="sr", vol=(3, 8, 12)),
]

# =========================================================================
# PART N -- hockey off-ice simulation (round 1)
# =========================================================================
EXERCISES += [
    E("Хоккейная стойка — изометрическое удержание", "Низкая хоккейная стойка (согнутые колени, наклон корпуса, руки как на клюшке), статическое удержание позиции.", stats=("on_ice_skating",), patterns=["squat"], muscles=SQUAT_M, stimulus="skill", diff=2, vtype="dur", vol=30),
    E("Ходьба в хоккейной стойке с резиной на бёдрах", "Резина выше колен, ходьба приставными шагами в низкой хоккейной стойке.", stats=("on_ice_skating",), patterns=["hip_mobility"], muscles=GLUTE_M, equip=["resistance_band"], stimulus="skill", diff=2, vtype="dur", vol=30),
    E("Скейтер-прыжок", "Прыжок вбок с одной ноги на другую по широкой амплитуде, имитируя отталкивание при катании, с полным контролем приземления.", stats=("on_ice_skating", "agility"), patterns=["squat"], muscles=LUNGE_M, stimulus="power", diff=3, vtype="sr", vol=(3, 6, 8)),
    E("Слайд-борд боковое скольжение", "Скольжение из стороны в сторону на слайд-борде в низкой стойке, имитация конькобежного шага без ударной нагрузки на суставы.", stats=("on_ice_skating",), patterns=["locomotion"], muscles=LOCOMOTION_M, equip=["slide_board"], stimulus="skill", diff=2, vtype="dur", vol=30),
    E("Слайд-борд с сопротивлением резины", "То же скольжение с дополнительным сопротивлением резины, зафиксированной сзади.", stats=("on_ice_skating",), patterns=["locomotion"], muscles=LOCOMOTION_M, equip=["slide_board", "resistance_band"], stimulus="skill", diff=3, vtype="dur", vol=30),
    E("Стартовый разгон конькобежца", "Низкий боковой старт из хоккейной стойки с несколькими мощными боковыми отталкиваниями, переходящими в спринт.", stats=("on_ice_skating", "agility"), patterns=["locomotion"], muscles=FULLBODY_POWER_M, stimulus="power", diff=3, vtype="sr", vol=(4, 1, 1)),
    E("Резаная имитация торможения", "Бег с резкой остановкой в низкую стойку боком, контроль замедления через колени и бёдра, без «втыкания» в пол прямыми ногами.", stats=("on_ice_skating", "agility"), patterns=["squat"], muscles=LUNGE_M, stimulus="skill", diff=3, vtype="sr", vol=(3, 5, 5)),
    E("Имитация броска с резиной", "Резина зафиксирована сзади на уровне рук, имитация броскового движения с сопротивлением через разгибание корпуса и перенос веса.", stats=("puck_handling", "strength"), patterns=["rotation"], muscles=CORE_ROT_M, equip=["resistance_band"], stimulus="power", uni=True, diff=2, vtype="sr", vol=(3, 8, 10)),
    E("Реакционная работа с клюшкой и мячом", "Ведение мяча клюшкой с быстрой сменой направления по звуковому/визуальному сигналу партнёра — координация рук и реакция.", stats=("puck_handling",), patterns=["stick_handling"], muscles=FOREARM_M, equip=["hockey_stick"], stimulus="skill", phase="puck", diff=2, vtype="dur", vol=30),
    E("Приём и передача у стены", "Многократная передача мяча в стену и приём на клюшку в движении, для отработки мягких рук.", stats=("puck_handling",), patterns=["stick_handling"], muscles=FOREARM_M, equip=["hockey_stick"], stimulus="skill", phase="puck", diff=1, vtype="dur", vol=60),
    E("Удержание одноногого баланса в хоккейной стойке", "Стойка на одной ноге в согнутом положении, имитирующем фазу опоры при катании.", stats=("on_ice_skating",), patterns=["coordination"], muscles=ANKLE_M, uni=True, stimulus="skill", diff=2, vtype="dur", vol=20),
    E("Реактивная агильность на визуальный сигнал", "Движение в разных направлениях по конусам, направление задаётся сигналом партнёра в реальном времени — тренировка принятия решений под нагрузкой.", stats=("agility",), patterns=["coordination"], muscles=FULLBODY_POWER_M, stimulus="skill", diff=3, vtype="dur", vol=30),
]

# =========================================================================
# PART O -- mobility/activation, round 3
# =========================================================================
EXERCISES += [
    E("Растяжка кушетка", "Заднее колено согнуто, голень вертикально у стены, глубокая растяжка сгибателя бедра и квадрицепса одновременно.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["hip_mobility"], muscles=HIP_FLEXOR_M, uni=True, diff=2, vtype="dur", vol=30),
    E("Скорпион", "Лёжа на животе, нога заводится по диагонали к противоположной руке с ротацией таза.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["hip_mobility"], muscles=GLUTE_M, uni=True, diff=1, vtype="sr", vol=(2, 6, 6)),
    E("Кошка-корова", "На четвереньках, чередование прогиба и округления спины синхронно с дыханием.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["shoulder_mobility"], muscles=THORACIC_M, diff=1, vtype="sr", vol=(2, 10, 10)),
    E("Величайшая растяжка мира", "Глубокий выпад вперёд с опорой руки на пол, ротация корпуса с поднятием второй руки вверх, комбинированная мобилизация бедра и грудного отдела.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["hip_mobility"], muscles=HIP_FLEXOR_M, uni=True, diff=2, vtype="sr", vol=(2, 6, 6)),
    E("Растяжка задней поверхности бедра с ремнём", "Лёжа на спине, ремень на стопе, подъём прямой ноги с мягким притягиванием к себе.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["hip_mobility"], muscles={"hamstrings": 0.8, "core": 0.2}, uni=True, diff=1, vtype="dur", vol=30),
    E("Растяжка грушевидной мышцы", "Лёжа на спине, лодыжка одной ноги на колене другой, притягивание бедра к груди.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["hip_mobility"], muscles=GLUTE_M, uni=True, diff=1, vtype="dur", vol=30),
    E("Контролируемые вращения ТБС", "Стоя у опоры, максимально полная контролируемая круговая амплитуда бедром во всех направлениях.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["hip_mobility"], muscles=GLUTE_M, uni=True, diff=2, vtype="sr", vol=(2, 5, 5)),
    E("Контролируемые вращения плеча", "Медленное максимально полное круговое движение прямой рукой с сохранением стабильного корпуса.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["shoulder_mobility"], muscles=SHOULDER_M, uni=True, diff=2, vtype="sr", vol=(2, 5, 5)),
    E("Мобилизация голеностопа колено к стене", "Стопа на расстоянии от стены, наклон колена к стене без отрыва пятки — тест и мобилизация тыльного сгибания.", phase="warmup", stage="joint_mobility", stats=("agility",), patterns=["ankle_mobility"], muscles=ANKLE_M, uni=True, diff=1, vtype="sr", vol=(2, 10, 10)),
]

# =========================================================================
# PART P -- power/speed, round 3
# =========================================================================
EXERCISES += [
    E("Лестница ловкости ёлочка", "Быстрая работа ступнями с внутренним/внешним заходом в каждую ячейку координационной лестницы.", stats=("agility",), patterns=["coordination"], muscles=LOCOMOTION_M, stimulus="skill", diff=2, vtype="dur", vol=20),
    E("Лестница ловкости приставные шаги", "Боковое прохождение лестницы приставным шагом, по одной/две ячейки за раз.", stats=("agility",), patterns=["coordination"], muscles=LOCOMOTION_M, stimulus="skill", diff=2, vtype="dur", vol=20),
    E("Прыжок в длину на 1 ноге", "Прыжок с одной ноги максимально далеко вперёд с приземлением на ту же ногу под контролем.", stats=("agility",), patterns=["squat"], muscles=LUNGE_M, stimulus="power", uni=True, diff=3, vtype="sr", vol=(3, 4, 6)),
    E("Боковой прыжок на дальность на 1 ноге", "То же самое в боковом направлении — тест и тренировка латеральной силы и стабильности.", stats=("agility",), patterns=["squat"], muscles=LUNGE_M, stimulus="power", uni=True, diff=3, vtype="sr", vol=(3, 4, 6)),
    E("Реактивный прыжок с ловлей мяча", "Партнёр бросает мяч в момент приземления после прыжка, атлет должен поймать — тренировка реактивности под когнитивной нагрузкой.", stats=("agility",), patterns=["coordination"], muscles=FULLBODY_POWER_M, equip=["medicine_ball"], stimulus="skill", diff=3, vtype="sr", vol=(3, 6, 8)),
    E("Выпрыгивание с резиной", "Резина фиксирована на поясе и под ногами/тумбой, вертикальный прыжок с дополнительным сопротивлением.", stats=("agility", "strength"), patterns=["squat"], muscles=SQUAT_M, equip=["resistance_band"], stimulus="power", diff=3, vtype="sr", vol=(3, 6, 8)),
]

# =========================================================================
# PART Q -- hockey off-ice simulation, round 2 (technique phases)
# =========================================================================
EXERCISES += [
    E("Кистевой бросок механика с резиной", "Резина фиксирована на уровне кисти нижней руки, имитация переката кисти при кистевом броске с сопротивлением на финальной фазе.", stats=("puck_handling",), patterns=["rotation"], muscles=FOREARM_M, equip=["resistance_band", "hockey_stick"], stimulus="skill", phase="puck", uni=True, diff=2, vtype="sr", vol=(3, 10, 12)),
    E("Замах слэпшота с сопротивлением", "Резина на верхней руке, полный замах с акцентом на ротацию корпуса и загрузку через заднюю ногу.", stats=("puck_handling", "strength"), patterns=["rotation"], muscles=CORE_ROT_M, equip=["resistance_band", "hockey_stick"], stimulus="power", phase="puck", uni=True, diff=3, vtype="sr", vol=(3, 8, 10)),
    E("Бросок в касание — реакция на пас", "Партнёр подаёт пас, атлет выполняет бросок сходу без остановки шайбы — тренировка тайминга переноса веса.", stats=("puck_handling",), patterns=["stick_handling"], muscles=FOREARM_M, equip=["hockey_stick"], stimulus="skill", phase="puck", diff=3, vtype="sr", vol=(3, 8, 8)),
    E("Ротационная мощность броска изолированно", "Ротационное движение корпуса, имитирующее фазу разгибания при броске, без клюшки — чистая наработка мощности вращения.", stats=("puck_handling", "strength"), patterns=["rotation"], muscles=CORE_ROT_M, equip=["medicine_ball"], stimulus="power", uni=True, diff=2, vtype="sr", vol=(3, 8, 10)),
    E("Кроссовер на месте", "Имитация перекрёстного шага конькобежца стоя на месте — заведение одной ноги за другую с сохранением низкой стойки.", stats=("on_ice_skating",), patterns=["locomotion"], muscles=LOCOMOTION_M, stimulus="skill", uni=True, diff=2, vtype="sr", vol=(3, 6, 8)),
    E("Пивот-разворот", "Резкий разворот с передней стойки на заднюю (имитация смены хода вперёд-назад), сохраняя низкий центр тяжести.", stats=("on_ice_skating",), patterns=["locomotion"], muscles=LOCOMOTION_M, stimulus="skill", uni=True, diff=2, vtype="sr", vol=(3, 6, 8)),
    E("C-cut имитация", "Имитация толчка при катании спиной вперёд — дугообразное отталкивающее движение ногой из-под корпуса.", stats=("on_ice_skating",), patterns=["hip_hinge"], muscles=HINGE_M, stimulus="skill", uni=True, diff=2, vtype="sr", vol=(3, 6, 8)),
    E("Контроль края конька латеральный баланс", "Стойка на одной ноге на нестабильной поверхности с наклоном корпуса в сторону, имитируя нагрузку на кант конька в повороте.", stats=("on_ice_skating",), patterns=["coordination"], muscles=ANKLE_M, uni=True, stimulus="skill", diff=3, vtype="dur", vol=20),
    E("Быстрая работа стоп на месте", "Максимально частая смена опорной ноги на месте в низкой стойке — тренировка частоты шагов при разгоне.", stats=("on_ice_skating", "agility"), patterns=["coordination"], muscles=LOCOMOTION_M, stimulus="skill", diff=2, vtype="dur", vol=15),
    E("Челнок с изменением высоты стойки", "Боковое перемещение с чередованием низкой и средней стойки по сигналу — имитация смены темпа катания в игровой ситуации.", stats=("on_ice_skating", "agility"), patterns=["locomotion"], muscles=LOCOMOTION_M, stimulus="skill", diff=3, vtype="dur", vol=30),
    E("Удержание позиции корпусом", "Стойка боком с отставленным локтем и корпусом между условным соперником и «шайбой», удержание позиции под лёгким давлением партнёра.", stats=("strength",), patterns=["core"], muscles=CORE_M, stimulus="strength", diff=2, vtype="dur", vol=20),
    E("Отработка силового приёма у борта", "Контролируемое столкновение плечом/корпусом с мягкой опорой, отработка стойки при контакте.", stats=("strength",), patterns=["push"], muscles=PUSH_M, stimulus="strength", diff=3, vtype="sr", vol=(3, 5, 5)),
    E("Приземление после силового контакта", "Контролируемое падение/приземление на бок с группировкой — профилактика травм при потере равновесия в контактной ситуации.", stats=("agility",), patterns=["coordination"], muscles=CORE_M, stimulus="skill", diff=3, vtype="sr", vol=(3, 5, 5)),
    E("Реакция на визуальный сигнал с клюшкой", "Ведение мяча клюшкой с резкой сменой направления по цветовому/числовому сигналу — совмещение моторики и принятия решений.", stats=("puck_handling", "agility"), patterns=["stick_handling"], muscles=FOREARM_M, equip=["hockey_stick"], stimulus="skill", phase="puck", diff=3, vtype="dur", vol=30),
    E("Периферийное зрение + ведение", "Ведение мяча клюшкой при одновременном отслеживании и назывании объектов/сигналов сбоку — тренировка игрового зрения.", stats=("puck_handling", "intellect"), patterns=["stick_handling"], muscles=FOREARM_M, equip=["hockey_stick"], stimulus="skill", phase="puck", diff=3, vtype="dur", vol=30),
]

# Part R is a revision note in the source doc (removes 25 bodybuilding-
# isolation exercises from earlier parts) -- nothing new to add, already
# reflected above by simply never including those exercises.

# =========================================================================
# PART S -- shift simulation (interval conditioning, 5-level folded into
# description same as Part K)
# =========================================================================
EXERCISES += [
    E("Имитация смены на велосипеде", "Максимальные интервалы с длинным неполным отдыхом, как игровая смена. Прогрессия: 10×40 сек/3 мин → ... → 18×45 сек/1:30.", stats=("endurance", "agility"), patterns=["locomotion"], muscles=LOCOMOTION_M, stimulus="power", diff=3, vtype="dur", vol=40),
    E("Имитация смены повторными спринтами", "Короткие максимальные спринты с неполным отдыхом. Прогрессия: 8×30 м/2 мин → ... → 15×40 м/1:15.", stats=("agility", "on_ice_skating"), patterns=["locomotion"], muscles=FULLBODY_POWER_M, stimulus="power", diff=3, vtype="sr", vol=(8, 1, 1)),
    E("Имитация смены на санях", "Максимальная работа с санями с длинным неполным отдыхом. Прогрессия: 6×30 сек/3 мин → ... → 12×40 сек/1:45.", stats=("strength", "agility"), patterns=["squat"], muscles=FULLBODY_POWER_M, stimulus="power", diff=3, vtype="dur", vol=30),
    E("Смешанная круговая имитация смены", "Сани+скейтер-прыжки+спринт в одном раунде — сочетает несколько типов усилия внутри одной «смены», как в реальной игре. Прогрессия: 3 раунда/3 мин → ... → 8 раундов/1:45.", stats=("endurance", "on_ice_skating"), patterns=["locomotion"], muscles=FULLBODY_POWER_M, stimulus="power", diff=4, vtype="dur", vol=60),
]

# =========================================================================
# PART T -- grip/forearm
# =========================================================================
EXERCISES += [
    E("Статическое удержание веса", "Груз в обеих руках сбоку, максимально долгое удержание с прямой осанкой, без движения — чистая сила хвата на время.", stats=("strength",), patterns=["core"], muscles=FOREARM_M, equip=["dumbbells"], tw=True, bwr=0.4, diff=2, vtype="dur", vol=30),
    E("Щипковый хват блинами", "Два блина гладкими сторонами наружу сжимаются пальцами (без обхвата ладонью), удержание на время.", stats=("strength",), patterns=["core"], muscles=FOREARM_M, diff=2, vtype="dur", vol=20),
    E("Вис на турнике на время", "Полный вис на прямых руках, удержание хвата максимально долго — база для любой хватовой выносливости.", stats=("strength",), patterns=["pull"], muscles=GRIP_HANG_M, equip=["pull_up_bar"], diff=1, vtype="dur", vol=30),
    E("Вис на турнике одной рукой", "Продвинутая версия — весь вес удерживается одной рукой.", stats=("strength",), patterns=["pull"], muscles=GRIP_HANG_M, equip=["pull_up_bar"], uni=True, diff=4, vtype="dur", vol=15),
    E("Подтягивание на полотенце", "Полотенца перекинуты через перекладину, хват за полотенца вместо грифа — резко увеличивает нагрузку на хват при обычном подтягивании.", stats=("strength",), patterns=["pull"], muscles=PULL_GRIP_M, equip=["pull_up_bar"], diff=3, vtype="sr", vol=(3, 4, 8)),
    E("Сгибание запястья с толстым грифом", "То же движение, что обычный wrist curl, но с толстым хватом — сильнее нагружает именно силу обхвата.", stats=("strength",), patterns=["wrist_mobility"], muscles=FOREARM_M, equip=["barbell"], tw=True, bwr=0.2, diff=2, vtype="sr", vol=(3, 12, 15)),
    E("Ролл кистевой на палке с верёвкой и грузом", "Груз на верёвке накручивается вращением кистей на палке — комплексная нагрузка сгибателей/разгибателей предплечья.", stats=("strength",), patterns=["wrist_mobility"], muscles=FOREARM_M, diff=2, vtype="sr", vol=(3, 1, 1)),
    E("Удержание клюшки на вытянутой руке", "Клюшка удерживается горизонтально на вытянутой руке хватом как при игре — специфическая изометрия именно под хват клюшки.", stats=("puck_handling", "strength"), patterns=["core"], muscles=FOREARM_M, equip=["hockey_stick"], uni=True, diff=2, vtype="dur", vol=20),
]

# =========================================================================
# PART V -- loaded explosive plyometrics + skater jump variations
# =========================================================================
EXERCISES += [
    E("Прыжок с трэп-грифом", "Лёгкий-средний вес в трэп-грифе, из полуприседа взрывной прыжок вверх с сохранением хвата, мягкое приземление в тот же полуприсед.", stats=("strength", "agility"), patterns=["squat"], muscles=SQUAT_M, equip=["barbell"], tw=True, bwr=0.3, stimulus="power", diff=4, vtype="sr", vol=(3, 5, 6)),
    E("Болгарские выпрыгивания", "Задняя нога на скамье, из нижней точки болгарского приседа — взрывной прыжок вверх передней ногой, мягкое приземление в ту же стойку.", stats=("strength", "agility"), patterns=["squat"], muscles=LUNGE_M, equip=["step_platform"], stimulus="power", uni=True, diff=4, vtype="sr", vol=(3, 5, 6)),
    E("Взрывной сплит-присед без смены ног", "Из нижней точки сплит-приседа — прыжок вверх с сохранением исходной расстановки ног в воздухе, приземление в ту же стойку.", stats=("agility",), patterns=["squat"], muscles=LUNGE_M, stimulus="power", uni=True, diff=3, vtype="sr", vol=(3, 6, 8)),
    E("Прыжок на бокс на 1 ноге", "Отталкивание одной ногой с места, запрыгивание на возвышение, приземление на ту же ногу с мягким контролем.", stats=("agility",), patterns=["squat"], muscles=LUNGE_M, equip=["step_platform"], stimulus="power", uni=True, diff=4, vtype="sr", vol=(3, 4, 6)),
    E("Прыжок с колен на стопы", "Старт на коленях на мате, взрывной мах руками и разгибание бёдер, прыжок в положение приземления на стопы в полуприсед.", stats=("strength", "agility"), patterns=["hip_hinge"], muscles=HINGE_M, stimulus="power", diff=3, vtype="sr", vol=(3, 5, 6)),
    E("Скейтер-прыжки непрерывной серией", "Без паузы между прыжками, немедленное реактивное отталкивание в противоположную сторону сразу после приземления.", stats=("on_ice_skating", "agility"), patterns=["squat"], muscles=LUNGE_M, stimulus="power", diff=3, vtype="dur", vol=20),
    E("Скейтер-прыжок через барьеры", "Серия боковых конькобежных прыжков через ряд невысоких препятствий, сохраняя низкую хоккейную стойку.", stats=("on_ice_skating", "agility"), patterns=["squat"], muscles=LUNGE_M, stimulus="power", diff=4, vtype="sr", vol=(3, 5, 6)),
    E("Скейтер-прыжок с резиной", "Резина фиксирована сбоку или партнёром, боковой скейтер-прыжок против сопротивления.", stats=("on_ice_skating", "agility"), patterns=["squat"], muscles=LUNGE_M, equip=["resistance_band"], stimulus="power", diff=3, vtype="sr", vol=(3, 6, 8)),
    E("Скейтер-прыжок на возвышение", "Боковой скейтер-прыжок с приземлением на невысокую тумбу вместо пола — совмещает латеральную мощность с вертикальным компонентом.", stats=("on_ice_skating", "agility"), patterns=["squat"], muscles=LUNGE_M, equip=["step_platform"], stimulus="power", diff=4, vtype="sr", vol=(3, 4, 6)),
    E("Реактивный скейтер-прыжок по сигналу", "Боковые скейтер-прыжки, направление которых задаётся сигналом партнёра в реальном времени — совмещение мощности и реакции.", stats=("on_ice_skating", "agility"), patterns=["coordination"], muscles=LUNGE_M, stimulus="power", diff=4, vtype="dur", vol=20),
    E("Прыжок-переход вперёд-назад", "Прыжок с разворотом из стойки лицом вперёд в стойку спиной вперёд и обратно — имитация смены хода при катании.", stats=("on_ice_skating", "agility"), patterns=["squat"], muscles=SQUAT_M, stimulus="power", diff=3, vtype="sr", vol=(3, 6, 8)),
    E("Прыжок кроссовер", "Прыжковая имитация перекрёстного шага — заведение одной ноги за другую в прыжке с приземлением в широкую стойку.", stats=("on_ice_skating", "agility"), patterns=["squat"], muscles=LUNGE_M, stimulus="power", uni=True, diff=3, vtype="sr", vol=(3, 6, 8)),
]

# =========================================================================
# PART U -- landing mechanics (progression, ACL-injury-prevention focus)
# =========================================================================
EXERCISES += [
    E("Приземление с места на 2 ноги", "Шаг с невысокой тумбы, приземление сразу на обе ноги с мягким сгибанием коленей и бёдер, колени над стопами, фиксация позы 2-3 сек.", stats=("agility",), patterns=["squat"], muscles=SQUAT_M, equip=["step_platform"], stimulus="skill", diff=1, vtype="sr", vol=(3, 5, 5)),
    E("Приземление с прыжка вверх на 2 ноги", "Небольшой прыжок вверх на месте, приземление с той же техникой контроля, что и ступень 1 — добавляется вертикальная скорость.", stats=("agility",), patterns=["squat"], muscles=SQUAT_M, stimulus="skill", diff=1, vtype="sr", vol=(3, 5, 5)),
    E("Приземление с тумбы на 1 ногу", "Тот же шаг с тумбы, но приземление только на одну ногу — резко повышает требования к стабильности таза и колена.", stats=("agility",), patterns=["squat"], muscles=LUNGE_M, equip=["step_platform"], stimulus="skill", uni=True, diff=2, vtype="sr", vol=(3, 5, 5)),
    E("Приземление после прыжка в длину на 2 ноги", "Прыжок вперёд (не вверх) с приземлением на обе ноги — добавляется горизонтальная скорость, которую нужно погасить.", stats=("agility",), patterns=["squat"], muscles=SQUAT_M, stimulus="skill", diff=2, vtype="sr", vol=(3, 5, 5)),
    E("Приземление после прыжка в длину на 1 ногу", "Комбинация горизонтальной скорости и одноногой стабилизации — существенно сложнее предыдущих ступеней по отдельности.", stats=("agility",), patterns=["squat"], muscles=LUNGE_M, stimulus="skill", uni=True, diff=3, vtype="sr", vol=(3, 4, 5)),
    E("Приземление с ротацией корпуса", "Прыжок с одновременным поворотом корпуса на 90° в воздухе, приземление с контролем — имитирует игровые ситуации смены направления в момент прыжка/контакта.", stats=("agility",), patterns=["squat"], muscles=SQUAT_M, equip=["step_platform"], stimulus="skill", diff=3, vtype="sr", vol=(3, 4, 5)),
    E("Реактивное приземление с немедленным повторным прыжком", "Техника приземления становится частью реактивного движения (та же механика, что депт-джамп, но с явным акцентом на качество приземления между двумя фазами).", stats=("agility",), patterns=["squat"], muscles=SQUAT_M, equip=["step_platform"], stimulus="power", diff=4, vtype="sr", vol=(3, 5, 5)),
    E("Приземление после контактного смещения", "Партнёр создаёт лёгкое непредсказуемое смещение в момент приземления (лёгкий толчок сбоку) — тренировка реактивной стабилизации колена в условиях, близких к игровому контакту.", stats=("agility",), patterns=["squat"], muscles=SQUAT_M, stimulus="skill", diff=4, vtype="sr", vol=(3, 4, 5)),
]

# warmup/cooldown entries above rely on E()'s "strength" default for
# stimulus_type (none of them explicitly override it to power/skill/
# endurance) -- but they're all light, short-rest work, not 2-3-minute
# strength-style rest. Normalize to "mobility" (15-30s rest, see
# app/core/rest.py) here instead of repeating stimulus="mobility" on
# every single call above.
for _entry in EXERCISES:
    if _entry["phase"] in ("warmup", "cooldown") and _entry["stimulus_type"] == "strength":
        _entry["stimulus_type"] = "mobility"

print(f"TOTAL: {len(EXERCISES)}")

names = [e["name"] for e in EXERCISES]
duplicates = {n for n in names if names.count(n) > 1}
if duplicates:
    print("DUPLICATE NAMES:", duplicates)
    sys.exit(1)


# =========================================================================
# Runner -- create + tag each exercise, skipping a name that already
# exists (idempotent against a partial re-run), printing progress as it
# goes ("iterate through the list and add them" -- 2026-08-31).
# =========================================================================
async def main() -> None:
    async with AsyncSessionLocal() as session:
        service = ExerciseService(session)
        existing = await session.execute(select(Exercise.name))
        existing_names = {row[0] for row in existing.all()}

        added = 0
        skipped = 0
        for index, entry in enumerate(EXERCISES, start=1):
            name = entry["name"]
            if name in existing_names:
                print(f"[{index}/{len(EXERCISES)}] SKIP (exists): {name}")
                skipped += 1
                continue

            create_payload = ExerciseCreate(
                name=name,
                description=entry["description"],
                category=entry["category"],
                phase=entry["phase"],
                difficulty_level=entry["difficulty_level"],
                target_sets=entry["target_sets"],
                rep_range_min=entry["rep_range_min"],
                rep_range_max=entry["rep_range_max"],
                target_duration_seconds=entry["target_duration_seconds"],
                tracks_weight=entry["tracks_weight"],
                bodyweight_ratio=entry["bodyweight_ratio"],
                suitable_for_game_day=entry["suitable_for_game_day"],
                is_unilateral=entry["is_unilateral"],
                stimulus_type=entry["stimulus_type"],
                exercise_type=entry["exercise_type"],
                warmup_stage=entry["warmup_stage"],
            )
            created = await service.create_exercise(create_payload)

            if entry["target_stats"]:
                await service.replace_target_stats(
                    created.id, [TargetStat(s) for s in entry["target_stats"]]
                )
            if entry["movement_patterns"]:
                await service.replace_movement_patterns(
                    created.id, [MovementPattern(p) for p in entry["movement_patterns"]]
                )
            if entry["muscle_groups"]:
                await service.replace_muscle_groups(
                    created.id,
                    [
                        MuscleGroupWeight(muscle_group=group, weight=weight)
                        for group, weight in entry["muscle_groups"].items()
                    ],
                )
            if entry["equipment_items"]:
                await service.replace_equipment_items(
                    created.id, [EquipmentItem(i) for i in entry["equipment_items"]]
                )

            print(f"[{index}/{len(EXERCISES)}] added: {name}")
            added += 1

        print(f"\nDone. Added {added}, skipped {skipped} (already existed).")


if __name__ == "__main__":
    asyncio.run(main())
