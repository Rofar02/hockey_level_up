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
    """A co-op layer over each member's own, already-personalized training --
    deliberately does NOT generate shared session content (see the design
    discussion: periodization/equipment/skill gaps differ per member, so a
    literal shared workout would fight TrainingBlock's per-user progression).
    Members just train their own DayPlan for target_date and see each
    other's live progress; TrainingPartyService.try_complete_parties_for
    (called from SessionBlockService right after training_completed fires)
    flips this to COMPLETED once every training member is done.
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
    TrainingPartyService._resolve_member_training_status), so a rest-day
    swap via the existing PATCH /schedule/weekly/current is picked up
    automatically on the next read, nothing here needs updating.
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
