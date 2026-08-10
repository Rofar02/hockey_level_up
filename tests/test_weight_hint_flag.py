"""User.has_seen_weight_hint: the one-time SetLogger hint (suggested weight
+ feedback) shown on first real encounter with that UI, not the general
onboarding tour (see frontend ExerciseDetailModal's SetLogger).

Unlike has_seen_onboarding_tour (its own dedicated endpoint), this reuses
the generic PATCH /users/me -> UserService.update_profile path, since it's
just one more simple field UserUpdate already knows how to set. Covers:
defaults False for a new user; update_profile flips it to True; is
idempotent (re-sending True is a no-op, not an error); and the flag is
actually committed, not just held on the in-memory object -- a fresh read
through the repository, simulating opening SetLogger on a different
exercise in a later session, must see it too.
"""
import uuid

import pytest

from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserUpdate
from app.services.user_service import UserService


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"weighthint_{unique}",
        email=f"weighthint_{unique}@example.com",
        password_hash="irrelevant",
    )


@pytest.mark.asyncio
async def test_new_user_has_not_seen_weight_hint_by_default(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    assert user.has_seen_weight_hint is False


@pytest.mark.asyncio
async def test_update_profile_sets_weight_hint_flag_true(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    result = await UserService(db_session).update_profile(
        user, UserUpdate(has_seen_weight_hint=True)
    )

    assert result.has_seen_weight_hint is True


@pytest.mark.asyncio
async def test_update_profile_weight_hint_is_idempotent(db_session) -> None:
    """Both "Понятно" on this hint and closing it some other way (if ever
    added) would call the same PATCH -- re-sending True must never error or
    behave differently the second time."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = UserService(db_session)
    first = await service.update_profile(user, UserUpdate(has_seen_weight_hint=True))
    second = await service.update_profile(user, UserUpdate(has_seen_weight_hint=True))

    assert first.has_seen_weight_hint is True
    assert second.has_seen_weight_hint is True


@pytest.mark.asyncio
async def test_update_profile_does_not_touch_weight_hint_when_field_omitted(db_session) -> None:
    """UserUpdate's other callers (e.g. changing reminder_preference from
    Settings) must never accidentally reset this flag back to False just by
    not mentioning it -- exclude_unset is what guarantees that."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = UserService(db_session)
    await service.update_profile(user, UserUpdate(has_seen_weight_hint=True))
    result = await service.update_profile(user, UserUpdate(first_name="Nikita"))

    assert result.first_name == "Nikita"
    assert result.has_seen_weight_hint is True


@pytest.mark.asyncio
async def test_weight_hint_flag_is_persisted_not_just_in_memory(db_session) -> None:
    """Simulates opening SetLogger on a different exercise in a later
    session: read the user back through a completely separate repository
    call rather than trusting the same in-memory `user` object
    update_profile returned."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    user_id = user.id

    await UserService(db_session).update_profile(user, UserUpdate(has_seen_weight_hint=True))

    refetched = await UserRepository(db_session).get_by_id(user_id)
    assert refetched is not None
    assert refetched.has_seen_weight_hint is True
