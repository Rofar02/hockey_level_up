import enum
import uuid
from datetime import date as date_
from datetime import datetime

from sqlalchemy import Date, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enum_column import enum_column


class TrainingPartyStatus(enum.StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    # No EXPIRED value here -- a pending party whose target_date has passed
    # is reported as "expired" only in TrainingPartyService's read-time
    # response, the same lazy-recompute idiom as ProgressService.get_streak.
    # No cron needed to sweep stale rows.


class TrainingParty(Base):
    """A co-op layer that gives every JOINED member the exact same set of
    exercises on target_date -- see TrainingPartyService.suggest_exercises /
    confirm_exercises. The exercise set itself is never stored on this row
    (or anywhere party-specific): confirm_exercises materializes it straight
    into each joined member's own DayPlan/TrainingSession/SessionBlock rows
    (see ScheduleService.replace_day_plan_content), so the creator's own
    materialized SessionBlocks *are* the canonical record of what the party
    trains -- read back via ScheduleRepository.get_day_plan_for_date when a
    friend joins after the fact (see _materialize_for_member).

    exercises_finalized_at is the only party-specific bit of state this adds:
    None means the creator hasn't confirmed a set yet (members keep whatever
    training -- or rest -- they already had); once set, every JOINED member
    has the shared session, and anyone who joins afterward is materialized
    into it immediately (see respond_to_invite).

    TrainingPartyService.try_complete_parties_for (called from
    SessionBlockService right after training_completed fires) flips this to
    COMPLETED once every training member is done.
    """

    __tablename__ = "training_parties"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_date: Mapped[date_] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[TrainingPartyStatus] = mapped_column(
        enum_column(TrainingPartyStatus, "training_party_status"),
        nullable=False,
        default=TrainingPartyStatus.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exercises_finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TrainingPartyMemberStatus(enum.StrEnum):
    INVITED = "invited"
    JOINED = "joined"
    DECLINED = "declined"


class TrainingPartyMember(Base):
    """One row per (party, user). The creator gets a row here too, status
    JOINED from the start -- same "captain is always a member" shape as
    TeamService.create_team, so member listing never special-cases the
    creator. No day_plan_id/training_session_id snapshot: a member's
    training status for target_date is always resolved live (see
    TrainingPartyService._resolve_member_training_status) against whatever
    DayPlan/TrainingSession actually exists for them on target_date --
    before confirm_exercises that's still their own personal plan (or rest),
    after it it's the materialized shared session, but the resolution code
    doesn't need to know which one it's looking at.
    """

    __tablename__ = "training_party_members"
    __table_args__ = (
        UniqueConstraint("party_id", "user_id", name="uq_training_party_members_party_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    party_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_parties.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[TrainingPartyMemberStatus] = mapped_column(
        enum_column(TrainingPartyMemberStatus, "training_party_member_status"),
        nullable=False,
        default=TrainingPartyMemberStatus.INVITED,
    )
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
