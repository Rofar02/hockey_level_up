import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enum_column import enum_column


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    invite_code: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    # Server-generated filename under settings.team_logo_upload_dir -- same
    # pattern as User.avatar_path (see TeamService.update_logo /
    # app/services/image_processing.py). Nullable: most teams start without
    # one, and only the captain is ever allowed to set it.
    logo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    @property
    def logo_url(self) -> str | None:
        if self.logo_path is None:
            return None
        return f"/static/team-logos/{self.logo_path}"


class TeamMembership(Base):
    """One row per (team, user) a player is actively part of -- a user can
    hold several of these at once (membership in multiple teams), which is
    exactly why this isn't a single team_id column on User. The team's
    captain also gets a row here (see TeamService.create_team), so member
    listing never has to special-case the owner.
    """

    __tablename__ = "team_memberships"
    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_memberships_team_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TeamJoinRequestStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class TeamJoinRequest(Base):
    """A player's request to join a team via its invite code, awaiting the
    captain's decision. "One pending request per (team, user)" is enforced
    in TeamService, not here -- a partial unique index (WHERE
    status='pending') isn't expressible via this codebase's plain
    UniqueConstraint idiom, so it's a deliberate app-layer check instead,
    same tradeoff as Exercise.muscle_group's nullability rules.
    """

    __tablename__ = "team_join_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[TeamJoinRequestStatus] = mapped_column(
        enum_column(TeamJoinRequestStatus, "team_join_request_status"),
        nullable=False,
        default=TeamJoinRequestStatus.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
