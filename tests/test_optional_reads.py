"""?optional=1 on the "nothing yet" reads (15.10): 200 + null for a player
without a week / block / day, the old 404 without the flag."""
import uuid

import httpx
import pytest

from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.user import User

PATHS = [
    "/schedule/weekly/current",
    "/schedule/weekly?week_start_date=2030-03-04",
    "/schedule/day-plan?date=2030-03-04",
    "/training-block/current",
]


@pytest.mark.asyncio
async def test_nothing_yet_is_null_with_the_flag_and_404_without(db_session):
    unique = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), username=f"opt_{unique}", email=f"opt_{unique}@example.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()

    async def _db():
        yield db_session

    app.dependency_overrides[get_db] = _db
    try:
        headers = {"Authorization": f"Bearer {create_access_token(str(user.id))}"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            for path in PATHS:
                separator = "&" if "?" in path else "?"
                with_flag = await client.get(f"{path}{separator}optional=1", headers=headers)
                without = await client.get(path, headers=headers)
                assert (path, with_flag.status_code, with_flag.json()) == (path, 200, None)
                assert (path, without.status_code) == (path, 404)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_leaderboard_me_without_birth_date(db_session):
    """No birth date: with the flag 200, no rank and the hint; the old 400
    without it."""
    unique = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), username=f"opt_{unique}", email=f"opt_{unique}@example.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()

    async def _db():
        yield db_session

    app.dependency_overrides[get_db] = _db
    try:
        headers = {"Authorization": f"Bearer {create_access_token(str(user.id))}"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            with_flag = await client.get("/leaderboard/me?optional=1", headers=headers)
            without = await client.get("/leaderboard/me", headers=headers)
        assert with_flag.status_code == 200
        body = with_flag.json()
        assert body["rank"] is None and body["rating_excess"] is None
        assert "дату рождения" in body["hint"]
        assert without.status_code == 400
    finally:
        app.dependency_overrides.pop(get_db, None)
