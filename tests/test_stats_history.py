"""ProgressService.get_stats_history: {date, value} points over a `days`
window, either for one stat_type (flat list) or every stat grouped by type
(dict) when stat_type is omitted. No history must come back as an empty
list, not an error -- callers (a fresh chart with nothing to plot yet)
shouldn't have to special-case a 4xx/5xx here.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.exercise import TargetStat
from app.models.progress import StatHistory
from app.models.user import User
from app.services.progress_service import ProgressService


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"statshist_{unique}",
        email=f"statshist_{unique}@example.com",
        password_hash="irrelevant",
    )


def _make_history(user_id: uuid.UUID, stat_type: TargetStat, value: float, recorded_at: datetime) -> StatHistory:
    return StatHistory(
        id=uuid.uuid4(),
        user_id=user_id,
        stat_type=stat_type,
        value=value,
        recorded_at=recorded_at,
        reason="test",
    )


@pytest.mark.asyncio
async def test_empty_history_returns_empty_list_not_error(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = ProgressService(db_session)
    result = await service.get_stats_history(user.id, TargetStat.STRENGTH, days=90)

    assert result == []


@pytest.mark.asyncio
async def test_days_filter_excludes_points_outside_the_window(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            _make_history(user.id, TargetStat.STRENGTH, 10.0, now - timedelta(days=120)),
            _make_history(user.id, TargetStat.STRENGTH, 20.0, now - timedelta(days=10)),
        ]
    )
    await db_session.flush()

    service = ProgressService(db_session)
    result = await service.get_stats_history(user.id, TargetStat.STRENGTH, days=30)

    assert len(result) == 1
    assert result[0].value == 20.0


@pytest.mark.asyncio
async def test_days_filter_widens_correctly(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            _make_history(user.id, TargetStat.STRENGTH, 10.0, now - timedelta(days=120)),
            _make_history(user.id, TargetStat.STRENGTH, 20.0, now - timedelta(days=10)),
        ]
    )
    await db_session.flush()

    service = ProgressService(db_session)
    result = await service.get_stats_history(user.id, TargetStat.STRENGTH, days=150)

    assert [point.value for point in result] == [10.0, 20.0]


@pytest.mark.asyncio
async def test_points_are_sorted_by_date(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    # Inserted out of order -- the repository query orders by recorded_at,
    # not insertion order.
    db_session.add_all(
        [
            _make_history(user.id, TargetStat.AGILITY, 30.0, now - timedelta(days=1)),
            _make_history(user.id, TargetStat.AGILITY, 10.0, now - timedelta(days=20)),
            _make_history(user.id, TargetStat.AGILITY, 20.0, now - timedelta(days=10)),
        ]
    )
    await db_session.flush()

    service = ProgressService(db_session)
    result = await service.get_stats_history(user.id, TargetStat.AGILITY, days=90)

    assert [point.value for point in result] == [10.0, 20.0, 30.0]


@pytest.mark.asyncio
async def test_without_stat_type_groups_every_stat_by_type(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    db_session.add(_make_history(user.id, TargetStat.ENDURANCE, 5.0, now))
    await db_session.flush()

    service = ProgressService(db_session)
    result = await service.get_stats_history(user.id, None, days=90)

    assert isinstance(result, dict)
    assert set(result.keys()) == set(TargetStat)
    assert [point.value for point in result[TargetStat.ENDURANCE]] == [5.0]
    # Every other stat has no history for this fresh user -- empty, not
    # missing/erroring.
    assert result[TargetStat.STRENGTH] == []
