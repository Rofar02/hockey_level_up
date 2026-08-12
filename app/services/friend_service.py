import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.friend import FriendRequest, FriendRequestStatus
from app.models.user import User
from app.repositories.friend_repository import FriendRepository
from app.schemas.friend import FriendRead, FriendRequestRead, FriendRequestSentRead


class FriendService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._friends = FriendRepository(session)

    async def send_request_by_code(self, sender: User, code: str) -> FriendRequestSentRead:
        receiver = await self._friends.get_user_by_friend_code(code)
        if receiver is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid friend code")
        if receiver.id == sender.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Can't send a friend request to yourself"
            )

        # Reverse direction first: if they already asked *us*, this call
        # accepts their existing request instead of creating a second
        # pending row the other way -- that's the "no duplicate pending
        # requests in both directions" rule from the diagnosis, resolved by
        # auto-accepting rather than rejecting the second sender.
        reverse = await self._friends.get_request(sender_id=receiver.id, receiver_id=sender.id)
        if reverse is not None:
            if reverse.status == FriendRequestStatus.ACCEPTED:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already friends")
            if reverse.status == FriendRequestStatus.PENDING:
                reverse.status = FriendRequestStatus.ACCEPTED
                reverse.responded_at = datetime.now(timezone.utc)
                await self._session.commit()
                return self._to_sent_read(reverse, receiver)
            # DECLINED reverse row doesn't block a fresh forward request --
            # it's a different (sender_id, receiver_id) ordered pair, so the
            # unique constraint has nothing to say about it. Fall through.

        forward = await self._friends.get_request(sender_id=sender.id, receiver_id=receiver.id)
        if forward is not None:
            if forward.status == FriendRequestStatus.PENDING:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="Friend request already sent"
                )
            if forward.status == FriendRequestStatus.ACCEPTED:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already friends")
            # DECLINED -- re-send by resetting the same row rather than
            # inserting a second one (UniqueConstraint(sender_id,
            # receiver_id) forbids a second row for this ordered pair).
            forward.status = FriendRequestStatus.PENDING
            forward.created_at = datetime.now(timezone.utc)
            forward.responded_at = None
            await self._session.commit()
            return self._to_sent_read(forward, receiver)

        request = await self._friends.create_request(sender.id, receiver.id)
        await self._session.commit()
        return self._to_sent_read(request, receiver)

    async def list_incoming_requests(self, user: User) -> list[FriendRequestRead]:
        requests = await self._friends.list_incoming_pending(user.id)
        reads = []
        for request in requests:
            sender = await self._session.get(User, request.sender_id)
            if sender is None:
                continue
            reads.append(self._to_request_read(request, sender))
        return reads

    async def respond_to_request(
        self, receiver: User, request_id: uuid.UUID, accept: bool
    ) -> FriendRequestRead:
        request = await self._friends.get_request_by_id(request_id)
        if request is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Friend request not found")
        if request.receiver_id != receiver.id:
            # Only the receiver decides -- unlike TeamJoinRequest, there's no
            # captain role standing in for anyone else here.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Not your request to respond to"
            )
        if request.status != FriendRequestStatus.PENDING:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already responded to")

        request.status = FriendRequestStatus.ACCEPTED if accept else FriendRequestStatus.DECLINED
        request.responded_at = datetime.now(timezone.utc)
        await self._session.commit()
        # FK CASCADE on sender_id guarantees the sender row still exists
        # whenever this request row does -- same trust-the-FK reasoning as
        # TeamService._to_join_request_read.
        sender = await self._session.get(User, request.sender_id)
        return self._to_request_read(request, sender)

    async def list_friends(self, user_id: uuid.UUID) -> list[FriendRead]:
        friends = await self._friends.list_friends(user_id)
        return [
            FriendRead(
                id=friend.id,
                first_name=friend.first_name,
                last_name=friend.last_name,
                avatar_url=friend.avatar_url,
                level=friend.level,
                jersey_number=friend.jersey_number,
                position=friend.position,
            )
            for friend in friends
        ]

    async def list_friend_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        return await self._friends.list_friend_ids(user_id)

    async def are_friends(self, user_id: uuid.UUID, other_id: uuid.UUID) -> bool:
        return await self._friends.get_accepted_request_between(user_id, other_id) is not None

    async def remove_friend(self, user: User, friend_id: uuid.UUID) -> None:
        request = await self._friends.get_accepted_request_between(user.id, friend_id)
        if request is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not friends")
        await self._friends.delete_request(request)
        await self._session.commit()

    @staticmethod
    def _to_request_read(request: FriendRequest, sender: User) -> FriendRequestRead:
        return FriendRequestRead(
            id=request.id,
            sender_id=sender.id,
            sender_first_name=sender.first_name,
            sender_last_name=sender.last_name,
            sender_avatar_url=sender.avatar_url,
            status=request.status,
            created_at=request.created_at,
        )

    @staticmethod
    def _to_sent_read(request: FriendRequest, receiver: User) -> FriendRequestSentRead:
        return FriendRequestSentRead(
            id=request.id,
            status=request.status,
            receiver_id=receiver.id,
            receiver_first_name=receiver.first_name,
            receiver_last_name=receiver.last_name,
            receiver_avatar_url=receiver.avatar_url,
        )
