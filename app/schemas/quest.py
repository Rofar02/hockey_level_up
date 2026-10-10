import uuid

from pydantic import BaseModel

from app.core.quests import QuestType


class QuestStatusRead(BaseModel):
    id: str
    type: QuestType
    title: str
    description: str
    xp_reward: int
    # True once the *current* period's XP has actually been claimed (see
    # QuestService.claim) -- not just satisfied.
    completed: bool
    # True once the criteria are met but the player hasn't tapped
    # "Получить" yet -- mutually exclusive with `completed`.
    claimable: bool
    # None for one_time quests -- always set for weekly/long_term, ISO date
    # of the Monday the current period is tracked under, so the frontend
    # can show "this week" honestly rather than a vague label.
    period_start: str | None = None


class CoachTaskRead(BaseModel):
    """One of the week's tasks from the coach (2026-10-09, step 7) --
    progress counted from the player's own data."""

    id: uuid.UUID
    type: str
    title: str
    # "coach" (the AI picked it, premium) or "template".
    source: str
    progress: int
    target: int
    done: bool
    claimed: bool
    xp_reward: int
