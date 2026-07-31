"""UserSkillPreference replace/list round-trip (PUT/GET /users/me/skill-preferences)."""
import uuid

import pytest
from fastapi import HTTPException

from app.models.skill import Skill
from app.models.user import User
from app.services.skill_service import SkillService


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"user_{unique}",
        email=f"user_{unique}@example.com",
        password_hash="irrelevant",
    )


@pytest.mark.asyncio
async def test_replace_is_full_replacement_and_dedupes(db_session) -> None:
    user = _make_user()
    skill_a = Skill(id=uuid.uuid4(), name=f"Skill A {uuid.uuid4().hex[:8]}")
    skill_b = Skill(id=uuid.uuid4(), name=f"Skill B {uuid.uuid4().hex[:8]}")
    db_session.add_all([user, skill_a, skill_b])
    await db_session.flush()

    service = SkillService(db_session)

    first = await service.replace_user_preferences(user.id, [skill_a.id, skill_a.id])
    assert {p.skill_id for p in first} == {skill_a.id}

    second = await service.replace_user_preferences(user.id, [skill_b.id])
    assert {p.skill_id for p in second} == {skill_b.id}

    listed = await service.list_user_preferences(user.id)
    assert {p.skill_id for p in listed} == {skill_b.id}
    assert listed[0].name == skill_b.name


@pytest.mark.asyncio
async def test_replace_rejects_unknown_skill_id(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = SkillService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.replace_user_preferences(user.id, [uuid.uuid4()])
    assert exc_info.value.status_code == 404
