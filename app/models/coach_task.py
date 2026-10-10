import uuid
from datetime import date as date_
from datetime import datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WeeklyCoachTask(Base):
    """One of the week's tasks from the coach (2026-10-09, release plan step
    7) -- see app.core.coach_tasks for the types. `source` is "coach" (the
    AI picked it with the weekly review, premium) or "template" (built off
    the week's plan). Progress is counted on read; claimed_at is set when
    the player takes the XP."""

    __tablename__ = "weekly_coach_tasks"
    __table_args__ = (
        UniqueConstraint("user_id", "week_start", "task_type", name="uq_weekly_coach_tasks_user_week_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    week_start: Mapped[date_] = mapped_column(Date, nullable=False)
    task_type: Mapped[str] = mapped_column(String(32), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    focus_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
