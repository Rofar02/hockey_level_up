"""AssessmentService.run_onice_test: gating around retaking POST
/assessment/on-ice-test, StatHistory audit trail, and the seconds->score
conversion for the 2 on-ice-only stats (on_ice_skating, puck_handling).

Mirrors tests/test_assessment_service.py's coverage for the off-ice test,
using the independent has_onice_assessment/suggested_onice_reassessment
flags instead of has_assessment/suggested_reassessment.
"""
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.config.norm_tables import score_from_value
from app.models.exercise import TargetStat
from app.models.progress import StatHistory
from app.models.user import User
from app.schemas.assessment import OnIceAssessmentTestIn
from app.services.assessment_service import (
    REASON_ONICE_ASSESSMENT_INITIAL,
    REASON_ONICE_ASSESSMENT_RETAKE,
    AssessmentService,
)


def _make_user(
    *,
    has_onice_assessment: bool = False,
    suggested_onice_reassessment: bool = False,
    age: int | None = 30,
) -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"onice_{unique}",
        email=f"onice_{unique}@example.com",
        password_hash="irrelevant",
        age=age,
        has_onice_assessment=has_onice_assessment,
        suggested_onice_reassessment=suggested_onice_reassessment,
    )


def _body() -> OnIceAssessmentTestIn:
    return OnIceAssessmentTestIn(on_ice_skating_seconds=5.0, puck_handling_seconds=16.0)


async def _history_for(db_session, user: User) -> list[StatHistory]:
    rows = (
        await db_session.execute(
            select(StatHistory)
            .where(StatHistory.user_id == user.id)
            .order_by(StatHistory.stat_type)
        )
    ).scalars().all()
    return list(rows)


@pytest.mark.asyncio
async def test_first_onice_test_is_always_allowed_and_logs_initial_history(db_session) -> None:
    user = _make_user(has_onice_assessment=False, suggested_onice_reassessment=False)
    db_session.add(user)
    await db_session.flush()

    result = await AssessmentService(db_session).run_onice_test(user, _body())

    assert user.has_onice_assessment is True
    assert user.suggested_onice_reassessment is False

    history = await _history_for(db_session, user)
    assert len(history) == 2
    assert {h.stat_type for h in history} == {TargetStat.ON_ICE_SKATING, TargetStat.PUCK_HANDLING}
    assert all(h.reason == REASON_ONICE_ASSESSMENT_INITIAL for h in history)

    skating_row = next(h for h in history if h.stat_type == TargetStat.ON_ICE_SKATING)
    assert skating_row.value == result.on_ice_skating


@pytest.mark.asyncio
async def test_onice_retake_without_suggested_reassessment_raises_403(db_session) -> None:
    user = _make_user(has_onice_assessment=True, suggested_onice_reassessment=False)
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await AssessmentService(db_session).run_onice_test(user, _body())

    assert exc_info.value.status_code == 403
    # Locked out before anything was touched -- no stat/history side effects,
    # and it must not have been unlocked by the *off-ice* flags instead.
    assert await _history_for(db_session, user) == []


@pytest.mark.asyncio
async def test_onice_retake_during_reassessment_window_succeeds_and_closes_the_window(
    db_session,
) -> None:
    user = _make_user(has_onice_assessment=True, suggested_onice_reassessment=True)
    db_session.add(user)
    await db_session.flush()

    await AssessmentService(db_session).run_onice_test(user, _body())

    assert user.suggested_onice_reassessment is False
    history = await _history_for(db_session, user)
    assert len(history) == 2
    assert all(h.reason == REASON_ONICE_ASSESSMENT_RETAKE for h in history)


@pytest.mark.asyncio
async def test_second_onice_retake_immediately_after_a_spent_window_raises_403(db_session) -> None:
    user = _make_user(has_onice_assessment=True, suggested_onice_reassessment=True)
    db_session.add(user)
    await db_session.flush()

    service = AssessmentService(db_session)
    await service.run_onice_test(user, _body())

    with pytest.raises(HTTPException) as exc_info:
        await service.run_onice_test(user, _body())

    assert exc_info.value.status_code == 403
    assert len(await _history_for(db_session, user)) == 2  # rejected 2nd call added nothing


@pytest.mark.asyncio
async def test_office_gate_state_does_not_unlock_onice_retake(db_session) -> None:
    # has_assessment/suggested_reassessment (off-ice) look "ready to retake"
    # here, but the on-ice gate must only ever look at its own flags.
    user = _make_user(has_onice_assessment=True, suggested_onice_reassessment=False)
    user.has_assessment = True
    user.suggested_reassessment = True
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await AssessmentService(db_session).run_onice_test(user, _body())
    assert exc_info.value.status_code == 403


# -- seconds -> 0-100 score conversion, at the norm table's own anchor points --


def test_on_ice_skating_score_at_defined_anchor_points_for_18_29() -> None:
    # NORM_TABLES["on_ice_skating_seconds"]["18-29"]: (20, 6.5), (50, 5.0), (80, 4.0), (100, 3.4)
    assert score_from_value("on_ice_skating_seconds", 25, 6.5) == 20
    assert score_from_value("on_ice_skating_seconds", 25, 5.0) == 50
    assert score_from_value("on_ice_skating_seconds", 25, 4.0) == 80
    assert score_from_value("on_ice_skating_seconds", 25, 3.4) == 100


def test_on_ice_skating_score_is_clamped_beyond_the_table_range() -> None:
    # Far slower than the worst anchor -> clamped at 0, not extrapolated negative.
    assert score_from_value("on_ice_skating_seconds", 25, 30.0) == 0
    # Far faster than the best anchor -> clamped at 100, not extrapolated past it.
    assert score_from_value("on_ice_skating_seconds", 25, 0.5) == 100


def test_puck_handling_score_at_defined_anchor_points_for_30_39() -> None:
    # NORM_TABLES["puck_handling_seconds"]["30-39"]: (20, 23.5), (50, 17.5), (80, 13.0), (100, 10.5)
    assert score_from_value("puck_handling_seconds", 35, 23.5) == 20
    assert score_from_value("puck_handling_seconds", 35, 17.5) == 50
    assert score_from_value("puck_handling_seconds", 35, 13.0) == 80
    assert score_from_value("puck_handling_seconds", 35, 10.5) == 100


def test_puck_handling_score_lower_time_scores_higher() -> None:
    # Lower (better) time must score higher, same "less time = more score"
    # direction as run_1km_seconds -- both are in INVERSE_TESTS.
    slow = score_from_value("puck_handling_seconds", 25, 20.0)
    fast = score_from_value("puck_handling_seconds", 25, 10.0)
    assert fast > slow


def test_older_age_group_gets_more_lenient_on_ice_skating_norms() -> None:
    # Same raw time, older age bracket -> equal or higher score (norms
    # loosen with age, same convention as the off-ice tables).
    young_score = score_from_value("on_ice_skating_seconds", 25, 5.5)
    older_score = score_from_value("on_ice_skating_seconds", 55, 5.5)
    assert older_score >= young_score
