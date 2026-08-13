import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.exercise import ExerciseRead
from app.schemas.training_party import (
    TrainingPartyCreate,
    TrainingPartyDetailRead,
    TrainingPartyExercisesConfirm,
    TrainingPartyInviteRead,
    TrainingPartySummaryRead,
)
from app.services.training_party_service import DEFAULT_SUGGESTION_COUNT, TrainingPartyService

router = APIRouter(prefix="/training-parties", tags=["training-parties"])


@router.post("", response_model=TrainingPartyDetailRead)
async def create_training_party(
    body: TrainingPartyCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TrainingPartyService(session).create_party(current_user, body)


@router.get("/me", response_model=list[TrainingPartySummaryRead])
async def list_my_training_parties(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Must stay registered *before* GET /{party_id} below -- same "/me"-style
    landmine documented in routers/teams.py."""
    return await TrainingPartyService(session).list_my_parties(current_user)


@router.get("/invites", response_model=list[TrainingPartyInviteRead])
async def list_incoming_training_party_invites(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Same route-ordering note as /me above."""
    return await TrainingPartyService(session).list_incoming_invites(current_user)


@router.get("/{party_id}", response_model=TrainingPartyDetailRead)
async def get_training_party(
    party_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TrainingPartyService(session).get_party(current_user, party_id)


@router.delete("/{party_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_training_party(
    party_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Creator-only (TrainingPartyService.cancel_party 403s otherwise)."""
    await TrainingPartyService(session).cancel_party(current_user, party_id)


@router.post("/{party_id}/accept", response_model=TrainingPartyDetailRead)
async def accept_training_party_invite(
    party_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TrainingPartyService(session).respond_to_invite(current_user, party_id, accept=True)


@router.post("/{party_id}/decline", response_model=TrainingPartyDetailRead)
async def decline_training_party_invite(
    party_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await TrainingPartyService(session).respond_to_invite(current_user, party_id, accept=False)


@router.post("/{party_id}/exercises/suggest", response_model=list[ExerciseRead])
async def suggest_training_party_exercises(
    party_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    count: Annotated[int, Query(ge=1, le=12)] = DEFAULT_SUGGESTION_COUNT,
):
    """Creator-only, never persists anything -- both "Сгенерировать" and the
    recommended-highlighting in "Собрать самому" call this; re-calling it is
    exactly "перемешать"."""
    return await TrainingPartyService(session).suggest_exercises(current_user, party_id, count)


@router.post("/{party_id}/exercises/confirm", response_model=TrainingPartyDetailRead)
async def confirm_training_party_exercises(
    party_id: uuid.UUID,
    body: TrainingPartyExercisesConfirm,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Creator-only. Materializes body.exercise_ids as every joined member's
    TrainingSession for the party's target_date -- same list regardless of
    whether it came from /suggest untouched or was hand-assembled."""
    return await TrainingPartyService(session).confirm_exercises(
        current_user, party_id, body.exercise_ids
    )


@router.delete("/{party_id}/members/me", status_code=status.HTTP_204_NO_CONTENT)
async def leave_training_party(
    party_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Creator can't leave -- must cancel instead (TrainingPartyService.leave_party 409s)."""
    await TrainingPartyService(session).leave_party(current_user, party_id)
