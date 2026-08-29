from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.quest import QuestStatusRead
from app.services.quest_service import QuestService

router = APIRouter(prefix="/quests", tags=["quests"])


@router.get("/status", response_model=list[QuestStatusRead])
async def get_quest_status(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await QuestService(session).list_status(current_user.id)


@router.post("/reference-visited", status_code=status.HTTP_204_NO_CONTENT)
async def mark_reference_visited(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """reference_first_visit has no server-side trace to check on its own
    (see QuestService's own docstring) -- ReferencePage calls this once its
    articles load successfully. Idempotent, safe on every visit."""
    await QuestService(session).mark_reference_visited(current_user.id)
