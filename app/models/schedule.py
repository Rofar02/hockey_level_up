import enum
import uuid
from datetime import date as date_
from datetime import datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, UniqueConstraint
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

    day_plans: Mapped[list["DayPlan"]] = relationship(
        back_populates="weekly_plan", cascade="all, delete-orphan", order_by="DayPlan.date"
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
