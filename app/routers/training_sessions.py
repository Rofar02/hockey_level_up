import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.set_completion import ExerciseSetsRead, SetCompletionSummary
from app.schemas.training_diary import TrainingDiaryEntryIn, TrainingDiaryEntryRead
from app.services.set_completion_service import SetCompletionService
from app.services.training_diary_service import TrainingDiaryService

router = APIRouter(prefix="/training-sessions", tags=["training-sessions"])


@router.get("/{session_id}/exercises/{exercise_id}/sets", response_model=ExerciseSetsRead)
async def list_exercise_sets(
    session_id: uuid.UUID,
    exercise_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    sets = await SetCompletionService(session).list_sets(current_user, exercise_id, session_id)
    # At most one row is expected to carry a non-null feedback (see
    # SetCompletionService.save_feedback -- it always targets a single row),
    # but this stays a scan rather than assuming that invariant holds.
    feedback = next((set_completion.feedback for set_completion in sets if set_completion.feedback is not None), None)
    return ExerciseSetsRead(
        sets=[SetCompletionSummary.model_validate(set_completion) for set_completion in sets],
        feedback=feedback,
    )


@router.get("/{session_id}/diary", response_model=TrainingDiaryEntryRead | None)
async def get_diary_entry(
    session_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    entry = await TrainingDiaryService(session).get_entry(current_user, session_id)
    return TrainingDiaryEntryRead.model_validate(entry) if entry is not None else None


@router.put("/{session_id}/diary", response_model=TrainingDiaryEntryRead)
async def save_diary_entry(
    session_id: uuid.UUID,
    body: TrainingDiaryEntryIn,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    entry = await TrainingDiaryService(session).save_entry(
        user=current_user, training_session_id=session_id, note=body.note
    )
    return TrainingDiaryEntryRead.model_validate(entry)
