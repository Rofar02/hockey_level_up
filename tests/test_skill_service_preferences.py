"""UserSkillPreference replace/list round-trip (PUT/GET /users/me/skill-preferences),
including the User.level-scaled cap on how many can be selected at once
(see app/core/skill_preferences.py): level 1-7 -> 3, 8-14 -> 6, 15-24 -> 9,
25+ -> unlimited.
"""
import uuid

import pytest
from fastapi import HTTPException

from app.models.skill import Skill
from app.models.user import User
from app.services.skill_service import SkillService


def _make_user(*, level: int = 1) -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"user_{unique}",
        email=f"user_{unique}@example.com",
        password_hash="irrelevant",
        level=level,
    )


def _make_skills(count: int, *, required_level: int = 1) -> list[Skill]:
    return [
        Skill(id=uuid.uuid4(), name=f"Skill {i} {uuid.uuid4().hex[:8]}", required_level=required_level)
        for i in range(count)
    ]


@pytest.mark.asyncio
async def test_replace_is_full_replacement_and_dedupes(db_session) -> None:
    user = _make_user()
    skill_a = Skill(id=uuid.uuid4(), name=f"Skill A {uuid.uuid4().hex[:8]}")
    skill_b = Skill(id=uuid.uuid4(), name=f"Skill B {uuid.uuid4().hex[:8]}")
    db_session.add_all([user, skill_a, skill_b])
    await db_session.flush()

    service = SkillService(db_session)

    first = await service.replace_user_preferences(user, [skill_a.id, skill_a.id])
    assert {p.skill_id for p in first} == {skill_a.id}

    second = await service.replace_user_preferences(user, [skill_b.id])
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
        await service.replace_user_preferences(user, [uuid.uuid4()])
    assert exc_info.value.status_code == 404


# -- level-scaled selection cap --


@pytest.mark.asyncio
async def test_replace_rejects_more_than_the_level_cap(db_session) -> None:
    user = _make_user(level=1)  # cap = 3
    skills = _make_skills(4)
    db_session.add(user)
    db_session.add_all(skills)
    await db_session.flush()

    service = SkillService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.replace_user_preferences(user, [s.id for s in skills])

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Доступно не более 3 навыков на вашем уровне"

    # Rejected outright -- no partial write from the 4 submitted ids.
    assert await service.list_user_preferences(user.id) == []


@pytest.mark.asyncio
async def test_replace_succeeds_exactly_at_the_level_cap(db_session) -> None:
    user = _make_user(level=1)  # cap = 3
    skills = _make_skills(3)
    db_session.add(user)
    db_session.add_all(skills)
    await db_session.flush()

    service = SkillService(db_session)
    result = await service.replace_user_preferences(user, [s.id for s in skills])
    assert {p.skill_id for p in result} == {s.id for s in skills}


@pytest.mark.asyncio
async def test_replace_has_no_limit_at_level_25(db_session) -> None:
    user = _make_user(level=25)
    skills = _make_skills(12)  # well past every finite tier's cap
    db_session.add(user)
    db_session.add_all(skills)
    await db_session.flush()

    service = SkillService(db_session)
    result = await service.replace_user_preferences(user, [s.id for s in skills])
    assert {p.skill_id for p in result} == {s.id for s in skills}


@pytest.mark.asyncio
async def test_swap_one_skill_at_a_full_cap_succeeds(db_session) -> None:
    """Deselecting one and selecting a different one while already at the
    cap must work -- what's checked is the resulting set's size (still
    == cap), not whether the set changed."""
    user = _make_user(level=1)  # cap = 3
    skills = _make_skills(4)
    db_session.add(user)
    db_session.add_all(skills)
    await db_session.flush()

    service = SkillService(db_session)
    await service.replace_user_preferences(user, [s.id for s in skills[:3]])

    # Drop skills[0], keep [1] and [2], add [3] -- still exactly 3.
    swapped_ids = [skills[1].id, skills[2].id, skills[3].id]
    result = await service.replace_user_preferences(user, swapped_ids)
    assert {p.skill_id for p in result} == set(swapped_ids)


@pytest.mark.asyncio
async def test_boundary_levels_match_the_documented_tiers(db_session) -> None:
    # level 7 (just under the level-8 tier) -> cap 3; 8/14 -> 6; 15/24 -> 9.
    for level, cap in ((7, 3), (8, 6), (14, 6), (15, 9), (24, 9)):
        user = _make_user(level=level)
        skills = _make_skills(cap + 1)
        db_session.add(user)
        db_session.add_all(skills)
        await db_session.flush()

        service = SkillService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.replace_user_preferences(user, [s.id for s in skills])
        assert exc_info.value.status_code == 400

        ok = await service.replace_user_preferences(user, [s.id for s in skills[:cap]])
        assert len(ok) == cap


# -- required_level gate (independent of the slot-count cap above) --


@pytest.mark.asyncio
async def test_replace_rejects_a_skill_locked_by_required_level(db_session) -> None:
    user = _make_user(level=5)
    locked_skill = _make_skills(1, required_level=8)[0]
    db_session.add(user)
    db_session.add(locked_skill)
    await db_session.flush()

    service = SkillService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.replace_user_preferences(user, [locked_skill.id])

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == f"Навык '{locked_skill.name}' доступен с уровня 8"
    assert await service.list_user_preferences(user.id) == []


@pytest.mark.asyncio
async def test_replace_succeeds_once_user_reaches_the_required_level(db_session) -> None:
    """Levelling up unlocks the skill with no separate action needed -- the
    exact same PUT that failed before now succeeds untouched."""
    skill = _make_skills(1, required_level=8)[0]
    db_session.add(skill)
    await db_session.flush()

    service = SkillService(db_session)

    below = _make_user(level=7)
    db_session.add(below)
    await db_session.flush()
    with pytest.raises(HTTPException):
        await service.replace_user_preferences(below, [skill.id])

    at_required_level = _make_user(level=8)
    db_session.add(at_required_level)
    await db_session.flush()
    result = await service.replace_user_preferences(at_required_level, [skill.id])
    assert {p.skill_id for p in result} == {skill.id}


@pytest.mark.asyncio
async def test_slot_limit_and_level_gate_apply_independently(db_session) -> None:
    """Both checks run unconditionally on every submitted id: being within
    the slot cap doesn't excuse a level-locked skill, and every skill being
    unlocked doesn't excuse exceeding the slot cap."""
    user = _make_user(level=10)  # slot cap = 6 (8-14 tier)
    unlocked = _make_skills(3, required_level=1)
    locked = _make_skills(1, required_level=15)
    db_session.add(user)
    db_session.add_all(unlocked + locked)
    await db_session.flush()

    service = SkillService(db_session)

    # Within the slot cap (4 <= 6), but one skill is level-locked -> 400.
    with pytest.raises(HTTPException) as exc_info:
        await service.replace_user_preferences(
            user, [s.id for s in unlocked] + [locked[0].id]
        )
    assert exc_info.value.status_code == 400
    assert "доступен с уровня 15" in exc_info.value.detail

    # All unlocked, but the count (7) exceeds the slot cap (6) -> 400, the
    # distinct slot-limit message, even though none are level-gated.
    more_unlocked = _make_skills(7, required_level=1)
    db_session.add_all(more_unlocked)
    await db_session.flush()
    with pytest.raises(HTTPException) as exc_info:
        await service.replace_user_preferences(user, [s.id for s in more_unlocked])
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Доступно не более 6 навыков на вашем уровне"

    # Within the cap AND all unlocked -> succeeds.
    result = await service.replace_user_preferences(user, [s.id for s in unlocked])
    assert {p.skill_id for p in result} == {s.id for s in unlocked}
