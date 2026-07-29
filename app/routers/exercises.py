import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.exercise import EquipmentType, ExerciseCategory, TargetStat, TrainingPhase
from app.models.user import User
from app.routers.deps import require_admin
from app.schemas.exercise import ExerciseCreate, ExerciseRead, ExerciseUpdate
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


@router.post("", response_model=ExerciseRead, status_code=status.HTTP_201_CREATED)
async def create_exercise(
    body: ExerciseCreate,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await ExerciseService(session).create_exercise(body)


@router.patch("/{exercise_id}", response_model=ExerciseRead)
async def update_exercise(
    exercise_id: uuid.UUID,
    body: ExerciseUpdate,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await ExerciseService(session).update_exercise(exercise_id, body)


@router.delete("/{exercise_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exercise(
    exercise_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    await ExerciseService(session).delete_exercise(exercise_id)
