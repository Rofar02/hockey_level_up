import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.training_block import get_phase
from app.repositories.training_block_repository import TrainingBlockRepository
from app.schemas.training_block import TrainingBlockRead


class TrainingBlockService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._blocks = TrainingBlockRepository(session)

    async def get_current(self, user_id: uuid.UUID) -> TrainingBlockRead:
        block = await self._blocks.get_active_for_user(user_id)
        if block is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No training block yet -- declare a weekly plan first",
            )
        return TrainingBlockRead(
            block_number=block.block_number,
            week_in_block=block.week_in_block,
            phase=get_phase(block.week_in_block),
        )
