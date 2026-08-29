import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.push_subscription import PushSubscription
from app.repositories.push_subscription_repository import PushSubscriptionRepository
from app.schemas.push_subscription import PushSubscriptionCreate
from app.services.push_service import send_push

# Not "IceLevel" -- see reminder_scheduler.REMINDER_TITLE's own comment on
# why (the OS/browser already shows the PWA's name; repeating it as the
# notification's own title just doubles it up).
TEST_NOTIFICATION_TITLE = "Проверка push-уведомлений"
TEST_NOTIFICATION_BODY = "Если вы это видите — push работает."


class PushSubscriptionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._subscriptions = PushSubscriptionRepository(session)

    async def save(
        self, user_id: uuid.UUID, data: PushSubscriptionCreate, user_agent: str | None
    ) -> PushSubscription:
        subscription = await self._subscriptions.upsert(
            user_id=user_id,
            endpoint=data.endpoint,
            p256dh_key=data.keys.p256dh,
            auth_key=data.keys.auth,
            user_agent=user_agent,
        )
        await self._session.commit()
        return subscription

    async def unsubscribe(self, user_id: uuid.UUID, endpoint: str) -> None:
        deleted = await self._subscriptions.delete_by_endpoint(user_id, endpoint)
        await self._session.commit()
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Push subscription not found"
            )

    async def send_test_notification(self, user_id: uuid.UUID) -> tuple[int, int]:
        """Sends a test push to every subscription this user has right now.
        Returns (total_subscriptions, delivered) -- delivered can be less
        than total if some sends failed or some subscriptions turned out to
        be dead (and were removed as a side effect, see push_service)."""
        subscriptions = await self._subscriptions.list_for_user(user_id)
        delivered = 0
        for subscription in subscriptions:
            if await send_push(
                self._session, subscription, TEST_NOTIFICATION_TITLE, TEST_NOTIFICATION_BODY
            ):
                delivered += 1
        await self._session.commit()
        return len(subscriptions), delivered
