import uuid

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.push_subscription import PushSubscription


class PushSubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        user_id: uuid.UUID,
        endpoint: str,
        p256dh_key: str,
        auth_key: str,
        user_agent: str | None,
    ) -> PushSubscription:
        """Re-subscribing from the same device (same endpoint) updates the
        keys in place rather than erroring on uq_push_subscriptions_user_endpoint
        -- browsers can rotate a subscription's keys without changing the
        endpoint, and the client has no way to know whether this is the
        first subscribe or a refresh."""
        stmt = (
            pg_insert(PushSubscription)
            .values(
                user_id=user_id,
                endpoint=endpoint,
                p256dh_key=p256dh_key,
                auth_key=auth_key,
                user_agent=user_agent,
            )
            .on_conflict_do_update(
                constraint="uq_push_subscriptions_user_endpoint",
                set_={"p256dh_key": p256dh_key, "auth_key": auth_key, "user_agent": user_agent},
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

        result = await self._session.execute(
            select(PushSubscription).where(
                PushSubscription.user_id == user_id, PushSubscription.endpoint == endpoint
            )
        )
        return result.scalar_one()

    async def list_for_user(self, user_id: uuid.UUID) -> list[PushSubscription]:
        result = await self._session.execute(
            select(PushSubscription).where(PushSubscription.user_id == user_id)
        )
        return list(result.scalars().all())

    async def delete_by_endpoint(self, user_id: uuid.UUID, endpoint: str) -> bool:
        result = await self._session.execute(
            delete(PushSubscription).where(
                PushSubscription.user_id == user_id, PushSubscription.endpoint == endpoint
            )
        )
        await self._session.flush()
        return result.rowcount > 0

    async def delete(self, subscription: PushSubscription) -> None:
        await self._session.delete(subscription)
        await self._session.flush()
