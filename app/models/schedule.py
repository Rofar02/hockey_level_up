import enum
import uuid
from datetime import date as date_
from datetime import datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enum_column import enum_column
from app.models.exercise import Exercise, TrainingPhase


class DaySessionType(enum.StrEnum):
    ON_ICE = "on_ice"
    OFF_ICE = "off_ice"
    REST = "rest"


class WeeklyPlan(Base):
    __tablename__ = "weekly_plans"
    __table_args__ = (
        UniqueConstraint("user_id", "week_start_date", name="uq_weekly_plans_user_week"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    week_start_date: Mapped[date_] = mapped_column(Date, nullable=False)
    training_block_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("training_blocks.id", ondelete="SET NULL"), nullable=True
    )

    day_plans: Mapped[list["DayPlan"]] = relationship(
        back_populates="weekly_plan", cascade="all, delete-orphan", order_by="DayPlan.date"
    )


class TrainingBlock(Base):
    """Periodization state for a user, mutated in place week-to-week.

    `week_in_block` is bumped on the same row while it's < 4; hitting 4
    (a completed deload week) retires the row and a new one starts at
    block_number + 1 / week_in_block=1. "Active" block for a user is simply
    the row with the highest `block_number` -- no separate flag needed.
    """

    __tablename__ = "training_blocks"
    __table_args__ = (
        UniqueConstraint("user_id", "block_number", name="uq_training_blocks_user_block_number"),
        CheckConstraint(
            "week_in_block >= 1 AND week_in_block <= 4", name="ck_training_blocks_week_in_block_range"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    block_number: Mapped[int] = mapped_column(Integer, nullable=False)
    week_in_block: Mapped[int] = mapped_column(Integer, nullable=False)
    # Which real calendar week (WeeklyPlan.week_start_date) week_in_block
    # currently reflects. Lets _resolve_training_block tell "another
    # create_weekly_plan call for the same week" apart from "a real week
    # actually elapsed" -- advancing week_in_block is driven by calendar
    # weeks between anchor and the newly-declared week, not by call count.
    # Nullable for rows created before this column existed; see the
    # backfill in the migration that adds it, and the None-handling in
    # _resolve_training_block for rows backfill couldn't populate.
    anchor_week_start_date: Mapped[date_ | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DayPlan(Base):
    __tablename__ = "day_plans"
    __table_args__ = (
        UniqueConstraint("weekly_plan_id", "date", name="uq_day_plans_weekly_plan_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    weekly_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("weekly_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date: Mapped[date_] = mapped_column(Date, nullable=False)
    session_type: Mapped[DaySessionType] = mapped_column(
        enum_column(DaySessionType, "day_session_type"), nullable=False
    )
    # Set the moment a reminder push goes out for this day -- guards against
    # sending the same reminder twice across scheduler ticks (e.g. if a tick
    # runs slow and overlaps the next one).
    reminder_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    weekly_plan: Mapped["WeeklyPlan"] = relationship(back_populates="day_plans")
    training_session: Mapped["TrainingSession | None"] = relationship(
        back_populates="day_plan", cascade="all, delete-orphan", uselist=False
    )


class TrainingSession(Base):
    __tablename__ = "training_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    day_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("day_plans.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    day_plan: Mapped["DayPlan"] = relationship(back_populates="training_session")
    blocks: Mapped[list["SessionBlock"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="SessionBlock.order"
    )


class SessionBlock(Base):
    __tablename__ = "session_blocks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    phase: Mapped[TrainingPhase] = mapped_column(
        enum_column(TrainingPhase, "training_phase"), nullable=False
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exercises.id"), nullable=False
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped["TrainingSession"] = relationship(back_populates="blocks")
    exercise: Mapped["Exercise"] = relationship()
