from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.assessment import (
    AssessmentResultRead,
    AssessmentStatusRead,
    AssessmentTestIn,
    OnIceAssessmentResultRead,
    OnIceAssessmentStatusRead,
    OnIceAssessmentTestIn,
)
from app.services.assessment_service import AssessmentService

router = APIRouter(prefix="/assessment", tags=["assessment"])


@router.post("/test", response_model=AssessmentResultRead)
async def run_fitness_test(
    body: AssessmentTestIn,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await AssessmentService(session).run_test(current_user, body)


@router.post("/start-from-scratch", response_model=AssessmentResultRead)
async def start_from_scratch(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await AssessmentService(session).start_from_scratch(current_user)


@router.get("/status", response_model=AssessmentStatusRead)
async def get_assessment_status(current_user: Annotated[User, Depends(get_current_user)]):
    return AssessmentStatusRead(
        has_assessment=current_user.has_assessment,
        suggested_reassessment=current_user.suggested_reassessment,
    )


@router.post("/dismiss-reassessment-suggestion", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_reassessment_suggestion(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    await AssessmentService(session).dismiss_reassessment_suggestion(current_user)


@router.post("/on-ice-test", response_model=OnIceAssessmentResultRead)
async def run_onice_test(
    body: OnIceAssessmentTestIn,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await AssessmentService(session).run_onice_test(current_user, body)


@router.get("/on-ice-status", response_model=OnIceAssessmentStatusRead)
async def get_onice_assessment_status(current_user: Annotated[User, Depends(get_current_user)]):
    return OnIceAssessmentStatusRead(
        has_onice_assessment=current_user.has_onice_assessment,
        suggested_onice_reassessment=current_user.suggested_onice_reassessment,
    )
