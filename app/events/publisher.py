import asyncio
import json
import uuid

import aio_pika

from app.core.config import get_settings

QUEUE_NAME = "domain_events"
DEAD_LETTER_EXCHANGE = "domain_events.dlx"
DEAD_LETTER_QUEUE = "domain_events.dead_letter"
QUEUE_ARGUMENTS = {"x-dead-letter-exchange": DEAD_LETTER_EXCHANGE}

_connection: aio_pika.abc.AbstractRobustConnection | None = None
_channel: aio_pika.abc.AbstractChannel | None = None
_lock = asyncio.Lock()


async def _get_channel() -> aio_pika.abc.AbstractChannel:
    global _connection, _channel
    async with _lock:
        if _channel is None or _channel.is_closed:
            settings = get_settings()
            _connection = await aio_pika.connect_robust(settings.rabbitmq_url)
            _channel = await _connection.channel()
            # Arguments must match the consumer's declaration exactly, or
            # RabbitMQ rejects the redeclare with PRECONDITION_FAILED.
            await _channel.declare_queue(QUEUE_NAME, durable=True, arguments=QUEUE_ARGUMENTS)
        return _channel


async def publish_event(event_id: uuid.UUID, event_type: str, payload: dict) -> None:
    channel = await _get_channel()
    body = json.dumps(
        {"event_id": str(event_id), "event_type": event_type, "payload": payload}
    ).encode()
    message = aio_pika.Message(
        body=body,
        content_type="application/json",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )
    await channel.default_exchange.publish(message, routing_key=QUEUE_NAME)


async def close_publisher() -> None:
    global _connection, _channel
    if _connection is not None:
        await _connection.close()
    _connection = None
    _channel = None
