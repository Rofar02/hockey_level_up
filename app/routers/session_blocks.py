import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.idempotency import run_idempotent
from app.db.session import get_db
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.schedule import BlockResolveIn, SessionBlockRead
from app.services.schedule_service import ScheduleService
from app.services.session_block_service import SessionBlockService

router = APIRouter(prefix="/session-blocks", tags=["session-blocks"])

# Б2: the offline queue sends every write with one; a repeat is replayed.
IdempotencyKeyHeader = Annotated[str | None, Header(alias="Idempotency-Key")]
OptionalResolveBody = Annotated[BlockResolveIn | None, Body()]


@router.post("/{block_id}/complete", response_model=SessionBlockRead)
async def complete_session_block(
    block_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    body: OptionalResolveBody = None,
    idempotency_key: IdempotencyKeyHeader = None,
):
    performed_at = body.performed_at if body is not None else None
    return await run_idempotent(
        session,
        current_user,
        idempotency_key,
        f"POST /session-blocks/{block_id}/complete",
        status.HTTP_200_OK,
        SessionBlockRead,
        lambda: SessionBlockService(session).complete_block(block_id, current_user, performed_at),
        body=body,
        reread=lambda: SessionBlockService(session).read_block(block_id, current_user),
    )


@router.post("/{block_id}/skip", response_model=SessionBlockRead)
async def skip_session_block(
    block_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    body: OptionalResolveBody = None,
    idempotency_key: IdempotencyKeyHeader = None,
):
    """Warmup/cooldown-only (media-player redesign, 2026-08-28): resolves
    the block without earning stat/XP/muscle-load gain, see
    SessionBlockService.skip_block."""
    performed_at = body.performed_at if body is not None else None
    return await run_idempotent(
        session,
        current_user,
        idempotency_key,
        f"POST /session-blocks/{block_id}/skip",
        status.HTTP_200_OK,
        SessionBlockRead,
        lambda: SessionBlockService(session).skip_block(block_id, current_user, performed_at),
        body=body,
        reread=lambda: SessionBlockService(session).read_block(block_id, current_user),
    )


@router.post("/{block_id}/replace", response_model=SessionBlockRead)
async def replace_session_block_exercise(
    block_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Stage 1.5 (2026-08-20 planning session, "тренажёр занят"): manual
    single-slot swap, see ScheduleService.replace_block_exercise."""
    return await ScheduleService(session).replace_block_exercise(block_id, current_user)
