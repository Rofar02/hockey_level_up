"""Focus of the day for an ice day (2026-10-08): one thing to pay attention
to during a practice the app doesn't run (the team coach does) -- the app's
part on the ice is to prepare, give a focus and collect the report after.

Each focus works one on-ice stat. Which one is shown: what the player asked
to work on in their latest game report (last WORK_ON_LOOKBACK_DAYS), else
their lowest on-ice stat; within that stat the pick rotates by date, so a
week of ice days doesn't repeat the same cue. Draft content -- the owner
(a hockey player) reviews the wording.
"""
from dataclasses import dataclass

from app.models.exercise import TargetStat


@dataclass(frozen=True)
class IceFocus:
    id: str
    stat: TargetStat
    title: str
    cues: tuple[str, ...]
    # Set for the cues that fit "what to work on" from a game report better
    # than the rest of their stat (e.g. defensive positioning).
    work_on: str | None = None


ON_ICE_STATS = (TargetStat.ON_ICE_SKATING, TargetStat.PUCK_HANDLING, TargetStat.INTELLECT)

ICE_FOCUSES: tuple[IceFocus, ...] = (
    # -- skating --
    IceFocus("skate_transitions", TargetStat.ON_ICE_SKATING, "Переходы назад-вперёд на скорости",
             ("Разворачивайтесь через открытие бедра, не сбрасывая скорость",
              "Первый толчок после разворота — самый мощный")),
    IceFocus("skate_full_stride", TargetStat.ON_ICE_SKATING, "Полный толчок",
             ("Выпрямляйте толчковую ногу до конца",
              "Возвращайте конёк под себя коротким путём")),
    IceFocus("skate_low_stance", TargetStat.ON_ICE_SKATING, "Низкая стойка",
             ("Колени согнуты, как будто садитесь на стул",
              "Плечи над носками коньков, спина ровная")),
    IceFocus("skate_crossovers", TargetStat.ON_ICE_SKATING, "Перебежки в поворотах",
             ("Внешняя нога толкает под себя, внутренняя — в сторону",
              "Голова и плечи смотрят в поворот")),
    IceFocus("skate_first_steps", TargetStat.ON_ICE_SKATING, "Взрывной старт",
             ("Первые три шага короткие и частые, на носках",
              "Корпус наклонён вперёд, руки работают")),
    IceFocus("skate_stops", TargetStat.ON_ICE_SKATING, "Остановка и сразу старт",
             ("Тормозите на обе ноги, вес на внутренние рёбра",
              "Из остановки — сразу толчок, без паузы")),
    IceFocus("skate_backwards", TargetStat.ON_ICE_SKATING, "Катание спиной",
             ("Толчок полукругом, пятка уходит наружу",
              "Спина прямая, клюшка на льду")),
    IceFocus("skate_edges", TargetStat.ON_ICE_SKATING, "Работа рёбрами",
             ("В каждом повороте чувствуйте ребро конька",
              "Наклоняйте голень, а не только корпус")),
    IceFocus("skate_tempo", TargetStat.ON_ICE_SKATING, "Скорость до конца тренировки",
             ("Последнее упражнение — на той же скорости, что первое",
              "Устали — сократите паузу между толчками, а не их силу")),
    # -- puck --
    IceFocus("puck_head_up", TargetStat.PUCK_HANDLING, "Голова поднята при ведении",
             ("Шайбу чувствуйте крюком, а смотрите вперёд",
              "Проверяйте шайбу взглядом коротко и снова поднимайте голову")),
    IceFocus("puck_tape_pass", TargetStat.PUCK_HANDLING, "Пас точно в крюк",
             ("Отдавайте в крюк партнёра, а не в коньки",
              "Доводите клюшку в сторону цели после паса")),
    IceFocus("puck_soft_hands", TargetStat.PUCK_HANDLING, "Мягкий приём",
             ("Крюк чуть уступает шайбе, а не бьёт по ней",
              "Принимайте сбоку от себя, а не под коньки")),
    IceFocus("puck_shot_on_move", TargetStat.PUCK_HANDLING, "Бросок с хода",
             ("Переносите вес с задней ноги на переднюю",
              "Смотрите в цель, а не на шайбу"), work_on="shooting"),
    IceFocus("puck_wrist_shot", TargetStat.PUCK_HANDLING, "Кистевой бросок",
             ("Шайба катится от пятки к носку крюка",
              "Доводите клюшку в цель после броска"), work_on="shooting"),
    IceFocus("puck_wide_dekes", TargetStat.PUCK_HANDLING, "Обводка на скорости",
             ("Широкое ведение — руки далеко от корпуса",
              "Не замедляйтесь перед защитником")),
    IceFocus("puck_protect", TargetStat.PUCK_HANDLING, "Защита шайбы корпусом",
             ("Корпус между соперником и шайбой",
              "Держите шайбу на дальней от соперника стороне")),
    IceFocus("puck_backhand", TargetStat.PUCK_HANDLING, "Неудобная сторона",
             ("Хотя бы раз в каждом упражнении — пас или бросок с бэкхенда",
              "Крюк закрыт, кисти работают вместе")),
    IceFocus("puck_net_front", TargetStat.PUCK_HANDLING, "Добивание у ворот",
             ("У ворот клюшка всегда на льду",
              "Ищите отскок, а не смотрите на бросок")),
    # -- game reading --
    IceFocus("iq_shoulder_check", TargetStat.INTELLECT, "Взгляд через плечо",
             ("Перед приёмом шайбы посмотрите через плечо",
              "Знайте, кто рядом, ещё до паса"), work_on="positioning"),
    IceFocus("iq_get_open", TargetStat.INTELLECT, "Открывание под пас",
             ("Двигайтесь в свободную зону, а не к шайбе",
              "Покажите крюком, куда отдавать"), work_on="positioning"),
    IceFocus("iq_move_after_pass", TargetStat.INTELLECT, "Отдал — двигайся",
             ("После паса сразу уходите в новую точку",
              "Не стойте и не смотрите, как играют другие")),
    IceFocus("iq_defensive_side", TargetStat.INTELLECT, "Позиция в защите",
             ("Будьте между соперником и своими воротами",
              "Клюшка на льду, перекрывайте линию паса"), work_on="defense"),
    IceFocus("iq_gap", TargetStat.INTELLECT, "Дистанция до соперника",
             ("Держите дистанцию в длину клюшки",
              "Отъезжайте спиной с той же скоростью, что он едет"), work_on="defense"),
    IceFocus("iq_talk", TargetStat.INTELLECT, "Говорите на льду",
             ("Подсказывайте: «есть время», «сзади», «отдай»",
              "Зовите шайбу голосом и клюшкой")),
    IceFocus("iq_switch_side", TargetStat.INTELLECT, "Смена направления атаки",
             ("Закрыто — играйте назад или на другую сторону",
              "Не лезьте в троих, ищите свободного")),
    IceFocus("iq_zone_exit", TargetStat.INTELLECT, "Выход из зоны",
             ("Решайте заранее: борт или партнёр в центре",
              "Под давлением — простой пас вместо обводки"), work_on="defense"),
    IceFocus("iq_loose_puck", TargetStat.INTELLECT, "Первым к шайбе",
             ("Читайте отскок и выезжайте раньше соперника",
              "Подобрали — сразу защитите шайбу корпусом")),
)

FOCUS_BY_ID: dict[str, IceFocus] = {focus.id: focus for focus in ICE_FOCUSES}

# "Над чем поработать" (GameWorkOn values) -> the stat a focus then works.
WORK_ON_STATS: dict[str, TargetStat] = {
    "skating": TargetStat.ON_ICE_SKATING,
    "shooting": TargetStat.PUCK_HANDLING,
    "defense": TargetStat.INTELLECT,
    "positioning": TargetStat.INTELLECT,
}
WORK_ON_LOOKBACK_DAYS = 14

STAT_REASON_NAMES: dict[TargetStat, str] = {
    TargetStat.ON_ICE_SKATING: "скорость на льду",
    TargetStat.PUCK_HANDLING: "владение шайбой",
    TargetStat.INTELLECT: "интеллект",
}
WORK_ON_REASON_NAMES: dict[str, str] = {
    "skating": "катание",
    "shooting": "броски",
    "defense": "игру в защите",
    "positioning": "выбор позиции",
}


def pick_focus(
    day_ordinal: int,
    stat_values: dict[TargetStat, float],
    work_on: list[str] | None,
) -> tuple[IceFocus, str]:
    """The day's focus and the "почему это" line. `day_ordinal` is the day's
    date.toordinal(), `stat_values` the player's current on-ice stats
    (missing = 0), `work_on` the latest recent game report's picks."""
    if work_on:
        choice = sorted(work_on)[day_ordinal % len(work_on)]
        stat = WORK_ON_STATS[choice]
        matching = [f for f in ICE_FOCUSES if f.work_on == choice] or [f for f in ICE_FOCUSES if f.stat == stat]
        reason = f"После игры вы хотели поработать: {WORK_ON_REASON_NAMES[choice]}"
    else:
        stat = min(ON_ICE_STATS, key=lambda s: (stat_values.get(s, 0.0), ON_ICE_STATS.index(s)))
        matching = [f for f in ICE_FOCUSES if f.stat == stat]
        reason = f"{STAT_REASON_NAMES[stat].capitalize()} — ваш самый низкий стат на льду"
    return matching[day_ordinal % len(matching)], reason
