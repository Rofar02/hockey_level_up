from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.training_block import TrainingBlockRead
from app.services.training_block_service import TrainingBlockService

router = APIRouter(prefix="/training-block", tags=["training-block"])


@router.get("/current", response_model=TrainingBlockRead)
async def get_current_training_block(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TrainingBlockService(session).get_current(current_user.id)
