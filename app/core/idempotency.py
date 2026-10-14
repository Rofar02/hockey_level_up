"""Idempotency-Key for workout writes (Б2, 2026-10-13).

The offline queue on the phone resends every action until it hears a 2xx:
a response lost on a bad connection, a second tab, an app killed mid-send.
A request that carries `Idempotency-Key: <uuid>` is applied once per
(player, key); every repeat gets the first answer back, same status code,
with nothing written again and no second XP.

How "once" holds:
- the key row is inserted (flushed, not committed) before the action runs,
  so it commits in the very transaction the service commits the action in
  -- "key stored" always means "action applied", never one without the other;
- a concurrent repeat blocks on the unique (user_id, key) index until the
  first commits, then sees the row;
- the response is written into the row right after the action's commit; a
  repeat arriving in that instant waits for it briefly.
Errors are not stored: a 4xx rolls the key back with the action, so the
client can see the same error again (and the queue drops the action).

Review 14.10 (15): the row keeps a hash of the request body -- the same key
with a different body is the client's bug, 422, never a replay of the wrong
answer. A row whose answer never got stored (the process died between the
commit and writing it) is answered by re-reading the resource, not with a
bare "already applied".

XP/stats/streak need nothing extra here: the action's outbox event commits
with it, and each consumer marks the event processed (app/events/idempotency.py).
"""
import asyncio
import hashlib
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, TypeAdapter
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.idempotency_key import IdempotencyKey
from app.models.user import User

RETENTION_DAYS = 7
# How long a repeat waits for the first request's stored answer.
REPLAY_WAIT_SECONDS = 3.0
_REPLAY_POLL_SECONDS = 0.1


def _parse_key(raw: str) -> str:
    try:
        return str(uuid.UUID(raw))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Idempotency-Key must be a UUID") from exc


async def _find(session: AsyncSession, user_id: uuid.UUID, key: str) -> IdempotencyKey | None:
    return await session.scalar(
        select(IdempotencyKey)
        .where(IdempotencyKey.user_id == user_id, IdempotencyKey.key == key)
        .execution_options(populate_existing=True)
    )


def body_hash(body: BaseModel | None) -> str | None:
    if body is None:
        return None
    canonical = json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


async def _replay(
    session: AsyncSession,
    row: IdempotencyKey,
    endpoint: str,
    request_hash: str | None,
    user: User,
    user_id: uuid.UUID,
    key: str,
    status_code: int,
    response_type: Any,
    reread: Callable[[], Awaitable[Any]] | None,
) -> Any:
    if row.endpoint != endpoint or (row.request_hash is not None and row.request_hash != request_hash):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Idempotency-Key already used for another request",
        )
    waited = 0.0
    while row.status_code is None and waited < REPLAY_WAIT_SECONDS:
        await session.rollback()
        await asyncio.sleep(_REPLAY_POLL_SECONDS)
        waited += _REPLAY_POLL_SECONDS
        found = await _find(session, user_id, key)
        if found is None:
            break
        row = found
    if row.status_code is None:
        # The action is applied (its key row committed with it); only the
        # stored answer is missing -- the process died in between. The
        # resource as it is now is that answer.
        if reread is not None:
            # The waiting above rolled back -- the player's row is expired.
            await session.refresh(user)
            current = await reread()
            content = TypeAdapter(response_type).dump_python(
                TypeAdapter(response_type).validate_python(current, from_attributes=True), mode="json"
            )
            return JSONResponse(status_code=status_code, content=content)
        return JSONResponse(status_code=status.HTTP_200_OK, content={"detail": "already applied"})
    return JSONResponse(status_code=row.status_code, content=row.response_json)


async def run_idempotent(
    session: AsyncSession,
    user: User,
    raw_key: str | None,
    endpoint: str,
    status_code: int,
    response_type: Any,
    action: Callable[[], Awaitable[Any]],
    *,
    body: BaseModel | None = None,
    reread: Callable[[], Awaitable[Any]] | None = None,
) -> Any:
    """Runs `action` once per (user, key). Without a key it just runs it --
    older clients and the online-only screens keep working unchanged.
    `body`: the request's payload, hashed to tell a repeat from a misuse.
    `reread`: fetches the resource as it is now (no side effects)."""
    if raw_key is None:
        return await action()
    key = _parse_key(raw_key)
    user_id = user.id
    request_hash = body_hash(body)

    async def replay(found: IdempotencyKey) -> Any:
        return await _replay(
            session, found, endpoint, request_hash, user, user_id, key, status_code, response_type, reread
        )

    existing = await _find(session, user_id, key)
    if existing is not None:
        return await replay(existing)

    row = IdempotencyKey(user_id=user_id, key=key, endpoint=endpoint, request_hash=request_hash)
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:
        # A parallel repeat got there first and has committed by now.
        await session.rollback()
        existing = await _find(session, user_id, key)
        if existing is None:
            raise
        return await replay(existing)

    result = await action()

    row.status_code = status_code
    row.response_json = TypeAdapter(response_type).dump_python(
        TypeAdapter(response_type).validate_python(result, from_attributes=True), mode="json"
    )
    await session.commit()
    return result
