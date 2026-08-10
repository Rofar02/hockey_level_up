"""User.has_seen_onboarding_tour: the one-time welcome-tour flag shown on
first Home visit after onboarding (see frontend HomePage/OnboardingTour).

Covers: defaults False for a new user; UserService.mark_onboarding_tour_seen
flips it to True and is idempotent on repeat calls (closing the tour twice,
e.g. a retried request, must not error); and the flag is actually persisted
(committed), not just held in the in-memory object -- a fresh read through
the repository, simulating the next time the user visits Home, must see it
too so the tour never shows a second time.
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
        username=f"tour_{unique}",
        email=f"tour_{unique}@example.com",
        password_hash="irrelevant",
    )


@pytest.mark.asyncio
async def test_new_user_has_not_seen_onboarding_tour_by_default(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    assert user.has_seen_onboarding_tour is False


@pytest.mark.asyncio
async def test_mark_onboarding_tour_seen_sets_flag_true(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    result = await UserService(db_session).mark_onboarding_tour_seen(user)

    assert result.has_seen_onboarding_tour is True


@pytest.mark.asyncio
async def test_mark_onboarding_tour_seen_is_idempotent(db_session) -> None:
    """Closing the tour by either "Начать" or "Пропустить" both call this --
    either could in principle fire twice (double-tap, retried request), and
    neither should error or behave differently the second time."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = UserService(db_session)
    first = await service.mark_onboarding_tour_seen(user)
    second = await service.mark_onboarding_tour_seen(user)

    assert first.has_seen_onboarding_tour is True
    assert second.has_seen_onboarding_tour is True


@pytest.mark.asyncio
async def test_flag_is_persisted_not_just_in_memory(db_session) -> None:
    """Simulates the real "does the tour show again on the next visit"
    check: mark seen, then read the user back through a completely separate
    repository call -- as HomePage's next mount effectively would -- rather
    than trusting the same in-memory `user` object mark_onboarding_tour_seen
    returned."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    user_id = user.id

    await UserService(db_session).mark_onboarding_tour_seen(user)

    refetched = await UserRepository(db_session).get_by_id(user_id)
    assert refetched is not None
    assert refetched.has_seen_onboarding_tour is True
