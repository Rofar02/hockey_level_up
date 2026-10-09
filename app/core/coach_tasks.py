"""Weekly tasks from the coach (2026-10-09, release plan step 7).

Two or three tasks a week, each of a fixed, checkable type -- the app
counts them itself, nobody is taken at their word. Premium players get
tasks the AI coach picks with the weekly review; everyone else gets them
from templates built off their week's plan.

Deliberately no "lift X kg / do Y reps" type: weight and reps belong to
double progression, and a task to go heavier would pull the player past
their plan for XP (owner's call, 2026-10-09) -- the same rule the quests
follow.
"""
import enum
from dataclasses import dataclass

from app.core.ice_focus import FOCUS_BY_ID


class CoachTaskType(enum.StrEnum):
    # Fully complete this many trainings (gym or ice) this week.
    COMPLETE_TRAININGS = "complete_trainings"
    # Send this many reports after ice or games this week.
    ICE_REPORTS = "ice_reports"
    # No missed training day this week.
    NO_MISSED_DAY = "no_missed_day"
    # This many training days in a row, all completed.
    DAYS_IN_A_ROW = "days_in_a_row"
    # Hold the ice focus (optionally a given one) and mark in the report
    # whether it worked, on this many ice days.
    ICE_FOCUS = "ice_focus"


# Same XP as a weekly quest.
COACH_TASK_XP = 100
MAX_TASKS_PER_WEEK = 3
COUNT_LIMITS: dict[CoachTaskType, tuple[int, int]] = {
    CoachTaskType.COMPLETE_TRAININGS: (1, 7),
    CoachTaskType.ICE_REPORTS: (1, 7),
    CoachTaskType.DAYS_IN_A_ROW: (2, 7),
    CoachTaskType.ICE_FOCUS: (1, 5),
}


@dataclass(frozen=True)
class CoachTaskSpec:
    type: CoachTaskType
    count: int = 1
    focus_id: str | None = None


def task_title(spec: CoachTaskSpec) -> str:
    if spec.type == CoachTaskType.COMPLETE_TRAININGS:
        return f"Закрой {spec.count} {_plural(spec.count, 'тренировку', 'тренировки', 'тренировок')} за неделю"
    if spec.type == CoachTaskType.ICE_REPORTS:
        return f"Отчитайся после льда или игры {spec.count} {_plural(spec.count, 'раз', 'раза', 'раз')}"
    if spec.type == CoachTaskType.NO_MISSED_DAY:
        return "Неделя без пропусков"
    if spec.type == CoachTaskType.DAYS_IN_A_ROW:
        return f"{spec.count} {_plural(spec.count, 'тренировочный день', 'тренировочных дня', 'тренировочных дней')} подряд без пропуска"
    focus = FOCUS_BY_ID.get(spec.focus_id or "")
    what = f"фокус «{focus.title}»" if focus is not None else "фокус дня"
    return f"Держи {what} на льду {spec.count} {_plural(spec.count, 'раз', 'раза', 'раз')} и отметь в отчёте, получилось ли"


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def parse_spec(raw: object) -> CoachTaskSpec | None:
    """A task from the AI's JSON -- None for anything unknown or out of
    range, which is then simply dropped (never shown)."""
    if not isinstance(raw, dict):
        return None
    try:
        task_type = CoachTaskType(str(raw.get("type")))
    except ValueError:
        return None
    count = raw.get("count", 1)
    if not isinstance(count, int) or isinstance(count, bool):
        return None
    limits = COUNT_LIMITS.get(task_type)
    if limits is not None and not limits[0] <= count <= limits[1]:
        return None
    focus_id = raw.get("focus_id")
    if task_type == CoachTaskType.ICE_FOCUS:
        if focus_id is not None and focus_id not in FOCUS_BY_ID:
            return None
    else:
        focus_id = None
    return CoachTaskSpec(task_type, count if limits is not None else 1, focus_id)


def template_specs(gym_days: int, ice_days: int) -> list[CoachTaskSpec]:
    """Free players' tasks, from the week's plan: close what's planned,
    report after the ice, and no missed day."""
    specs: list[CoachTaskSpec] = []
    planned = gym_days + ice_days
    if planned > 0:
        specs.append(CoachTaskSpec(CoachTaskType.COMPLETE_TRAININGS, min(planned, 7)))
    if ice_days > 0:
        specs.append(CoachTaskSpec(CoachTaskType.ICE_REPORTS, min(ice_days, 7)))
    if planned >= 2:
        specs.append(CoachTaskSpec(CoachTaskType.NO_MISSED_DAY))
    return specs[:MAX_TASKS_PER_WEEK]
