import uuid

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import (
    EquipmentType,
    Exercise,
    ExerciseCategory,
    MovementPattern,
    TargetStat,
    TrainingPhase,
)
from app.repositories.exercise_repository import ExerciseRepository
from app.schemas.exercise import ExerciseCreate, ExerciseUpdate


class ExerciseService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._exercises = ExerciseRepository(session)

    async def list_exercises(
        self,
        category: ExerciseCategory | None = None,
        phase: TrainingPhase | None = None,
        equipment_type: EquipmentType | None = None,
        target_stat: TargetStat | None = None,
    ) -> list[Exercise]:
        return await self._exercises.list_exercises(
            category=category,
            phase=phase,
            equipment_type=equipment_type,
            target_stat=target_stat,
        )

    async def get_exercise(self, exercise_id: uuid.UUID) -> Exercise:
        exercise = await self._exercises.get_by_id(exercise_id)
        if exercise is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Exercise not found"
            )
        return exercise

    async def create_exercise(self, data: ExerciseCreate) -> Exercise:
        try:
            exercise = await self._exercises.create(data)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Exercise name already exists"
            ) from exc
        return exercise

    async def update_exercise(self, exercise_id: uuid.UUID, data: ExerciseUpdate) -> Exercise:
        exercise = await self.get_exercise(exercise_id)

        updates = data.model_dump(exclude_unset=True)
        try:
            await self._exercises.update(exercise, updates)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Exercise name already exists"
            ) from exc
        await self._session.refresh(exercise)
        return exercise

    async def list_movement_patterns(self, exercise_id: uuid.UUID) -> list[MovementPattern]:
        await self.get_exercise(exercise_id)
        return await self._exercises.list_movement_patterns(exercise_id)

    async def replace_movement_patterns(
        self, exercise_id: uuid.UUID, patterns: list[MovementPattern]
    ) -> list[MovementPattern]:
        await self.get_exercise(exercise_id)
        unique_patterns = list(dict.fromkeys(patterns))
        await self._exercises.replace_movement_patterns(exercise_id, unique_patterns)
        await self._session.commit()
        return unique_patterns

    async def delete_exercise(self, exercise_id: uuid.UUID) -> None:
        exercise = await self.get_exercise(exercise_id)
        try:
            await self._exercises.delete(exercise)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Exercise is used in existing training sessions and cannot be deleted",
            ) from exc
