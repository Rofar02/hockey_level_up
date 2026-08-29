import uuid
from datetime import date as date_
from datetime import datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserQuestCompletion(Base):
    """One row per (user, quest, period) grant -- item 6's quest system
    (2026-08-30 gamification pass). `period_key` is what makes a grant
    idempotent and lets a recurring quest be earned again in a later
    period without a second table:

    - one_time quests: always `QuestService.ONE_TIME_PERIOD_KEY` ("once") --
      at most one row can ever exist per (user, quest).
    - weekly/long_term quests: the ISO Monday of the week the grant
      happened in (as a real date, not a string) -- a weekly quest can be
      re-earned every week, a long_term one (e.g. "4 consecutive weeks
      hitting the goal") whenever its rolling window becomes satisfied
      again, each a fresh row keyed by that week.

    See app.core.quests for the quest definitions themselves and
    QuestService for the satisfaction checks that decide when a row gets
    inserted.
    """

    __tablename__ = "user_quest_completions"
    __table_args__ = (
        UniqueConstraint("user_id", "quest_id", "period_key", name="uq_user_quest_completions_period"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quest_id: Mapped[str] = mapped_column(String(50), nullable=False)
    period_key: Mapped[date_] = mapped_column(Date, nullable=False)
    xp_awarded: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
