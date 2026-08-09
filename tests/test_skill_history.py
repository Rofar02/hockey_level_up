"""SkillService's on-the-fly skill-value history: skill value is never
persisted (see get_skill_value), so get_skill_history/get_all_skills_history
replay Σ weight * get_effective_value against each weighted stat's real
StatHistory rows instead of reading a stored series back. Covers: empty
history -> empty list (not an error), the `days` window, decay actually
being applied when a later event outlives an earlier stat's grace period,
and that grouping by skill_id in get_all_skills_history doesn't mix up
which stat feeds which skill.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.exercise import TargetStat
from app.models.progress import StatHistory, UserStat
from app.models.skill import Skill, SkillStatWeight
from app.models.user import User
from app.services.skill_service import SkillService
from app.services.stat_service import get_effective_value


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"skillhist_{unique}",
        email=f"skillhist_{unique}@example.com",
        password_hash="irrelevant",
    )


def _make_skill(*, name: str | None = None) -> Skill:
    unique = uuid.uuid4().hex[:8]
    return Skill(id=uuid.uuid4(), name=name or f"Skill {unique}")


def _make_weight(skill_id: uuid.UUID, stat_type: TargetStat, weight: float) -> SkillStatWeight:
    return SkillStatWeight(id=uuid.uuid4(), skill_id=skill_id, stat_type=stat_type, weight=weight)


def _make_history(
    user_id: uuid.UUID, stat_type: TargetStat, value: float, recorded_at: datetime
) -> StatHistory:
    return StatHistory(
        id=uuid.uuid4(),
        user_id=user_id,
        stat_type=stat_type,
        value=value,
        recorded_at=recorded_at,
        reason="test",
    )


@pytest.mark.asyncio
async def test_skill_history_empty_returns_empty_list_not_error(db_session) -> None:
    user = _make_user()
    skill = _make_skill()
    db_session.add_all([user, skill, _make_weight(skill.id, TargetStat.STRENGTH, 1.0)])
    await db_session.flush()

    service = SkillService(db_session)
    result = await service.get_skill_history(skill.id, user.id, days=90)

    assert result == []


@pytest.mark.asyncio
async def test_skill_history_no_weights_returns_empty_list(db_session) -> None:
    user = _make_user()
    skill = _make_skill()
    db_session.add_all([user, skill])
    await db_session.flush()

    service = SkillService(db_session)
    result = await service.get_skill_history(skill.id, user.id, days=90)

    assert result == []


@pytest.mark.asyncio
async def test_skill_history_unknown_skill_raises_404(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = SkillService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.get_skill_history(uuid.uuid4(), user.id, days=90)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_skill_history_filters_by_days(db_session) -> None:
    user = _make_user()
    skill = _make_skill()
    db_session.add_all([user, skill, _make_weight(skill.id, TargetStat.STRENGTH, 1.0)])
    await db_session.flush()

    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            _make_history(user.id, TargetStat.STRENGTH, 10.0, now - timedelta(days=120)),
            _make_history(user.id, TargetStat.STRENGTH, 20.0, now - timedelta(days=10)),
        ]
    )
    await db_session.flush()

    service = SkillService(db_session)
    result = await service.get_skill_history(skill.id, user.id, days=30)

    # Only the in-window event becomes its own point -- the older row still
    # exists (it's what a wider window would have picked up as the seed
    # value), it just doesn't get plotted here since 120 days ago isn't in
    # a 30-day window and there's no earlier stat to decay from within it.
    assert len(result) == 1
    assert result[0].value == pytest.approx(20.0)


@pytest.mark.asyncio
async def test_skill_history_widens_correctly(db_session) -> None:
    user = _make_user()
    skill = _make_skill()
    db_session.add_all([user, skill, _make_weight(skill.id, TargetStat.STRENGTH, 1.0)])
    await db_session.flush()

    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            _make_history(user.id, TargetStat.STRENGTH, 10.0, now - timedelta(days=120)),
            _make_history(user.id, TargetStat.STRENGTH, 20.0, now - timedelta(days=10)),
        ]
    )
    await db_session.flush()

    service = SkillService(db_session)
    result = await service.get_skill_history(skill.id, user.id, days=150)

    assert [round(point.value, 4) for point in result] == [10.0, 20.0]


@pytest.mark.asyncio
async def test_skill_history_applies_decay_to_stale_stats_at_later_events(db_session) -> None:
    # Two-stat skill: STRENGTH set once and then left alone long enough to
    # decay (grace period is 10 days), AGILITY updated fresh 30 days later --
    # the point at that later event should show STRENGTH's contribution
    # decayed, not still at its raw recorded value.
    user = _make_user()
    skill = _make_skill()
    db_session.add_all(
        [
            user,
            skill,
            _make_weight(skill.id, TargetStat.STRENGTH, 0.5),
            _make_weight(skill.id, TargetStat.AGILITY, 0.5),
        ]
    )
    await db_session.flush()

    now = datetime.now(timezone.utc)
    strength_at = now - timedelta(days=40)
    agility_at = now - timedelta(days=10)
    db_session.add_all(
        [
            _make_history(user.id, TargetStat.STRENGTH, 100.0, strength_at),
            _make_history(user.id, TargetStat.AGILITY, 50.0, agility_at),
        ]
    )
    await db_session.flush()

    service = SkillService(db_session)
    result = await service.get_skill_history(skill.id, user.id, days=90)

    assert len(result) == 2
    at_agility_event = result[-1]
    assert at_agility_event.date == agility_at.date()

    expected_strength_contribution = get_effective_value(
        UserStat(stat_type=TargetStat.STRENGTH, current_value=100.0, last_updated_at=strength_at),
        agility_at,
    )
    expected_value = expected_strength_contribution * 0.5 + 50.0 * 0.5
    assert at_agility_event.value == pytest.approx(expected_value)
    # And that decay was actually exercised, not a no-op -- the decayed
    # contribution must be strictly less than the raw recorded one.
    assert expected_strength_contribution < 100.0


@pytest.mark.asyncio
async def test_all_skills_history_groups_by_skill_id_without_mixing(db_session) -> None:
    user = _make_user()
    skill_a = _make_skill(name=f"Skill A {uuid.uuid4().hex[:8]}")
    skill_b = _make_skill(name=f"Skill B {uuid.uuid4().hex[:8]}")
    db_session.add_all(
        [
            user,
            skill_a,
            skill_b,
            _make_weight(skill_a.id, TargetStat.STRENGTH, 1.0),
            _make_weight(skill_b.id, TargetStat.AGILITY, 1.0),
        ]
    )
    await db_session.flush()

    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            _make_history(user.id, TargetStat.STRENGTH, 42.0, now - timedelta(days=5)),
            _make_history(user.id, TargetStat.AGILITY, 7.0, now - timedelta(days=5)),
        ]
    )
    await db_session.flush()

    service = SkillService(db_session)
    result = await service.get_all_skills_history(user.id, days=90)

    assert set(result.keys()) >= {skill_a.id, skill_b.id}
    assert [point.value for point in result[skill_a.id]] == [42.0]
    assert [point.value for point in result[skill_b.id]] == [7.0]
