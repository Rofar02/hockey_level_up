import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import EquipmentType, Exercise, ExerciseCategory, TargetStat, TrainingPhase
from app.schemas.exercise import ExerciseCreate


class ExerciseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_exercises(
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

    async def create(self, data: ExerciseCreate) -> Exercise:
        exercise = Exercise(**data.model_dump())
        self._session.add(exercise)
        await self._session.flush()
        return exercise

    async def update(self, exercise: Exercise, updates: dict) -> Exercise:
        for field, value in updates.items():
            setattr(exercise, field, value)
        await self._session.flush()
        return exercise

    async def delete(self, exercise: Exercise) -> None:
        await self._session.delete(exercise)
        await self._session.flush()

    async def list_for_assembly(
        self,
        phase: TrainingPhase,
        equipment_access: EquipmentType,
        category: ExerciseCategory | None = None,
    ) -> list[Exercise]:
        """Candidates for training-session assembly.

        equipment_access only constrains off_ice exercises -- on the ice, the
        player doesn't choose gym/home/bodyweight, so on_ice exercises are
        never excluded by equipment.
        """
        query = select(Exercise).where(Exercise.phase == phase)
        if category is not None:
            query = query.where(Exercise.category == category)
        query = query.where(
            or_(
                Exercise.category == ExerciseCategory.ON_ICE,
                Exercise.equipment_type == equipment_access,
            )
        )

        result = await self._session.execute(query.order_by(Exercise.name))
        return list(result.scalars().all())
