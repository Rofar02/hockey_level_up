from pydantic import BaseModel

from app.core.quests import QuestType


class QuestStatusRead(BaseModel):
    id: str
    type: QuestType
    title: str
    description: str
    xp_reward: int
    # True if the *current* period (the one QuestService just evaluated --
    # "once" for one_time, "this week" for weekly/long_term) is done.
    completed: bool
    # None for one_time quests -- always set for weekly/long_term, ISO date
    # of the Monday the current period is tracked under, so the frontend
    # can show "this week" honestly rather than a vague label.
    period_start: str | None = None
