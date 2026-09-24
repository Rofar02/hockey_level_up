import enum
import uuid
from datetime import datetime
from datetime import time as time_

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Time, func, true
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enum_column import enum_column


class TeamEventType(enum.StrEnum):
    TRAINING = "training"
    GAME = "game"


class TeamEventStatus(enum.StrEnum):
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"


class TeamEventPublishStatus(enum.StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class TeamIceScheduleTemplate(Base):
    """A recurring weekday+time slot a captain sets up for TRAINING events
    only -- games are always one-off (TeamService creates each TeamEvent
    directly, no template). A background job stamps future TeamEvent rows
    from active templates; deactivating a template (active=False) doesn't
    touch TeamEvent rows it already stamped, so moving/cancelling one
    training never affects the recurring slot itself.
    """

    __tablename__ = "team_ice_schedule_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Python's date.weekday(): 0=Monday .. 6=Sunday.
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time_] = mapped_column(Time, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TeamEvent(Base):
    """A single team practice or game -- see IceLevel v2 plan (2026-09-16)
    section 2 for why training and game share one table instead of two:
    attendance/lineup/notifications are identical shapes for both, only the
    board (training-only) and opponent_name (game-only) differ.

    board_status is meaningless for GAME events (games have no board) --
    left nullable rather than adding a CHECK constraint, same tradeoff as
    Exercise.muscle_group's nullability rules elsewhere in this codebase.
    """

    __tablename__ = "team_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[TeamEventType] = mapped_column(
        enum_column(TeamEventType, "team_event_type"), nullable=False
    )
    status: Mapped[TeamEventStatus] = mapped_column(
        enum_column(TeamEventStatus, "team_event_status"),
        nullable=False,
        default=TeamEventStatus.SCHEDULED,
    )
    # Exact start, not just a date -- attendance deadline (-2h) and the
    # morning "board not ready" nudge both need a real instant to compare
    # against, unlike DayPlan.date elsewhere in this codebase.
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    opponent_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("team_ice_schedule_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    board_status: Mapped[TeamEventPublishStatus | None] = mapped_column(
        enum_column(TeamEventPublishStatus, "team_event_publish_status"), nullable=True
    )
    lineup_status: Mapped[TeamEventPublishStatus] = mapped_column(
        enum_column(TeamEventPublishStatus, "team_event_publish_status"),
        nullable=False,
        default=TeamEventPublishStatus.DRAFT,
    )
    # Nudge-button rate limit (max once/hour) -- checked server-side, not
    # just a disabled button on the frontend.
    last_nudge_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Guards against the attendance-summary and "board not ready" pushes
    # firing twice if a scheduler tick overlaps the next one, same idiom as
    # DayPlan.reminder_sent_at.
    attendance_summary_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    board_not_ready_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
