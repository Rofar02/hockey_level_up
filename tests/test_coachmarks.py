"""CoachmarkService/CoachmarkRepository: the reusable first-touch tour
overlay's per-user "seen" state (2026-08-30 discoverability pass), backing
frontend/src/hooks/useCoachmarkStep.ts. One row per (user, hint_id) so a
step stays dismissed across devices -- see UserCoachmark's own docstring for
why this replaced an earlier localStorage-only version.
"""
import uuid

import pytest

from app.models.user import User
from app.services.coachmark_service import CoachmarkService


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"coachmark_{unique}",
        email=f"coachmark_{unique}@example.com",
        password_hash="irrelevant",
    )


@pytest.mark.asyncio
async def test_new_user_has_seen_no_coachmarks(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    seen = await CoachmarkService(db_session).list_seen(user.id)

    assert seen == []


@pytest.mark.asyncio
async def test_mark_seen_adds_the_hint(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    seen = await CoachmarkService(db_session).mark_seen(user.id, "home-skill-milestones")

    assert seen == ["home-skill-milestones"]


@pytest.mark.asyncio
async def test_mark_seen_is_idempotent(db_session) -> None:
    """A double-tap on the "Далее" button, or two tabs open, must not error
    or duplicate the row (the unique constraint would reject a plain
    insert)."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = CoachmarkService(db_session)
    first = await service.mark_seen(user.id, "home-skill-milestones")
    second = await service.mark_seen(user.id, "home-skill-milestones")

    assert first == ["home-skill-milestones"]
    assert second == ["home-skill-milestones"]


@pytest.mark.asyncio
async def test_multiple_hints_for_the_same_user_accumulate(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = CoachmarkService(db_session)
    await service.mark_seen(user.id, "home-skill-milestones")
    seen = await service.mark_seen(user.id, "schedule-week-day-tap")

    assert set(seen) == {"home-skill-milestones", "schedule-week-day-tap"}


@pytest.mark.asyncio
async def test_seen_hints_are_scoped_per_user(db_session) -> None:
    user_a = _make_user()
    user_b = _make_user()
    db_session.add_all([user_a, user_b])
    await db_session.flush()

    service = CoachmarkService(db_session)
    await service.mark_seen(user_a.id, "home-skill-milestones")

    assert await service.list_seen(user_b.id) == []


@pytest.mark.asyncio
async def test_mark_seen_is_persisted_not_just_in_memory(db_session) -> None:
    """Simulates the same user reopening the app on a different device: read
    back through a fresh service instance rather than trusting the return
    value of the call that just wrote it."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    user_id = user.id

    await CoachmarkService(db_session).mark_seen(user_id, "home-skill-milestones")

    seen = await CoachmarkService(db_session).list_seen(user_id)
    assert seen == ["home-skill-milestones"]
