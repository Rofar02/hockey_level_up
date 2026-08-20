import uuid
from datetime import date as date_
from datetime import datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enum_column import enum_column
from app.models.exercise import MuscleGroup, TargetStat


class UserStat(Base):
    __tablename__ = "user_stats"
    __table_args__ = (
        UniqueConstraint("user_id", "stat_type", name="uq_user_stats_user_stat_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stat_type: Mapped[TargetStat] = mapped_column(
        enum_column(TargetStat, "target_stat"), nullable=False
    )
    current_value: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class StatHistory(Base):
    __tablename__ = "stat_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stat_type: Mapped[TargetStat] = mapped_column(
        enum_column(TargetStat, "target_stat"), nullable=False
    )
    value: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(255), nullable=False)


class UserMuscleLoad(Base):
    """Body-muscles map (2026-08-20 planning session, dependent on Stage
    2.1's MuscleGroup taxonomy) -- same (user, category, running value,
    last-touched timestamp) shape as UserStat, but the *meaning* of the
    stored value and its decay direction are opposite: a stat's
    current_value is a permanent high-water mark that only ever grows
    (get_effective_value in app.services.stat_service projects a
    *temporary* dip from disuse without ever mutating the stored peak), 0-10
    fatigue/load from recent training that's expected to fully return to 0
    as the muscle recovers -- there's no "peak" worth preserving here.
    Because of that, muscle_load_consumer collapses the decayed effective
    value into current_value *before* adding a new session's load (see
    app.core.muscle_load's own module docstring for why this can't reuse
    stat_service's write-then-project-on-read pattern as-is)."""

    __tablename__ = "user_muscle_loads"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "muscle_group", name="uq_user_muscle_loads_user_muscle_group"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    muscle_group: Mapped[MuscleGroup] = mapped_column(
        enum_column(MuscleGroup, "muscle_group"), nullable=False
    )
    current_value: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TrainingStreak(Base):
    __tablename__ = "training_streaks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    current_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    longest_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_activity_date: Mapped[date_ | None] = mapped_column(Date, nullable=True)
