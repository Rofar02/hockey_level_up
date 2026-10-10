import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enum_column import enum_column


class GuestTeamStatus(enum.StrEnum):
    INVITED = "invited"
    ACCEPTED = "accepted"
    DECLINED = "declined"


class TeamEventGuestTeam(Base):
    """A joint training (2026-10-09, release plan step 3.5): another team
    the host captain invited to one TeamEvent. TeamEvent.team_id stays the
    host -- the plan, the lineup and the event itself are the host
    captain's; an ACCEPTED guest team's players see the event, mark
    attendance and can be put into its lineup. Players stay in their own
    team: the event is linked, not the people."""

    __tablename__ = "team_event_guest_teams"
    __table_args__ = (UniqueConstraint("team_event_id", "team_id", name="uq_team_event_guest_teams_event_team"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("team_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[GuestTeamStatus] = mapped_column(
        enum_column(GuestTeamStatus, "guest_team_status", length=16), nullable=False, default=GuestTeamStatus.INVITED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TeamIceTemplateGuestTeam(Base):
    """The same invitation on a recurring slot: every training stamped from
    the template is joint with the accepted guest team from the start."""

    __tablename__ = "team_ice_template_guest_teams"
    __table_args__ = (UniqueConstraint("template_id", "team_id", name="uq_team_ice_template_guest_teams_template_team"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("team_ice_schedule_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[GuestTeamStatus] = mapped_column(
        enum_column(GuestTeamStatus, "guest_team_status", length=16), nullable=False, default=GuestTeamStatus.INVITED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
