import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.schedule import SessionBlockRead
from app.services.session_block_service import SessionBlockService

router = APIRouter(prefix="/session-blocks", tags=["session-blocks"])


@router.post("/{block_id}/complete", response_model=SessionBlockRead)
async def complete_session_block(
    block_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await SessionBlockService(session).complete_block(block_id, current_user)
