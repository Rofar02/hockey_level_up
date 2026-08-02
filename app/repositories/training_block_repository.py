import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schedule import TrainingBlock


class TrainingBlockRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_for_user(self, user_id: uuid.UUID) -> TrainingBlock | None:
        """The user's current block: the row with the highest block_number."""
        result = await self._session.execute(
            select(TrainingBlock)
            .where(TrainingBlock.user_id == user_id)
            .order_by(TrainingBlock.block_number.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def create(self, block: TrainingBlock) -> TrainingBlock:
        self._session.add(block)
        await self._session.flush()
        return block

    async def get_by_id(self, block_id: uuid.UUID) -> TrainingBlock | None:
        return await self._session.get(TrainingBlock, block_id)
