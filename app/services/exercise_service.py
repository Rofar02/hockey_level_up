import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import EquipmentType, Exercise, ExerciseCategory, TargetStat, TrainingPhase
from app.repositories.exercise_repository import ExerciseRepository


class ExerciseService:
    def __init__(self, session: AsyncSession) -> None:
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
