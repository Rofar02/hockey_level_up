import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, SmallInteger, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enum_column import enum_column


class IceEffort(str, enum.Enum):
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"


class IceHighlight(str, enum.Enum):
    """"Что шло лучше всего" after an ice day."""

    SKATING = "skating"
    PASSING = "passing"
    SHOOTING = "shooting"
    GAME_READING = "game_reading"


class FocusResult(str, enum.Enum):
    """"Фокус получился?" for the focus of the day (app.core.ice_focus)."""

    DONE = "done"
    PARTIAL = "partial"
    MISSED = "missed"


class GameResult(str, enum.Enum):
    WIN = "win"
    DRAW = "draw"
    LOSS = "loss"


class GameWorkOn(str, enum.Enum):
    """"Над чем поработать" after a game."""

    SKATING = "skating"
    DEFENSE = "defense"
    SHOOTING = "shooting"
    POSITIONING = "positioning"


class TrainingDiaryEntry(Base):
    """A player's own notebook entry for a single ON_ICE or GAME
    TrainingSession -- the app has no structured content for either (see
    ScheduleService._build_on_ice_day_session / _build_game_day_session),
    so free text is the only way the player can record what actually
    happened. Deliberately not fed into OverloadService's brakes (see
    app.core.overload) -- that mechanism counts individual sets within a
    session, a different granularity than one day-level judgment; wiring
    it in needs its own dedicated design, not a bolted-on hack here.

    2026-10-08: plus a structured report (a few taps, see the report
    columns below) -- the owner found that after a practice nobody wants to
    write, so the taps are what earns the day's reward and the free-text
    note became optional. (A 2026-09 version had a single canned quick-tag;
    that one was dropped for free text.)

    One row per TrainingSession (unique constraint below), upserted in
    place on every save rather than accumulating a history -- see
    TrainingDiaryService.save_entry.
    """

    __tablename__ = "training_diary_entries"
    __table_args__ = (
        UniqueConstraint("training_session_id", name="uq_training_diary_entries_session"),
        CheckConstraint("self_rating BETWEEN 1 AND 5", name="ck_training_diary_entries_self_rating"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Denormalized, same convention as SetCompletion.user_id -- avoids a
    # join through TrainingSession->DayPlan->WeeklyPlan for the common
    # "this user's diary entries" access pattern.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    training_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 2026-10-08 report after an ice day or a game: a few taps instead of
    # free text (the note stays, optional). reported_at is set on the first
    # submitted report; all report fields are None on a note-only entry
    # (entries from before the report existed, or "Не буду писать").
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # "Не был": the day is closed honestly, without a reward.
    skipped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # Ice day.
    duration_minutes: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    effort: Mapped[IceEffort | None] = mapped_column(enum_column(IceEffort, "ice_effort", length=16), nullable=True)
    highlights: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    # The focus of the day the player saw (app.core.ice_focus id) and how
    # it went; a done/partial focus adds a little to its stat.
    focus_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    focus_result: Mapped[FocusResult | None] = mapped_column(
        enum_column(FocusResult, "focus_result", length=16), nullable=True
    )
    # Game. goals/assists/shots are left None for a goalie (their own form
    # comes later). The team coach always sees the counters for a team game;
    # self_rating and work_on only when share_rating_with_coach is on.
    game_result: Mapped[GameResult | None] = mapped_column(
        enum_column(GameResult, "game_result", length=16), nullable=True
    )
    goals: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    assists: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    shots: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    self_rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    work_on: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    share_rating_with_coach: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
