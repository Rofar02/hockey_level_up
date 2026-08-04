from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.set_completion import SetCompletionCreate, SetCompletionRead, SetFeedbackIn
from app.services.set_completion_service import SetCompletionService

router = APIRouter(prefix="/set-completions", tags=["set-completions"])


@router.post("", response_model=SetCompletionRead, status_code=status.HTTP_201_CREATED)
async def save_set(
    body: SetCompletionCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await SetCompletionService(session).save_set(
        user=current_user,
        exercise_id=body.exercise_id,
        training_session_id=body.training_session_id,
        set_number=body.set_number,
        weight_kg=body.weight_kg,
        reps_completed=body.reps_completed,
        duration_seconds_completed=body.duration_seconds_completed,
    )


@router.post("/feedback", response_model=SetCompletionRead)
async def save_feedback(
    body: SetFeedbackIn,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await SetCompletionService(session).save_feedback(
        user=current_user,
        exercise_id=body.exercise_id,
        training_session_id=body.training_session_id,
        feedback=body.feedback,
    )
