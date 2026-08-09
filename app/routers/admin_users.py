import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.routers.deps import require_admin
from app.schemas.user import UserAdminRead, UserAdminUpdate
from app.services.user_service import UserService

router = APIRouter(prefix="/admin/users", tags=["admin"])


@router.get("", response_model=list[UserAdminRead])
async def list_users_admin(
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    q: str | None = Query(default=None, description="Search by email, first or last name"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return await UserService(session).list_users_admin(search=q, limit=limit, offset=offset)


@router.patch("/{user_id}", response_model=UserAdminRead)
async def update_user_admin(
    user_id: uuid.UUID,
    body: UserAdminUpdate,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    return await UserService(session).update_user_admin(user_id, body)
