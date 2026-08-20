"""AssessmentService: gating around retaking POST /assessment/test (and
start-from-scratch), and the StatHistory audit trail for both paths.

Before this test file existed, ProgressRepository.set_stat_value overwrote
UserStat.current_value with no StatHistory row at all, so a repeatable
assessment call could silently rewrite a stat and the jump would only show
up misattributed to the next quest_completed row. Coverage here locks in:
first assessment always allowed, retake only allowed during the
suggested_reassessment window (set at training-block rollover), the window
closing itself after use, and every applied value being logged with a
reason that identifies it as an assessment, not a quest.
"""
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.exercise import TargetStat
from app.models.progress import StatHistory, UserStat
from app.models.user import User
from app.schemas.assessment import AssessmentTestIn, OnIceAssessmentTestIn
from app.services.assessment_service import (
    REASON_ASSESSMENT_INITIAL,
    REASON_ASSESSMENT_RETAKE,
    REASON_ONICE_BASELINE_DEFAULT,
    SCRATCH_STARTING_VALUE,
    AssessmentService,
)

OFF_ICE_STAT_TYPES = {
    TargetStat.AGILITY,
    TargetStat.STRENGTH,
    TargetStat.ENDURANCE,
    TargetStat.INTELLECT,
}
ON_ICE_STAT_TYPES = {TargetStat.ON_ICE_SKATING, TargetStat.PUCK_HANDLING}


def _make_user(
    *, has_assessment: bool = False, suggested_reassessment: bool = False, age: int | None = 30
) -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"assess_{unique}",
        email=f"assess_{unique}@example.com",
        password_hash="irrelevant",
        age=age,
        has_assessment=has_assessment,
        suggested_reassessment=suggested_reassessment,
    )


async def _history_for(db_session, user: User) -> list[StatHistory]:
    rows = (
        await db_session.execute(
            select(StatHistory)
            .where(StatHistory.user_id == user.id)
            .order_by(StatHistory.stat_type)
        )
    ).scalars().all()
    return list(rows)


async def _user_stats_for(db_session, user: User) -> list[UserStat]:
    rows = (
        await db_session.execute(
            select(UserStat).where(UserStat.user_id == user.id).order_by(UserStat.stat_type)
        )
    ).scalars().all()
    return list(rows)


@pytest.mark.asyncio
async def test_first_assessment_is_always_allowed_and_logs_initial_history(db_session) -> None:
    user = _make_user(has_assessment=False, suggested_reassessment=False)
    db_session.add(user)
    await db_session.flush()

    result = await AssessmentService(db_session).start_from_scratch(user)

    assert result.strength == SCRATCH_STARTING_VALUE
    assert user.has_assessment is True
    assert user.suggested_reassessment is False

    # 4 off-ice (the test itself) + 2 on-ice baseline defaults, seeded
    # alongside it so a brand-new user's on-ice tiles have something to
    # render before they've ever set foot on the ice.
    history = await _history_for(db_session, user)
    assert len(history) == 6
    off_ice = [h for h in history if h.stat_type in OFF_ICE_STAT_TYPES]
    on_ice = [h for h in history if h.stat_type in ON_ICE_STAT_TYPES]

    assert {h.stat_type for h in off_ice} == OFF_ICE_STAT_TYPES
    assert all(h.reason == REASON_ASSESSMENT_INITIAL for h in off_ice)
    # Intellect isn't set to SCRATCH_STARTING_VALUE directly -- start_from_scratch
    # computes it from years_of_experience (intellect_baseline) even on the
    # "skip the real test" path, independent of the physical-stat
    # placeholder. This test's user has no years_of_experience set
    # (None -> 0 years), so intellect_baseline is just its base -- which
    # equals SCRATCH_STARTING_VALUE (10.0) precisely because a user with no
    # hockey experience shouldn't have intellect start ahead of every other
    # stat -- see app.config.expected_baseline.INTELLECT_BASE.
    physical = [h for h in off_ice if h.stat_type != TargetStat.INTELLECT]
    intellect = next(h for h in off_ice if h.stat_type == TargetStat.INTELLECT)
    assert all(h.value == SCRATCH_STARTING_VALUE for h in physical)
    assert intellect.value == SCRATCH_STARTING_VALUE

    assert {h.stat_type for h in on_ice} == ON_ICE_STAT_TYPES
    assert all(h.reason == REASON_ONICE_BASELINE_DEFAULT for h in on_ice)
    assert all(h.value == SCRATCH_STARTING_VALUE for h in on_ice)


@pytest.mark.asyncio
async def test_retake_without_suggested_reassessment_raises_403(db_session) -> None:
    user = _make_user(has_assessment=True, suggested_reassessment=False)
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await AssessmentService(db_session).start_from_scratch(user)

    assert exc_info.value.status_code == 403

    # Locked out before anything was touched -- no stat/history side effects.
    history = await _history_for(db_session, user)
    assert history == []


@pytest.mark.asyncio
async def test_retake_during_reassessment_window_succeeds_and_closes_the_window(
    db_session,
) -> None:
    user = _make_user(has_assessment=True, suggested_reassessment=True)
    db_session.add(user)
    await db_session.flush()

    result = await AssessmentService(db_session).start_from_scratch(user)

    assert result.strength == SCRATCH_STARTING_VALUE
    # Window closes after being spent, so a second retake right after fails.
    assert user.suggested_reassessment is False

    history = await _history_for(db_session, user)
    assert len(history) == 6
    off_ice = [h for h in history if h.stat_type in OFF_ICE_STAT_TYPES]
    on_ice = [h for h in history if h.stat_type in ON_ICE_STAT_TYPES]
    assert all(h.reason == REASON_ASSESSMENT_RETAKE for h in off_ice)
    # No prior on-ice row existed for this user (a fresh in-memory User with
    # has_assessment set directly, not a real prior _apply_assessment call)
    # -- this first-ever ensure_stat_exists call still inserts + logs it as
    # a baseline default, same as the very first assessment would.
    assert all(h.reason == REASON_ONICE_BASELINE_DEFAULT for h in on_ice)


@pytest.mark.asyncio
async def test_second_retake_immediately_after_a_spent_window_raises_403(db_session) -> None:
    user = _make_user(has_assessment=True, suggested_reassessment=True)
    db_session.add(user)
    await db_session.flush()

    service = AssessmentService(db_session)
    await service.start_from_scratch(user)

    with pytest.raises(HTTPException) as exc_info:
        await service.start_from_scratch(user)

    assert exc_info.value.status_code == 403
    # Still only the first retake's rows -- the rejected second call added nothing.
    history = await _history_for(db_session, user)
    assert len(history) == 6


@pytest.mark.asyncio
async def test_run_test_gate_matches_start_from_scratch(db_session) -> None:
    user = _make_user(has_assessment=True, suggested_reassessment=False, age=30)
    db_session.add(user)
    await db_session.flush()

    body = AssessmentTestIn(
        long_jump_cm=200,
        pushups_reps=25,
        squats_reps=35,
        plank_seconds=60,
        run_1km_seconds=300,
    )

    with pytest.raises(HTTPException) as exc_info:
        await AssessmentService(db_session).run_test(user, body)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_run_test_within_window_logs_retake_history_with_computed_values(
    db_session,
) -> None:
    user = _make_user(has_assessment=True, suggested_reassessment=True, age=30)
    db_session.add(user)
    await db_session.flush()

    body = AssessmentTestIn(
        long_jump_cm=200,
        pushups_reps=25,
        squats_reps=35,
        plank_seconds=60,
        run_1km_seconds=300,
    )

    result = await AssessmentService(db_session).run_test(user, body)

    history = await _history_for(db_session, user)
    assert len(history) == 6
    off_ice = [h for h in history if h.stat_type in OFF_ICE_STAT_TYPES]
    on_ice = [h for h in history if h.stat_type in ON_ICE_STAT_TYPES]
    assert all(h.reason == REASON_ASSESSMENT_RETAKE for h in off_ice)
    assert all(h.reason == REASON_ONICE_BASELINE_DEFAULT for h in on_ice)
    assert all(h.value == SCRATCH_STARTING_VALUE for h in on_ice)

    strength_row = next(h for h in history if h.stat_type == TargetStat.STRENGTH)
    assert strength_row.value == result.strength
    assert user.suggested_reassessment is False


# -- UserStat row counts (the actual table the frontend reads from, not
# just its StatHistory audit trail) --


@pytest.mark.asyncio
async def test_start_from_scratch_creates_exactly_six_user_stats(db_session) -> None:
    user = _make_user(has_assessment=False, suggested_reassessment=False)
    db_session.add(user)
    await db_session.flush()

    await AssessmentService(db_session).start_from_scratch(user)

    stats = await _user_stats_for(db_session, user)
    assert len(stats) == 6
    assert {s.stat_type for s in stats} == OFF_ICE_STAT_TYPES | ON_ICE_STAT_TYPES
    on_ice_values = {s.stat_type: s.current_value for s in stats if s.stat_type in ON_ICE_STAT_TYPES}
    assert on_ice_values == {
        TargetStat.ON_ICE_SKATING: SCRATCH_STARTING_VALUE,
        TargetStat.PUCK_HANDLING: SCRATCH_STARTING_VALUE,
    }


@pytest.mark.asyncio
async def test_run_test_creates_exactly_six_user_stats(db_session) -> None:
    user = _make_user(has_assessment=False, suggested_reassessment=False, age=30)
    db_session.add(user)
    await db_session.flush()

    body = AssessmentTestIn(
        long_jump_cm=200, pushups_reps=25, squats_reps=35, plank_seconds=60, run_1km_seconds=300
    )
    await AssessmentService(db_session).run_test(user, body)

    stats = await _user_stats_for(db_session, user)
    assert len(stats) == 6
    assert {s.stat_type for s in stats} == OFF_ICE_STAT_TYPES | ON_ICE_STAT_TYPES


# -- the on-ice baseline must never clobber a real on-ice test result --


@pytest.mark.asyncio
async def test_onice_baseline_does_not_overwrite_a_real_onice_result(db_session) -> None:
    """A user who's already taken the real on-ice test, then later takes
    (or retakes) the off-ice assessment, must keep their measured on-ice
    values -- the baseline-seed in _apply_assessment is insert-only-if-
    missing, never an overwrite."""
    user = _make_user(has_assessment=True, suggested_reassessment=True, age=30)
    db_session.add(user)
    await db_session.flush()

    service = AssessmentService(db_session)
    real_result = await service.run_onice_test(
        user, OnIceAssessmentTestIn(on_ice_skating_seconds=5.0, puck_handling_seconds=16.0)
    )
    assert real_result.on_ice_skating != SCRATCH_STARTING_VALUE

    # Now the off-ice retake runs and would, without the insert-only guard,
    # stomp the just-recorded real on-ice values back down to the baseline.
    await service.start_from_scratch(user)

    stats = await _user_stats_for(db_session, user)
    on_ice_by_type = {s.stat_type: s.current_value for s in stats if s.stat_type in ON_ICE_STAT_TYPES}
    assert on_ice_by_type[TargetStat.ON_ICE_SKATING] == real_result.on_ice_skating
    assert on_ice_by_type[TargetStat.PUCK_HANDLING] == real_result.puck_handling
    # Confirms the test is actually meaningful: the real result differs from
    # the baseline value that would otherwise have clobbered it.
    assert on_ice_by_type[TargetStat.ON_ICE_SKATING] != SCRATCH_STARTING_VALUE


@pytest.mark.asyncio
async def test_onice_baseline_is_not_duplicated_across_repeated_assessment_calls(
    db_session,
) -> None:
    user = _make_user(has_assessment=True, suggested_reassessment=True, age=30)
    db_session.add(user)
    await db_session.flush()

    service = AssessmentService(db_session)
    await service.start_from_scratch(user)
    # Reopen the retake window and go again -- the on-ice ensure-exists call
    # runs on every retake, but must stay a no-op after the first insert.
    user.suggested_reassessment = True
    await service.start_from_scratch(user)

    stats = await _user_stats_for(db_session, user)
    on_ice_stats = [s for s in stats if s.stat_type in ON_ICE_STAT_TYPES]
    assert len(on_ice_stats) == 2  # one row per stat type, not one per call
