"""AnalyticsService.get_summary: the biggest gainer/decliner across every
stat and skill over a `days` window, an honest (never fabricated)
decline_reason drawn from real decay state, and the skill closest to its
next milestone (same selection as HomePage's "Ближайшие пороги" card).

Deltas are baseline-vs-current, where baseline is the on-the-fly
reconstructed value *as of* `since` (window start) -- not "first point
inside the window" -- so a stat/skill that changed once long before the
window still gets a meaningful baseline. Test stat history rows are seeded
just outside the window (since - 1 day) with a fresh live UserStat inside
it, so neither side decays and deltas come out exact, not approximate.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.exercise import TargetStat
from app.models.progress import StatHistory, UserStat
from app.models.skill import SkillMilestone
from app.models.user import User
from app.services.analytics_service import DECLINE_REASON_DECAY, AnalyticsService

DAYS = 90


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"analytics_{unique}",
        email=f"analytics_{unique}@example.com",
        password_hash="irrelevant",
    )


def _seed_baseline(
    user_id: uuid.UUID, stat_type: TargetStat, value: float, since: datetime
) -> StatHistory:
    """A history row just before the window starts -- picked up as the
    baseline (\"value as of `since`\"), close enough that it never decays
    by the time it's evaluated at `since` itself."""
    return StatHistory(
        id=uuid.uuid4(),
        user_id=user_id,
        stat_type=stat_type,
        value=value,
        recorded_at=since - timedelta(days=1),
        reason="baseline",
    )


def _live_stat(
    user_id: uuid.UUID, stat_type: TargetStat, value: float, last_updated_at: datetime
) -> UserStat:
    return UserStat(
        id=uuid.uuid4(),
        user_id=user_id,
        stat_type=stat_type,
        current_value=value,
        last_updated_at=last_updated_at,
    )


@pytest.mark.asyncio
async def test_top_gainer_and_decliner_across_stats(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=DAYS)

    # STRENGTH: 50 -> 80 (+30, the biggest move). AGILITY: 60 -> 40 (-20,
    # the only decline). Every other stat has no data at all (delta 0).
    db_session.add_all(
        [
            _seed_baseline(user.id, TargetStat.STRENGTH, 50.0, since),
            _seed_baseline(user.id, TargetStat.AGILITY, 60.0, since),
            _live_stat(user.id, TargetStat.STRENGTH, 80.0, now),
            _live_stat(user.id, TargetStat.AGILITY, 40.0, now),
        ]
    )
    await db_session.flush()

    service = AnalyticsService(db_session)
    result = await service.get_summary(user, DAYS)

    assert result.top_gainer.type == "stat"
    assert result.top_gainer.name == TargetStat.STRENGTH.value
    assert result.top_gainer.delta == pytest.approx(30.0)
    assert result.top_gainer.current_value == pytest.approx(80.0)

    assert result.top_decliner is not None
    assert result.top_decliner.type == "stat"
    assert result.top_decliner.name == TargetStat.AGILITY.value
    assert result.top_decliner.delta == pytest.approx(-20.0)
    assert result.top_decliner.current_value == pytest.approx(40.0)


@pytest.mark.asyncio
async def test_decline_reason_is_none_when_decay_not_active(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=DAYS)

    # AGILITY declines (60 -> 40), but its live UserStat was *just* updated
    # (last_updated_at=now) -- idle_days is ~0, well under the 10-day grace
    # period, so decay is definitely not active for it.
    db_session.add_all(
        [
            _seed_baseline(user.id, TargetStat.AGILITY, 60.0, since),
            _live_stat(user.id, TargetStat.AGILITY, 40.0, now),
        ]
    )
    await db_session.flush()

    service = AnalyticsService(db_session)
    result = await service.get_summary(user, DAYS)

    assert result.top_decliner is not None
    assert result.top_decliner.name == TargetStat.AGILITY.value
    assert result.decline_reason is None


@pytest.mark.asyncio
async def test_decline_reason_names_decay_when_active(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=DAYS)

    # AGILITY declines (60 -> 40), and its live UserStat hasn't been
    # touched in 60 days -- well past the 10-day grace period, so decay is
    # active for it right now.
    db_session.add_all(
        [
            _seed_baseline(user.id, TargetStat.AGILITY, 60.0, since),
            _live_stat(user.id, TargetStat.AGILITY, 40.0, now - timedelta(days=60)),
        ]
    )
    await db_session.flush()

    service = AnalyticsService(db_session)
    result = await service.get_summary(user, DAYS)

    assert result.top_decliner is not None
    assert result.top_decliner.name == TargetStat.AGILITY.value
    assert result.decline_reason == DECLINE_REASON_DECAY


@pytest.mark.asyncio
async def test_no_decline_at_all_leaves_top_decliner_and_reason_none(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=DAYS)

    # Only growth, nothing declines.
    db_session.add_all(
        [
            _seed_baseline(user.id, TargetStat.STRENGTH, 10.0, since),
            _live_stat(user.id, TargetStat.STRENGTH, 20.0, now),
        ]
    )
    await db_session.flush()

    service = AnalyticsService(db_session)
    result = await service.get_summary(user, DAYS)

    assert result.top_decliner is None
    assert result.decline_reason is None


@pytest.mark.asyncio
async def test_closest_to_milestone_null_when_everything_is_maxed(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    # Neutralize every milestone in the DB for the duration of this test
    # (rolled back at teardown along with everything else here) -- with
    # none left, every skill's next_milestone is None regardless of what's
    # actually seeded in the shared dev database this suite runs against.
    all_milestones = (await db_session.execute(select(SkillMilestone))).scalars().all()
    for milestone in all_milestones:
        await db_session.delete(milestone)
    await db_session.flush()

    service = AnalyticsService(db_session)
    result = await service.get_summary(user, DAYS)

    assert result.closest_to_milestone is None
