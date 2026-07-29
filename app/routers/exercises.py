import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.exercise import EquipmentType, ExerciseCategory, TargetStat, TrainingPhase
from app.schemas.exercise import ExerciseRead
from app.services.exercise_service import ExerciseService

router = APIRouter(prefix="/exercises", tags=["exercises"])


@router.get("", response_model=list[ExerciseRead])
async def list_exercises(
    session: Annotated[AsyncSession, Depends(get_db)],
    category: Annotated[ExerciseCategory | None, Query()] = None,
    phase: Annotated[TrainingPhase | None, Query()] = None,
    equipment_type: Annotated[EquipmentType | None, Query()] = None,
    target_stat: Annotated[TargetStat | None, Query()] = None,
):
    return await ExerciseService(session).list_exercises(
        category=category,
        phase=phase,
        equipment_type=equipment_type,
        target_stat=target_stat,
    )


@router.get("/{exercise_id}", response_model=ExerciseRead)
async def get_exercise(
    exercise_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_db)]
):
    return await ExerciseService(session).get_exercise(exercise_id)
