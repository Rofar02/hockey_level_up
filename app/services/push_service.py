"""Low-level Web Push sending, using pywebpush + this app's VAPID key pair
(app/core/config.py). Deliberately a plain function here, not a class --
same style as stat_service.py's pure functions, no per-call state to hold.
"""
import json
import logging

from pywebpush import WebPushException, webpush_async
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.push_subscription import PushSubscription

logger = logging.getLogger(__name__)

# The push service (browser vendor's endpoint) returns this when the
# subscription no longer exists -- uninstalled, browser data cleared,
# permission revoked, ... It's permanent, not a transient failure worth
# retrying, so the dead row is removed rather than just logged: leaving it
# behind would mean every future send to this user keeps failing on it
# forever.
GONE_STATUS = 410


async def send_push(
    session: AsyncSession, subscription: PushSubscription, title: str, body: str
) -> bool:
    """Sends one Web Push notification. Returns whether it was actually
    delivered. On a 410 from the push service, deletes `subscription` from
    the DB (flushed, not committed -- the caller owns the transaction)."""
    settings = get_settings()
    try:
        await webpush_async(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh_key, "auth": subscription.auth_key},
            },
            data=json.dumps({"title": title, "body": body}),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
        )
        return True
    except WebPushException as exc:
        status_code = getattr(exc.response, "status", None)
        if status_code == GONE_STATUS:
            logger.info(
                "Push subscription %s is gone (410) -- removing it", subscription.id
            )
            await session.delete(subscription)
            await session.flush()
        else:
            logger.exception(
                "Push send failed for subscription_id=%s (status=%s)",
                subscription.id,
                status_code,
            )
        return False
    except ValueError:
        # pywebpush base64-decodes p256dh_key/auth_key *before* making any
        # request -- malformed key data (corrupted row, bad client input
        # that somehow got saved) raises a plain binascii.Error (a ValueError
        # subclass) here, not a WebPushException, since it never reaches the
        # HTTP layer at all. Not the same as a confirmed-dead (410)
        # subscription, so it's logged and left alone rather than deleted.
        logger.exception(
            "Push send failed for subscription_id=%s: malformed key data", subscription.id
        )
        return False
