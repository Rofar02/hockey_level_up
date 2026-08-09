import asyncio
import json
import logging
import uuid

import aio_pika

from app.core.config import get_settings
from app.events.publisher import (
    DEAD_LETTER_EXCHANGE,
    DEAD_LETTER_QUEUE,
    QUEUE_ARGUMENTS,
    QUEUE_NAME,
)
from app.events.registry import get_handlers

logger = logging.getLogger(__name__)


async def _dispatch(message: aio_pika.abc.AbstractIncomingMessage) -> None:
    try:
        data = json.loads(message.body)
        event_id = uuid.UUID(data["event_id"])
        event_type = data["event_type"]
        payload = data["payload"]
    except Exception:
        logger.exception("Failed to parse event message body; dead-lettering")
        await message.reject(requeue=False)
        return

    failed = False
    for handler in get_handlers(event_type):
        try:
            await handler(payload, event_id)
        except Exception:
            failed = True
            # payload is included in the message text itself, not just via
            # `extra=` -- the default logging formatter doesn't render extra
            # fields, so extra-only would silently drop the payload from the
            # actual log output.
            logger.exception(
                "Handler %s failed for event_type=%s payload=%s",
                handler.__qualname__,
                event_type,
                payload,
                extra={"payload": payload, "event_type": event_type},
            )

    if failed:
        # Dead-letter immediately rather than requeue-and-retry: there is no
        # retry-count tracking, and failures observed in practice (e.g.
        # UniqueViolationError from concurrent inserts) are not obviously
        # transient, so blindly requeuing the same message could hot-loop.
        # A human/process can inspect and replay from the DLQ deliberately.
        #
        # Note: handlers for the same message are independent side effects
        # (stat/streak/xp). If only one handler fails, the others have
        # already committed by the time we dead-letter here, so a naive
        # replay of the DLQ message re-runs *all* handlers again. That's
        # safe now: each handler claims (event_id, handler_name) in
        # processed_events in the same transaction as its own side-effect
        # (see app/events/idempotency.py), so a handler that already
        # committed just finds its claim on replay and skips, while one that
        # never committed (no claim persisted) retries properly.
        await message.reject(requeue=False)
    else:
        await message.ack()


async def run_consumer() -> None:
    # Import here so handler modules register themselves before we start consuming.
    from app.events.handlers import block_completed  # noqa: F401

    settings = get_settings()
    try:
        connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    except Exception:
        logger.exception("Event consumer could not connect to RabbitMQ; consumer disabled")
        return

    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)

        dlx = await channel.declare_exchange(
            DEAD_LETTER_EXCHANGE, aio_pika.ExchangeType.FANOUT, durable=True
        )
        dead_letter_queue = await channel.declare_queue(DEAD_LETTER_QUEUE, durable=True)
        await dead_letter_queue.bind(dlx)

        queue = await channel.declare_queue(QUEUE_NAME, durable=True, arguments=QUEUE_ARGUMENTS)
        await queue.consume(_dispatch)
        await asyncio.Future()
