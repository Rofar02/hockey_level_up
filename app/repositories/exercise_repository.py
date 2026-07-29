import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import EquipmentType, Exercise, ExerciseCategory, TargetStat, TrainingPhase


class ExerciseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(
        self,
        category: ExerciseCategory | None = None,
        phase: TrainingPhase | None = None,
        equipment_type: EquipmentType | None = None,
        target_stat: TargetStat | None = None,
    ) -> list[Exercise]:
        query = select(Exercise)
        if category is not None:
            query = query.where(Exercise.category == category)
        if phase is not None:
            query = query.where(Exercise.phase == phase)
        if equipment_type is not None:
            query = query.where(Exercise.equipment_type == equipment_type)
        if target_stat is not None:
            query = query.where(Exercise.target_stat == target_stat)

        result = await self._session.execute(query.order_by(Exercise.name))
        return list(result.scalars().all())

    async def get_by_id(self, exercise_id: uuid.UUID) -> Exercise | None:
        return await self._session.get(Exercise, exercise_id)
