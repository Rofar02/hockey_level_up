import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enum_column import enum_column


class FriendRequestStatus(enum.StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"


class FriendRequest(Base):
    """A request to become friends, sent via the receiver's personal
    User.friend_code -- a symmetric (sender, receiver) pair decided by the
    receiver themselves. Deliberately separate from TeamJoinRequest, not a
    generalization of it: a team's captain decides join requests on behalf
    of the whole team, but a friend request has no third-party role like
    that to lean on -- only the receiver can accept/decline their own.

    "Are these two users friends" is answered by the existence of an
    ACCEPTED row in either direction (sender_id, receiver_id) or
    (receiver_id, sender_id) -- there's no separate Friendship table.
    UniqueConstraint(sender_id, receiver_id) means only one row can ever
    exist per *ordered* pair; FriendService re-sends after a DECLINED
    response by resetting that same row rather than inserting a second one.
    """

    __tablename__ = "friend_requests"
    __table_args__ = (
        UniqueConstraint("sender_id", "receiver_id", name="uq_friend_requests_sender_receiver"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    receiver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[FriendRequestStatus] = mapped_column(
        enum_column(FriendRequestStatus, "friend_request_status"),
        nullable=False,
        default=FriendRequestStatus.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
