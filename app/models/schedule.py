import enum
import uuid
from datetime import date as date_
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enum_column import enum_column
from app.models.exercise import Exercise, TrainingPhase


class DaySessionType(enum.StrEnum):
    # Real ice time is always a coach-run team practice -- the app has no
    # content for the practice itself, only an on-ice warmup + cooldown
    # wrapped around it, no MAIN block -- see
    # ScheduleService._build_on_ice_day_session. Unlike GAME, ON_ICE still
    # counts as a real training day for TrainingStreak/periodization (see
    # streak_service.TRAINING_SESSION_TYPES /
    # training_block_repository._TRAINING_SESSION_TYPES): a shorter,
    # coach-content session is still a session, unlike GAME's optional
    # light activation.
    ON_ICE = "on_ice"
    OFF_ICE = "off_ice"
    REST = "rest"
    # Light pre-game activation + mental prep, not a full workout -- see
    # ScheduleService._build_game_day_session. Like REST, a missed GAME day
    # doesn't break TrainingStreak (see streak_service.TRAINING_SESSION_TYPES).
    GAME = "game"


class BlockPhase(enum.StrEnum):
    ACCUMULATION = "accumulation"
    INTENSIFICATION = "intensification"
    DELOAD = "deload"


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
    """Periodization state for a user, mutated in place as real training
    sessions complete (Phase 4) -- no longer calendar-driven.

    `phase` advances accumulation -> intensification -> deload on the same
    row once enough real (on/off-ice) sessions have completed since
    `phase_started_at`, or that calendar ceiling has been hit regardless of
    session count (see app.core.training_block.phase_transition_due).
    Completing deload retires the row and a new one starts at
    block_number + 1 / phase=ACCUMULATION. "Active" block for a user is
    simply the row with the highest `block_number` -- no separate flag
    needed. See TrainingBlockService.resolve_active_block for the
    query-and-mutate logic driven by this state.

    `is_macrocycle_deload` (Phase: П.2) is set once at creation, on top of
    the normal accumulation/intensification/deload phase cycle within the
    block -- every 4th block is a full-block recovery period where
    WeightSuggestionService/RepsSuggestionService suggest the floor of
    whatever range/history they'd otherwise use, regardless of accumulated
    progress. See app.core.training_block.is_macrocycle_deload_block.
    """

    __tablename__ = "training_blocks"
    __table_args__ = (
        UniqueConstraint("user_id", "block_number", name="uq_training_blocks_user_block_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    block_number: Mapped[int] = mapped_column(Integer, nullable=False)
    phase: Mapped[BlockPhase] = mapped_column(
        enum_column(BlockPhase, "block_phase"), nullable=False, default=BlockPhase.ACCUMULATION
    )
    # When the CURRENT phase started -- purely the anchor for the
    # calendar-ceiling fallback now (weeks_since_phase_started in
    # phase_transition_due). Reset to today() every time phase advances
    # (including the deload->new-block rollover, on the new row).
    phase_started_at: Mapped[date_] = mapped_column(Date, nullable=False, default=date_.today)
    # How many of this block's total completed real sessions had already
    # been consumed by an earlier phase transition, as of the moment the
    # CURRENT phase started -- the lower bound for "sessions completed in
    # this phase" is (total real sessions for this block) minus this,
    # NOT a phase_started_at date filter (found 2026-09-01 simulating
    # months of play: phase_started_at is a bare Date, so a second
    # same-day transition -- e.g. a catch-up burst of several real
    # sessions, or several SessionBlock.complete calls landing inside one
    # TrainingBlockService._catch_up loop -- re-stamped the same today()
    # value, and DayPlan.date >= that date matched the very sessions that
    # had just fired the PREVIOUS transition, so they got re-counted
    # toward the next one too, cascading a mesocycle through in far fewer
    # than SESSIONS_TO_ADVANCE_PHASE*3 real sessions). Reset to the
    # block's own total-so-far every time phase advances within the same
    # block (see TrainingBlockService._advance); 0 on a brand-new block.
    phase_session_baseline: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_macrocycle_deload: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
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
    # Indexed (not just part of the uq_day_plans_weekly_plan_date composite
    # above, which leads with weekly_plan_id): TeamRatingService's "trainings
    # in the last 7 days" aggregate filters by date alone, across many
    # users' weekly_plans, so it needs date to be the leading/only column.
    date: Mapped[date_] = mapped_column(Date, nullable=False, index=True)
    session_type: Mapped[DaySessionType] = mapped_column(
        enum_column(DaySessionType, "day_session_type"), nullable=False
    )
    # Set the moment a reminder push goes out for this day -- guards against
    # sending the same reminder twice across scheduler ticks (e.g. if a tick
    # runs slow and overlaps the next one).
    reminder_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Set while a TeamEvent the user marked "going" has taken this day over
    # (TRAINING -> ON_ICE, GAME -> GAME), see
    # ScheduleService.apply_team_event_to_day. replaced_session_type is what
    # the day was before, so "not going"/cancel/reschedule can put it back
    # (revert_team_event_days). Both None on an ordinary day.
    team_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("team_events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    replaced_session_type: Mapped[DaySessionType | None] = mapped_column(
        enum_column(DaySessionType, "day_session_type"), nullable=True
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
    __table_args__ = (
        # Partial index, same idiom as OutboxEvent.ix_outbox_events_unpublished:
        # speeds up the EXISTS(... completed_at IS NOT NULL ...) checks used by
        # has_missed_training_day and TeamRatingService's completed-trainings
        # aggregate, without indexing the (much larger) set of incomplete rows
        # neither of those ever queries for.
        Index(
            "ix_session_blocks_completed_at_not_null",
            "completed_at",
            postgresql_where=text("completed_at IS NOT NULL"),
        ),
        # Same idiom, for warmup/cooldown skips (media-player redesign,
        # 2026-08-28) -- see skipped_at's own comment below.
        Index(
            "ix_session_blocks_skipped_at_not_null",
            "skipped_at",
            postgresql_where=text("skipped_at IS NOT NULL"),
        ),
    )

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
    # Warmup/cooldown-only (media-player redesign, 2026-08-28): resolves the
    # block for session/phase/streak-completion purposes exactly like
    # completed_at does, but deliberately never fires block_completed --
    # skipping earns no stat/XP/muscle-load gain. See SessionBlockService
    # .skip_block for the phase-scope enforcement (server-side, not just
    # trusted from the frontend).
    skipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped["TrainingSession"] = relationship(back_populates="blocks")
    exercise: Mapped["Exercise"] = relationship()
