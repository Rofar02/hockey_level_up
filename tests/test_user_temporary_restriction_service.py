"""UserTemporaryRestrictionService: a player-reported "this hurts right
now" flag (P3 item #7, manual-report-only first pass; extended 2026-08-27
with muscle_group alongside the original movement_pattern). Covers
report/list/lift, the upsert-extend-on-repeat-report behavior, and the
exactly-one-target validation.
"""
import uuid
from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from app.models.exercise import MovementPattern, MuscleGroup
from app.models.user import User
from app.models.user_temporary_restriction import UserTemporaryRestriction
from app.services.user_temporary_restriction_service import (
    DEFAULT_RESTRICTION_DAYS,
    UserTemporaryRestrictionService,
)


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"restrict_{unique}",
        email=f"restrict_{unique}@example.com",
        password_hash="irrelevant",
    )


@pytest.mark.asyncio
async def test_report_creates_a_restriction_expiring_in_default_days(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = UserTemporaryRestrictionService(db_session)
    restriction = await service.report(user, MovementPattern.SQUAT, None, "колено болит")

    assert restriction.movement_pattern == MovementPattern.SQUAT
    assert restriction.muscle_group is None
    assert restriction.reason == "колено болит"
    assert restriction.expires_at == date.today() + timedelta(days=DEFAULT_RESTRICTION_DAYS)
    assert restriction.lifted_at is None


@pytest.mark.asyncio
async def test_report_by_muscle_group_creates_a_restriction(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = UserTemporaryRestrictionService(db_session)
    restriction = await service.report(user, None, MuscleGroup.QUADS, "колено болит")

    assert restriction.movement_pattern is None
    assert restriction.muscle_group == MuscleGroup.QUADS
    assert restriction.reason == "колено болит"


@pytest.mark.asyncio
async def test_report_rejects_neither_target(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = UserTemporaryRestrictionService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.report(user, None, None, None)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_report_rejects_both_targets(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = UserTemporaryRestrictionService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.report(user, MovementPattern.SQUAT, MuscleGroup.QUADS, None)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_list_active_returns_what_was_reported(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = UserTemporaryRestrictionService(db_session)
    await service.report(user, MovementPattern.SQUAT, None, "колено болит")

    active = await service.list_active(user)

    assert [r.movement_pattern for r in active] == [MovementPattern.SQUAT]


@pytest.mark.asyncio
async def test_reporting_same_pattern_again_extends_instead_of_duplicating(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = UserTemporaryRestrictionService(db_session)
    first = await service.report(user, MovementPattern.SQUAT, None, "немного тянет")
    second = await service.report(user, MovementPattern.SQUAT, None, "болит сильнее")

    assert second.id == first.id
    assert second.reason == "болит сильнее"

    active = await service.list_active(user)
    assert len(active) == 1


@pytest.mark.asyncio
async def test_reporting_same_muscle_group_again_extends_instead_of_duplicating(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = UserTemporaryRestrictionService(db_session)
    first = await service.report(user, None, MuscleGroup.QUADS, "немного тянет")
    second = await service.report(user, None, MuscleGroup.QUADS, "болит сильнее")

    assert second.id == first.id
    assert second.reason == "болит сильнее"

    active = await service.list_active(user)
    assert len(active) == 1


@pytest.mark.asyncio
async def test_lift_removes_a_restriction_from_the_active_list(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = UserTemporaryRestrictionService(db_session)
    restriction = await service.report(user, MovementPattern.SQUAT, None, None)

    await service.lift(user, restriction.id)

    assert await service.list_active(user) == []


@pytest.mark.asyncio
async def test_lift_is_idempotent(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = UserTemporaryRestrictionService(db_session)
    restriction = await service.report(user, MovementPattern.SQUAT, None, None)

    await service.lift(user, restriction.id)
    await service.lift(user, restriction.id)  # must not raise

    assert await service.list_active(user) == []


@pytest.mark.asyncio
async def test_lift_rejects_someone_elses_restriction(db_session) -> None:
    owner = _make_user()
    stranger = _make_user()
    db_session.add_all([owner, stranger])
    await db_session.flush()

    service = UserTemporaryRestrictionService(db_session)
    restriction = await service.report(owner, MovementPattern.SQUAT, None, None)

    with pytest.raises(HTTPException) as exc_info:
        await service.lift(stranger, restriction.id)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_lift_rejects_unknown_restriction(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = UserTemporaryRestrictionService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.lift(user, uuid.uuid4())
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_list_active_excludes_expired_restrictions(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    expired = UserTemporaryRestriction(
        user_id=user.id,
        movement_pattern=MovementPattern.SQUAT,
        expires_at=date.today() - timedelta(days=1),
    )
    db_session.add(expired)
    await db_session.flush()

    service = UserTemporaryRestrictionService(db_session)
    assert await service.list_active(user) == []
