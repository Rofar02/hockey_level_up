from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.auth import (
    DetailResponse,
    EmailAvailabilityRead,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    TokenPair,
)
from app.schemas.user import UserCreate, UserRead
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

# Always the exact same body, whether or not the email is actually
# registered -- POST /password-reset/request must not let a caller
# enumerate accounts by comparing responses (see AuthService.request_password_reset).
_PASSWORD_RESET_REQUESTED_DETAIL = "Если такой email зарегистрирован, на него отправлено письмо"


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, session: Annotated[AsyncSession, Depends(get_db)]):
    return await AuthService(session).register(user_in)


@router.get("/email-availability", response_model=EmailAvailabilityRead)
async def email_availability(email: EmailStr, session: Annotated[AsyncSession, Depends(get_db)]):
    """Public -- registration step 1 needs this before the athlete fills in
    the rest of the wizard, see AuthService.is_email_available."""
    available = await AuthService(session).is_email_available(email)
    return EmailAvailabilityRead(available=available)


@router.post("/login", response_model=TokenPair)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await AuthService(session).login(form_data.username, form_data.password)


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, session: Annotated[AsyncSession, Depends(get_db)]):
    return await AuthService(session).refresh(body.refresh_token)


@router.get("/me", response_model=UserRead)
async def read_current_user(current_user: Annotated[UserRead, Depends(get_current_user)]):
    return current_user


@router.post("/verify-email/resend", response_model=DetailResponse)
async def resend_verification_email(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """Authenticated -- resending only makes sense for whoever's asking, no
    email-enumeration concern here (unlike password-reset/request) since the
    caller already proved they own this account via their access token."""
    await AuthService(session).resend_verification_email(current_user)
    return DetailResponse(detail="Письмо с подтверждением отправлено")


@router.get("/verify-email/confirm", response_model=DetailResponse)
async def confirm_verify_email(token: str, session: Annotated[AsyncSession, Depends(get_db)]):
    """Public (a link clicked from an email, not necessarily from a logged-in
    browser) -- consume_token itself is what actually validates `token`."""
    await AuthService(session).confirm_email_verification(token)
    return DetailResponse(detail="Email подтверждён")


@router.post("/password-reset/request", response_model=DetailResponse)
async def request_password_reset(
    body: PasswordResetRequest, session: Annotated[AsyncSession, Depends(get_db)]
):
    """Public. Always the same response body regardless of whether `email`
    belongs to an account -- see AuthService.request_password_reset."""
    await AuthService(session).request_password_reset(body.email)
    return DetailResponse(detail=_PASSWORD_RESET_REQUESTED_DETAIL)


@router.post("/password-reset/confirm", response_model=DetailResponse)
async def confirm_password_reset(
    body: PasswordResetConfirm, session: Annotated[AsyncSession, Depends(get_db)]
):
    await AuthService(session).confirm_password_reset(body.token, body.new_password)
    return DetailResponse(detail="Пароль обновлён")
