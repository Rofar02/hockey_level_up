import enum
import uuid
from datetime import datetime
from datetime import time as time_

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
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


class TeamEventAttendanceStatus(enum.StrEnum):
    GOING = "going"
    NOT_GOING = "not_going"


class TeamEventAbsenceReason(enum.StrEnum):
    WORK = "work"
    INJURY = "injury"
    STUDY = "study"
    OTHER = "other"


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


class TeamEventDrillSection(Base):
    """A named block of the board ("Разминка", "Броски", ...) -- the coach
    creates these freely (the frontend only suggests preset names), then
    adds drills inside. Deleting a section deletes its drills.
    """

    __tablename__ = "team_event_drill_sections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    team_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("team_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Dense 0..N-1 within a team_event_id, same convention as
    # TeamEventDrill.order.
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TeamEventDrill(Base):
    """One card on the board, TRAINING events only -- GAME has no board at
    all (see TeamEvent.board_status). Deliberately no difficulty_level,
    unlike Exercise -- the v2 plan calls this out explicitly, the coach
    picks whatever content fits without the app grading it.

    Content edits (title/description) after the board is published happen
    silently, no push -- see TeamEventService.update_drill. Only starts_at
    changes and the publish/cancel actions themselves notify the team.
    """

    __tablename__ = "team_event_drills"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    team_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("team_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("team_event_drill_sections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Dense 0..N-1 within a section_id, kept contiguous by
    # TeamEventService.reorder_drills -- no UniqueConstraint on
    # (section_id, order) since a reorder briefly passes through
    # colliding values before the final flush settles them.
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional planned length -- sums into the section/board totals shown
    # to players.
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The drill's rink scheme (tokens + arrows, coordinates normalized to
    # 0..1) -- validated on write by schemas.team_event.DrillDiagram, a
    # couple of KB even for a busy drill. None = no scheme.
    diagram: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TeamEventAttendance(Base):
    """A player's own going/not_going call for one TeamEvent -- "unmarked"
    (the plan's third status) is the absence of a row here, not a stored
    value, so this table only ever holds the two states that actually need
    data attached (a reason for not_going). Applies identically to
    TRAINING and GAME, unlike the board.

    Deadline (starts_at - 2h, see TeamEventService.ATTENDANCE_DEADLINE) is
    computed on read, never stored -- TeamEventService rejects writes past
    it, GET stays open so the frozen status/board remain viewable.
    """

    __tablename__ = "team_event_attendances"
    __table_args__ = (
        UniqueConstraint(
            "team_event_id", "user_id", name="uq_team_event_attendances_event_user"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    team_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("team_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[TeamEventAttendanceStatus] = mapped_column(
        enum_column(TeamEventAttendanceStatus, "team_event_attendance_status"), nullable=False
    )
    # Only meaningful when status=NOT_GOING -- left nullable rather than a
    # CHECK constraint, same tradeoff as TeamEvent.board_status above.
    reason: Mapped[TeamEventAbsenceReason | None] = mapped_column(
        enum_column(TeamEventAbsenceReason, "team_event_absence_reason"), nullable=True
    )
    reason_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    responded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TeamEventLineupGroup(Base):
    """One group in the lineup -- a game's lines/pairs (by position) and a
    training's scrimmage teams (mixed) are the SAME shape, per the v2 plan:
    free-form (name + optional color + a player list), not a fixed
    "3 lines + 3 pairs" grid. `color` only makes sense for a TRAINING
    scrimmage (a game's whole team wears one jersey) -- TeamEventService
    rejects it for a GAME event's group, same nullability tradeoff as
    TeamEvent.board_status.
    """

    __tablename__ = "team_event_lineup_groups"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    team_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("team_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Display order among this event's groups -- same dense-from-0 idiom as
    # TeamEventDrill.order, kept contiguous by TeamEventService.delete_lineup_group.
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TeamEventLineupSlot(Base):
    """One player's placement into exactly one TeamEventLineupGroup for one
    event. team_event_id is denormalized from the group (same convention as
    TrainingDiaryEntry.user_id) -- it's what the unique constraint below
    needs to enforce "at most one group per player per event" without a
    join, and what get_lineup's per-user lookup filters on directly.
    """

    __tablename__ = "team_event_lineup_slots"
    __table_args__ = (
        UniqueConstraint(
            "team_event_id", "user_id", name="uq_team_event_lineup_slots_event_user"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    team_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("team_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("team_event_lineup_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )


class TeamEventDiaryEntry(Base):
    """A player's own note for a TRAINING TeamEvent -- the personal-schedule
    TrainingDiaryEntry's team-day counterpart, deliberately a separate
    table rather than reusing it: per the v2 plan, a team day generates no
    WeeklyPlan/DayPlan/TrainingSession at all (that stack stays untouched),
    so there's no training_session_id to hang an entry off of.

    Saving this entry -- with a note or an explicit skip (note=None), same
    "empty is still a save" convention as TrainingDiaryEntry -- is the
    reward trigger (see TeamEventService.save_diary_entry): the three
    on-ice stats + a fixed XP bonus, once, on first save, regardless of
    what the player's attendance said beforehand. A game gets no entry
    here (TeamEventService 400s) -- rewards are training-only per the plan
    (a game is too unpredictable to credit a specific skill).
    """

    __tablename__ = "team_event_diary_entries"
    __table_args__ = (
        UniqueConstraint(
            "team_event_id", "user_id", name="uq_team_event_diary_entries_event_user"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    team_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("team_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
