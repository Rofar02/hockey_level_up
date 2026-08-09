"""Admin user management: list pagination/search, and the guard that stops
an admin from demoting the last remaining is_admin=True account.

Runs against the same shared dev database as every other test here (see
conftest.py) -- which already has real admin accounts in it, so the
last-admin tests neutralize every *other* admin for the duration of the
test (rolled back at teardown along with everything else) rather than
assuming the table starts empty.
"""
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.user import User
from app.schemas.user import UserAdminUpdate
from app.services.user_service import UserService


def _make_user(
    *,
    email: str | None = None,
    first_name: str = "Test",
    last_name: str = "User",
    is_admin: bool = False,
) -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"adminlist_{unique}",
        email=email or f"adminlist_{unique}@example.com",
        password_hash="irrelevant",
        first_name=first_name,
        last_name=last_name,
        is_admin=is_admin,
    )


# -- list_users_admin: pagination --


@pytest.mark.asyncio
async def test_list_users_admin_paginates(db_session) -> None:
    run_id = uuid.uuid4().hex[:8]
    users = [_make_user(email=f"page_{run_id}_{i}@example.com") for i in range(5)]
    db_session.add_all(users)
    await db_session.flush()

    service = UserService(db_session)
    search = f"page_{run_id}"
    page1 = await service.list_users_admin(search=search, limit=2, offset=0)
    page2 = await service.list_users_admin(search=search, limit=2, offset=2)
    page3 = await service.list_users_admin(search=search, limit=2, offset=4)

    assert len(page1) == 2
    assert len(page2) == 2
    assert len(page3) == 1
    seen_ids = {u.id for u in page1} | {u.id for u in page2} | {u.id for u in page3}
    assert seen_ids == {u.id for u in users}


# -- list_users_admin: search --


@pytest.mark.asyncio
async def test_list_users_admin_search_matches_name(db_session) -> None:
    unique = uuid.uuid4().hex[:8]
    target = _make_user(first_name=f"Zzyzx{unique}", last_name="Distinctive")
    other = _make_user()
    db_session.add_all([target, other])
    await db_session.flush()

    service = UserService(db_session)
    results = await service.list_users_admin(search=f"zzyzx{unique}", limit=50, offset=0)

    assert [u.id for u in results] == [target.id]


@pytest.mark.asyncio
async def test_list_users_admin_search_matches_email(db_session) -> None:
    unique = uuid.uuid4().hex[:8]
    target = _make_user(email=f"findme_{unique}@example.com")
    other = _make_user()
    db_session.add_all([target, other])
    await db_session.flush()

    service = UserService(db_session)
    results = await service.list_users_admin(search=f"findme_{unique}", limit=50, offset=0)

    assert [u.id for u in results] == [target.id]


# -- update_user_admin: last-admin guard --


@pytest.mark.asyncio
async def test_update_user_admin_blocks_removing_last_admin(db_session) -> None:
    other_admins = list(
        (await db_session.execute(select(User).where(User.is_admin.is_(True)))).scalars()
    )
    for other in other_admins:
        other.is_admin = False
    await db_session.flush()

    admin = _make_user(is_admin=True)
    db_session.add(admin)
    await db_session.flush()

    service = UserService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.update_user_admin(admin.id, UserAdminUpdate(is_admin=False))

    assert exc_info.value.status_code == 400
    await db_session.refresh(admin)
    assert admin.is_admin is True


@pytest.mark.asyncio
async def test_update_user_admin_allows_demoting_when_another_admin_remains(db_session) -> None:
    admin_a = _make_user(is_admin=True)
    admin_b = _make_user(is_admin=True)
    db_session.add_all([admin_a, admin_b])
    await db_session.flush()

    service = UserService(db_session)
    updated = await service.update_user_admin(admin_a.id, UserAdminUpdate(is_admin=False))

    assert updated.is_admin is False


@pytest.mark.asyncio
async def test_update_user_admin_allows_promoting_to_admin(db_session) -> None:
    user = _make_user(is_admin=False)
    db_session.add(user)
    await db_session.flush()

    service = UserService(db_session)
    updated = await service.update_user_admin(user.id, UserAdminUpdate(is_admin=True))

    assert updated.is_admin is True


@pytest.mark.asyncio
async def test_update_user_admin_missing_user_returns_404(db_session) -> None:
    service = UserService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.update_user_admin(uuid.uuid4(), UserAdminUpdate(is_admin=True))

    assert exc_info.value.status_code == 404
