import enum
import uuid
from typing import Literal
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.friend import FriendRequestStatus
from app.models.user import Position


class FriendRead(BaseModel):
    """One row in the friends list -- same shape as team.TeamMemberRead
    minus is_captain (friendship has no roles)."""

    id: uuid.UUID
    first_name: str
    last_name: str
    avatar_url: str | None = None
    level: int
    jersey_number: int | None = None
    position: Position | None = None


class FriendCodePayload(BaseModel):
    """A request goes by the friend's code (typed in or from their invite
    link) or, from the search/team/suggestion lists, by their id -- one of
    the two."""

    code: str | None = Field(default=None, min_length=1)
    user_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _one_target(self) -> "FriendCodePayload":
        if (self.code is None) == (self.user_id is None):
            raise ValueError("Pass either code or user_id")
        return self


class FriendRelation(str, enum.Enum):
    NONE = "none"
    OUTGOING = "outgoing"  # I asked, they haven't answered
    INCOMING = "incoming"  # they asked me
    FRIEND = "friend"


class PlayerSuggestionRead(BaseModel):
    """A row in the "Добавить" tab (2026-10-08): a search hit, a teammate or
    someone friends with my friends. What anyone may see about a player
    before being friends: no age, no feed."""

    id: uuid.UUID
    first_name: str
    last_name: str
    avatar_url: str | None = None
    level: int
    jersey_number: int | None = None
    position: Position | None = None
    team_name: str | None = None
    mutual_friends: int = 0
    relation: FriendRelation = FriendRelation.NONE
    # Search only: "similar" for a spelling-tolerant hit (Питров -> Петров).
    match: Literal["exact", "similar"] = "exact"


class FriendRequestSentRead(BaseModel):
    """Response to POST /friends/requests -- the receiver's info (not the
    sender's, who already knows who they are) so the UI can confirm "request
    sent to <name>" even though the sender only typed in a code.
    """

    id: uuid.UUID
    status: FriendRequestStatus
    receiver_id: uuid.UUID
    receiver_first_name: str
    receiver_last_name: str
    receiver_avatar_url: str | None = None


class FriendRequestRead(BaseModel):
    """Assembled manually in FriendService (not from_attributes) -- a
    FriendRequest row plus the sender's display fields, same "flat, reused
    as-is" reasoning as team.TeamJoinRequestRead. Only the sender's info is
    carried since the only list this backs is "requests sent *to* me"
    (see FriendService.list_incoming_requests) -- the receiver is always
    the caller themself.
    """

    id: uuid.UUID
    sender_id: uuid.UUID
    sender_first_name: str
    sender_last_name: str
    sender_avatar_url: str | None = None
    status: FriendRequestStatus
    created_at: datetime
