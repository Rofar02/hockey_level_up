from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.routers.deps import get_current_user
from app.schemas.auth import RefreshRequest, TokenPair
from app.schemas.user import UserCreate, UserRead
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, session: Annotated[AsyncSession, Depends(get_db)]):
    return await AuthService(session).register(user_in)


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
