import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.exercise import EquipmentItem, ExerciseCategory, MovementPattern, TargetStat, TrainingPhase
from app.models.user import User
from app.routers.deps import get_current_user, require_admin
from app.schemas.exercise import (
    EquipmentItemsReplace,
    ExerciseCreate,
    ExerciseEquipmentRequirement,
    ExerciseRead,
    ExerciseUpdate,
    MovementPatternsReplace,
    MuscleGroupsReplace,
    MuscleGroupWeight,
    SuggestedRepsRead,
    SuggestedWeightRead,
    TargetStatsReplace,
)
from app.schemas.skill import SkillTagRead
from app.services.exercise_service import ExerciseService
from app.services.reps_suggestion_service import RepsSuggestionService
from app.services.skill_service import SkillService
from app.services.weight_suggestion_service import WeightSuggestionService

router = APIRouter(prefix="/exercises", tags=["exercises"])


@router.get("", response_model=list[ExerciseRead])
async def list_exercises(
    session: Annotated[AsyncSession, Depends(get_db)],
    category: Annotated[ExerciseCategory | None, Query()] = None,
    phase: Annotated[TrainingPhase | None, Query()] = None,
    target_stat: Annotated[TargetStat | None, Query()] = None,
):
    return await ExerciseService(session).list_exercises(
        category=category,
        phase=phase,
        target_stat=target_stat,
    )


@router.get("/equipment-requirements", response_model=list[ExerciseEquipmentRequirement])
async def list_exercise_equipment_requirements(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Bulk, not admin-gated (unlike GET .../{id}/equipment-items) -- lets
    the onboarding/profile inventory screen compute its live "unlocked N
    exercises" counter client-side. Must be registered before
    GET /{exercise_id} below, or FastAPI would try to parse
    "equipment-requirements" as a UUID path param."""
    return await ExerciseService(session).list_equipment_requirements()


@router.get("/{exercise_id}", response_model=ExerciseRead)
async def get_exercise(
    exercise_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_db)]
):
    return await ExerciseService(session).get_exercise_read(exercise_id)


@router.get("/{exercise_id}/skill-tags", response_model=list[SkillTagRead])
async def list_exercise_skill_tags(
    exercise_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Which skills this exercise is tagged for -- for the admin exercise
    edit form, so its skill associations are visible/editable right there
    instead of only reachable per-skill under /skills/{id}/tags."""
    return await SkillService(session).list_tags_for_exercise(exercise_id)


@router.get("/{exercise_id}/movement-patterns", response_model=list[MovementPattern])
async def list_exercise_movement_patterns(
    exercise_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await ExerciseService(session).list_movement_patterns(exercise_id)


@router.put("/{exercise_id}/movement-patterns", response_model=list[MovementPattern])
async def replace_exercise_movement_patterns(
    exercise_id: uuid.UUID,
    body: MovementPatternsReplace,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await ExerciseService(session).replace_movement_patterns(
        exercise_id, body.movement_patterns
    )


@router.get("/{exercise_id}/muscle-groups", response_model=list[MuscleGroupWeight])
async def list_exercise_muscle_groups(
    exercise_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await ExerciseService(session).list_muscle_groups(exercise_id)


@router.put("/{exercise_id}/muscle-groups", response_model=list[MuscleGroupWeight])
async def replace_exercise_muscle_groups(
    exercise_id: uuid.UUID,
    body: MuscleGroupsReplace,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await ExerciseService(session).replace_muscle_groups(exercise_id, body.muscle_groups)


@router.get("/{exercise_id}/equipment-items", response_model=list[EquipmentItem])
async def list_exercise_equipment_items(
    exercise_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await ExerciseService(session).list_equipment_items(exercise_id)


@router.put("/{exercise_id}/equipment-items", response_model=list[EquipmentItem])
async def replace_exercise_equipment_items(
    exercise_id: uuid.UUID,
    body: EquipmentItemsReplace,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await ExerciseService(session).replace_equipment_items(exercise_id, body.equipment_items)


@router.get("/{exercise_id}/target-stats", response_model=list[TargetStat])
async def list_exercise_target_stats(
    exercise_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await ExerciseService(session).list_target_stats(exercise_id)


@router.put("/{exercise_id}/target-stats", response_model=list[TargetStat])
async def replace_exercise_target_stats(
    exercise_id: uuid.UUID,
    body: TargetStatsReplace,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await ExerciseService(session).replace_target_stats(exercise_id, body.target_stats)


@router.get("/{exercise_id}/suggested-weight", response_model=SuggestedWeightRead)
async def get_suggested_weight(
    exercise_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    exercise = await ExerciseService(session).get_exercise(exercise_id)
    suggested = await WeightSuggestionService(session).suggest_weight(current_user, exercise)
    return SuggestedWeightRead(suggested_weight_kg=suggested)


@router.get("/{exercise_id}/suggested-reps", response_model=SuggestedRepsRead)
async def get_suggested_reps(
    exercise_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    exercise = await ExerciseService(session).get_exercise(exercise_id)
    suggested = await RepsSuggestionService(session).suggest_reps(current_user, exercise)
    return SuggestedRepsRead(suggested_reps=suggested)


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
