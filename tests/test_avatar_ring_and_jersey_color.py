"""Level-gated cosmetics (item 6, 2026-08-30 gamification pass):
avatar_ring_accent (unlocks at app.core.level_unlocks.LEVEL_AVATAR_RING_CHOICE,
10) and jersey_color (unlocks at LEVEL_JERSEY_COLOR_CHOICE, 15), both set via
the generic PATCH /users/me -> UserService.update_profile path, same as
has_seen_weight_hint. Covers: rejected below the level, accepted at/above
it, resetting to null is never gated, and the two fields don't interfere
with each other.
"""
import uuid

import pytest
from fastapi import HTTPException

from app.models.user import AvatarRingAccent, JerseyColor, User
from app.schemas.user import UserUpdate
from app.services.user_service import UserService


def _make_user(*, level: int = 1) -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"cosmetics_{unique}",
        email=f"cosmetics_{unique}@example.com",
        password_hash="irrelevant",
        level=level,
    )


@pytest.mark.asyncio
async def test_avatar_ring_choice_rejected_below_level_10(db_session) -> None:
    user = _make_user(level=9)
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await UserService(db_session).update_profile(
            user, UserUpdate(avatar_ring_accent=AvatarRingAccent.PERSIMMON)
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_avatar_ring_choice_accepted_at_level_10(db_session) -> None:
    user = _make_user(level=10)
    db_session.add(user)
    await db_session.flush()

    result = await UserService(db_session).update_profile(
        user, UserUpdate(avatar_ring_accent=AvatarRingAccent.MIX)
    )
    assert result.avatar_ring_accent == AvatarRingAccent.MIX


@pytest.mark.asyncio
async def test_jersey_color_rejected_below_level_15(db_session) -> None:
    user = _make_user(level=14)
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await UserService(db_session).update_profile(
            user, UserUpdate(jersey_color=JerseyColor.GOLD)
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_jersey_color_accepted_at_level_15(db_session) -> None:
    user = _make_user(level=15)
    db_session.add(user)
    await db_session.flush()

    result = await UserService(db_session).update_profile(
        user, UserUpdate(jersey_color=JerseyColor.GOLD)
    )
    assert result.jersey_color == JerseyColor.GOLD


@pytest.mark.asyncio
async def test_resetting_to_null_is_never_gated(db_session) -> None:
    """A level-1 account can't set a real value, but must still be able to
    clear one back to null (e.g. rolling back a choice made before a
    since-reverted level, or just future-proofing against level changes)."""
    user = _make_user(level=1)
    db_session.add(user)
    await db_session.flush()

    result = await UserService(db_session).update_profile(
        user, UserUpdate(avatar_ring_accent=None, jersey_color=None)
    )
    assert result.avatar_ring_accent is None
    assert result.jersey_color is None


@pytest.mark.asyncio
async def test_the_two_cosmetic_fields_are_independent(db_session) -> None:
    """A level-12 account can set avatar_ring_accent (unlocked at 10) but
    not jersey_color (needs 15) -- one being allowed doesn't waive the
    other's own gate."""
    user = _make_user(level=12)
    db_session.add(user)
    await db_session.flush()

    service = UserService(db_session)
    result = await service.update_profile(user, UserUpdate(avatar_ring_accent=AvatarRingAccent.ICE))
    assert result.avatar_ring_accent == AvatarRingAccent.ICE

    with pytest.raises(HTTPException):
        await service.update_profile(user, UserUpdate(jersey_color=JerseyColor.WHITE))
