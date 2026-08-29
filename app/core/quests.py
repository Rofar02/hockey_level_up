"""Quest registry -- item 6 of the roadmap (2026-08-30 gamification pass).
Definitions only (id, type, copy, XP reward); the actual "is this satisfied
right now" checks live in QuestService, since they need DB access this
module deliberately doesn't have (same split as app.core.level_unlocks
being pure while the callers that gate on it live in the services layer).

XP amounts (50/100/300 for one_time/weekly/long_term) were an explicit
product call -- the roadmap item itself only said "rewards existing XP
only", no numbers. Picked to read as "roughly one exercise" / "roughly two
exercises" / "a real chunk" relative to xp_consumer's own difficulty*10
(10-50 XP per exercise) rather than competing with or dwarfing normal
training XP.

Deliberately excluded (per the roadmap item's own text): any quest based on
volume/intensity ("do more/heavier") -- that's core-engine territory, quests
must not compete with it.
"""
import enum
from dataclasses import dataclass


class QuestType(enum.StrEnum):
    ONE_TIME = "one_time"
    WEEKLY = "weekly"
    LONG_TERM = "long_term"


XP_REWARD_BY_TYPE: dict[QuestType, int] = {
    QuestType.ONE_TIME: 50,
    QuestType.WEEKLY: 100,
    QuestType.LONG_TERM: 300,
}


@dataclass(frozen=True)
class QuestDefinition:
    id: str
    type: QuestType
    title: str
    description: str

    @property
    def xp_reward(self) -> int:
        return XP_REWARD_BY_TYPE[self.type]


# reference_first_visit has no natural DB signal (visiting a page leaves no
# trace, unlike logging a diary entry or a restriction) -- QuestService
# grants it via a dedicated client-reported endpoint instead of an
# evaluated check, see QuestService.mark_reference_visited. Every other
# quest is evaluated purely by querying already-existing data -- no new
# event consumers, no other new client signals.
QUEST_DEFINITIONS: list[QuestDefinition] = [
    QuestDefinition(
        id="reference_first_visit",
        type=QuestType.ONE_TIME,
        title="Первое знакомство",
        description="Загляните в Справочник",
    ),
    QuestDefinition(
        id="diary_first_entry",
        type=QuestType.ONE_TIME,
        title="Первая запись",
        description="Оставьте первую запись в Дневнике",
    ),
    QuestDefinition(
        id="restriction_first_logged",
        type=QuestType.ONE_TIME,
        title="Честно о самочувствии",
        description="Отметьте первое ограничение — что болит",
    ),
    QuestDefinition(
        id="first_full_workout",
        type=QuestType.ONE_TIME,
        title="Первая тренировка",
        description="Полностью пройдите тренировку — все этапы",
    ),
    QuestDefinition(
        id="first_friend_added",
        type=QuestType.ONE_TIME,
        title="Не один на льду",
        description="Добавьте первого друга",
    ),
    QuestDefinition(
        id="weekly_three_workouts",
        type=QuestType.WEEKLY,
        title="Три за неделю",
        description="Полностью пройдите 3 тренировки за эту неделю",
    ),
    QuestDefinition(
        id="weekly_no_missed_day",
        type=QuestType.WEEKLY,
        title="Ни одного пропуска",
        description="Ни одного пропущенного тренировочного дня за эту неделю",
    ),
    QuestDefinition(
        id="weekly_restrictions_updated",
        type=QuestType.WEEKLY,
        title="На связи с телом",
        description="Обновите ограничения хотя бы раз за эту неделю",
    ),
    QuestDefinition(
        id="monthly_no_big_gap",
        type=QuestType.LONG_TERM,
        title="Без больших пауз",
        description="Месяц без перерывов между тренировками больше 3 дней",
    ),
    QuestDefinition(
        id="four_week_streak_goal",
        type=QuestType.LONG_TERM,
        title="Месяц в ритме",
        description="4 недели подряд с выполненной недельной целью (3 тренировки)",
    ),
]

QUEST_DEFINITIONS_BY_ID: dict[str, QuestDefinition] = {q.id: q for q in QUEST_DEFINITIONS}
