import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox import OutboxEvent
from app.models.user import User
from app.repositories.friend_repository import FriendRepository
from app.schemas.friend_activity import ActivityFeedEntryRead

LEVEL_UP_EVENT = "level_up"
TRAINING_COMPLETED_EVENT = "training_completed"
# One row per trainer (see TrainingPartyService._maybe_finish) -- same
# user_id-keyed shape as the other two, so it needs no special-casing in the
# query below, only in _to_entry's payload extraction.
PARTY_COMPLETED_EVENT = "party_completed"
FEED_EVENT_TYPES = (LEVEL_UP_EVENT, TRAINING_COMPLETED_EVENT, PARTY_COMPLETED_EVENT)


class FriendActivityService:
    """Reads outbox_events directly rather than via a RabbitMQ consumer --
    it's a persistent table (never purged, see app/models/outbox.py), so
    it doubles as the event history a feed needs. No new event log.

    Filters on payload->>'user_id' (JSONB text extraction) rather than a
    dedicated column -- see get_feed for the efficiency caveat.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._friends = FriendRepository(session)

    async def get_feed(
        self, user_id: uuid.UUID, limit: int, offset: int
    ) -> list[ActivityFeedEntryRead]:
        friend_ids = await self._friends.list_friend_ids(user_id)
        if not friend_ids:
            return []
        friend_id_strings = [str(friend_id) for friend_id in friend_ids]

        # payload["user_id"].astext -> Postgres `payload ->> 'user_id'`.
        # No index backs this (outbox_events only has the partial
        # ix_outbox_events_unpublished on created_at) -- every call scans
        # the full, never-purged table. Fine at current scale; flagged as a
        # real scaling risk in the implementation report, not fixed here.
        result = await self._session.execute(
            select(OutboxEvent)
            .where(
                OutboxEvent.event_type.in_(FEED_EVENT_TYPES),
                OutboxEvent.payload["user_id"].astext.in_(friend_id_strings),
            )
            .order_by(OutboxEvent.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        events = list(result.scalars().all())

        actor_ids = {uuid.UUID(event.payload["user_id"]) for event in events}
        actors = await self._load_actors(actor_ids)

        entries = []
        for event in events:
            actor = actors.get(uuid.UUID(event.payload["user_id"]))
            if actor is None:
                # Actor account deleted since the event was recorded --
                # skip rather than show an orphaned entry with no name.
                continue
            entries.append(self._to_entry(event, actor))
        return entries

    async def _load_actors(self, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, User]:
        if not user_ids:
            return {}
        result = await self._session.execute(select(User).where(User.id.in_(user_ids)))
        return {user.id: user for user in result.scalars().all()}

    @staticmethod
    def _to_entry(event: OutboxEvent, actor: User) -> ActivityFeedEntryRead:
        return ActivityFeedEntryRead(
            id=event.id,
            event_type=event.event_type,
            user_id=actor.id,
            first_name=actor.first_name,
            last_name=actor.last_name,
            avatar_url=actor.avatar_url,
            created_at=event.created_at,
            level=event.payload.get("new_level") if event.event_type == LEVEL_UP_EVENT else None,
            session_type=(
                event.payload.get("session_type")
                if event.event_type == TRAINING_COMPLETED_EVENT
                else None
            ),
            party_size=event.payload.get("party_size") if event.event_type == PARTY_COMPLETED_EVENT else None,
        )
