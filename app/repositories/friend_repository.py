import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.friend import FriendRequest, FriendRequestStatus
from app.models.user import User


class FriendRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_user_by_friend_code(self, friend_code: str) -> User | None:
        result = await self._session.execute(select(User).where(User.friend_code == friend_code))
        return result.scalar_one_or_none()

    async def get_request(
        self, sender_id: uuid.UUID, receiver_id: uuid.UUID
    ) -> FriendRequest | None:
        result = await self._session.execute(
            select(FriendRequest).where(
                FriendRequest.sender_id == sender_id, FriendRequest.receiver_id == receiver_id
            )
        )
        return result.scalar_one_or_none()

    async def get_request_by_id(self, request_id: uuid.UUID) -> FriendRequest | None:
        return await self._session.get(FriendRequest, request_id)

    async def get_accepted_request_between(
        self, user_id: uuid.UUID, other_id: uuid.UUID
    ) -> FriendRequest | None:
        """Direction-agnostic -- an accepted (A,B) row and an accepted (B,A)
        row can never both exist (send_request_by_code always resolves a
        pending reverse row instead of letting a second one form), so at
        most one row ever matches this either-direction lookup.
        """
        result = await self._session.execute(
            select(FriendRequest).where(
                FriendRequest.status == FriendRequestStatus.ACCEPTED,
                or_(
                    and_(FriendRequest.sender_id == user_id, FriendRequest.receiver_id == other_id),
                    and_(FriendRequest.sender_id == other_id, FriendRequest.receiver_id == user_id),
                ),
            )
        )
        return result.scalar_one_or_none()

    async def create_request(self, sender_id: uuid.UUID, receiver_id: uuid.UUID) -> FriendRequest:
        request = FriendRequest(sender_id=sender_id, receiver_id=receiver_id)
        self._session.add(request)
        await self._session.flush()
        return request

    async def delete_request(self, request: FriendRequest) -> None:
        await self._session.delete(request)
        await self._session.flush()

    async def list_incoming_pending(self, user_id: uuid.UUID) -> list[FriendRequest]:
        result = await self._session.execute(
            select(FriendRequest)
            .where(
                FriendRequest.receiver_id == user_id,
                FriendRequest.status == FriendRequestStatus.PENDING,
            )
            .order_by(FriendRequest.created_at)
        )
        return list(result.scalars().all())

    async def list_friends(self, user_id: uuid.UUID) -> list[User]:
        # Single query, either direction: joins User to whichever side of an
        # ACCEPTED row isn't user_id.
        result = await self._session.execute(
            select(User)
            .join(
                FriendRequest,
                or_(
                    and_(FriendRequest.sender_id == user_id, FriendRequest.receiver_id == User.id),
                    and_(FriendRequest.receiver_id == user_id, FriendRequest.sender_id == User.id),
                ),
            )
            .where(FriendRequest.status == FriendRequestStatus.ACCEPTED)
            .order_by(User.first_name, User.last_name)
        )
        return list(result.scalars().all())

    async def list_friend_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        result = await self._session.execute(
            select(FriendRequest.sender_id, FriendRequest.receiver_id).where(
                FriendRequest.status == FriendRequestStatus.ACCEPTED,
                or_(FriendRequest.sender_id == user_id, FriendRequest.receiver_id == user_id),
            )
        )
        return [
            receiver_id if sender_id == user_id else sender_id
            for sender_id, receiver_id in result.all()
        ]
