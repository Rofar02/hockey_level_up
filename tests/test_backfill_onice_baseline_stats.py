"""scripts/backfill_onice_baseline_stats.py: one-off fix for users created
before AssessmentService._apply_assessment started seeding on_ice_skating/
puck_handling itself. Coverage locks in:
  - only touches users who've completed onboarding (has_assessment=True);
  - never overwrites a real on-ice test result already on record;
  - re-running it (the "already-fixed data" case) is a true no-op, not
    just non-destructive -- 0 rows inserted, 0 duplicates.
"""
import uuid

import pytest
from sqlalchemy import select

from app.models.exercise import TargetStat
from app.models.progress import UserStat
from app.models.user import User
from app.services.assessment_service import SCRATCH_STARTING_VALUE
from scripts.backfill_onice_baseline_stats import backfill_onice_baseline_stats

ON_ICE_STAT_TYPES = {TargetStat.ON_ICE_SKATING, TargetStat.PUCK_HANDLING}


def _make_user(*, has_assessment: bool) -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"backfill_{unique}",
        email=f"backfill_{unique}@example.com",
        password_hash="irrelevant",
        has_assessment=has_assessment,
    )


async def _onice_stats_for(db_session, user: User) -> list[UserStat]:
    rows = (
        await db_session.execute(
            select(UserStat).where(
                UserStat.user_id == user.id, UserStat.stat_type.in_(ON_ICE_STAT_TYPES)
            )
        )
    ).scalars().all()
    return list(rows)


@pytest.mark.asyncio
async def test_backfills_only_users_with_completed_onboarding(db_session) -> None:
    # No assertion on the aggregate inserted_count here -- db_session runs
    # against the real dev DB (rolled back at teardown, see conftest.py),
    # which may already have other has_assessment=True users the script
    # legitimately also backfills in the same pass. What actually matters
    # is scoped to these two specific users, checked below.
    onboarded = _make_user(has_assessment=True)
    not_onboarded = _make_user(has_assessment=False)
    db_session.add_all([onboarded, not_onboarded])
    await db_session.flush()

    await backfill_onice_baseline_stats(db_session)

    onboarded_stats = await _onice_stats_for(db_session, onboarded)
    assert {s.stat_type for s in onboarded_stats} == ON_ICE_STAT_TYPES
    assert all(s.current_value == SCRATCH_STARTING_VALUE for s in onboarded_stats)

    assert await _onice_stats_for(db_session, not_onboarded) == []


@pytest.mark.asyncio
async def test_does_not_overwrite_an_existing_onice_value(db_session) -> None:
    user = _make_user(has_assessment=True)
    db_session.add(user)
    await db_session.flush()

    real_value = 71.5
    db_session.add(
        UserStat(user_id=user.id, stat_type=TargetStat.ON_ICE_SKATING, current_value=real_value)
    )
    await db_session.flush()

    await backfill_onice_baseline_stats(db_session)

    stats_by_type = {s.stat_type: s for s in await _onice_stats_for(db_session, user)}
    # The already-real ON_ICE_SKATING value survives untouched...
    assert stats_by_type[TargetStat.ON_ICE_SKATING].current_value == real_value
    # ...while the genuinely-missing PUCK_HANDLING still gets its baseline.
    assert stats_by_type[TargetStat.PUCK_HANDLING].current_value == SCRATCH_STARTING_VALUE


@pytest.mark.asyncio
async def test_rerunning_on_already_fixed_data_is_a_true_no_op(db_session) -> None:
    user = _make_user(has_assessment=True)
    db_session.add(user)
    await db_session.flush()

    await backfill_onice_baseline_stats(db_session)
    assert len(await _onice_stats_for(db_session, user)) == 2

    # After the first run, *every* eligible user (pre-existing dev-DB ones
    # included) already has both rows -- so a second pass must insert
    # nothing for anyone, not just for this test's own user. This
    # assertion holds regardless of how much other data is in the DB.
    second_run_inserted = await backfill_onice_baseline_stats(db_session)
    assert second_run_inserted == 0

    stats = await _onice_stats_for(db_session, user)
    assert len(stats) == 2  # no duplicates
    assert all(s.current_value == SCRATCH_STARTING_VALUE for s in stats)
