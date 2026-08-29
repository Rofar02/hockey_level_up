"""User.has_seen_coach_personality_intro: the one-time explainer shown on
first /coach visit (2026-08-30 follow-up) -- coach_personality was
silently defaulted to CALM for every user with no explanation that it
also drives reminder/check-in notification wording, not just the AI chat.
Same idempotent "has_seen_X" shape as has_seen_onboarding_tour.
"""
import uuid

import pytest

from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.user_service import UserService


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"coachintro_{unique}",
        email=f"coachintro_{unique}@example.com",
        password_hash="irrelevant",
    )


@pytest.mark.asyncio
async def test_new_user_has_not_seen_coach_personality_intro_by_default(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    assert user.has_seen_coach_personality_intro is False


@pytest.mark.asyncio
async def test_mark_coach_personality_intro_seen_sets_flag_true(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    result = await UserService(db_session).mark_coach_personality_intro_seen(user)

    assert result.has_seen_coach_personality_intro is True


@pytest.mark.asyncio
async def test_mark_coach_personality_intro_seen_is_idempotent(db_session) -> None:
    """Both picking a personality and dismissing the intro call this --
    either could fire twice (double-tap, retried request), and neither
    should error or behave differently the second time."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = UserService(db_session)
    first = await service.mark_coach_personality_intro_seen(user)
    second = await service.mark_coach_personality_intro_seen(user)

    assert first.has_seen_coach_personality_intro is True
    assert second.has_seen_coach_personality_intro is True


@pytest.mark.asyncio
async def test_flag_is_persisted_not_just_in_memory(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    user_id = user.id

    await UserService(db_session).mark_coach_personality_intro_seen(user)

    refetched = await UserRepository(db_session).get_by_id(user_id)
    assert refetched is not None
    assert refetched.has_seen_coach_personality_intro is True


@pytest.mark.asyncio
async def test_picking_a_personality_via_update_profile_does_not_itself_mark_intro_seen(
    db_session,
) -> None:
    """update_profile (Settings' own picker) and mark_coach_personality_intro_seen
    (the /coach intro) are deliberately separate actions -- CoachPage calls
    both together when a player picks from the intro modal, but a plain
    Settings edit alone must not silently mark the intro as seen for a
    player who has never actually opened /coach."""
    from app.models.user import CoachPersonality
    from app.schemas.user import UserUpdate

    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    await UserService(db_session).update_profile(user, UserUpdate(coach_personality=CoachPersonality.HUMOR))

    assert user.coach_personality == CoachPersonality.HUMOR
    assert user.has_seen_coach_personality_intro is False
