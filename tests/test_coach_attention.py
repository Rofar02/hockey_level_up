"""GET /users/me/coach-attention -- why the tab bar's AI coach button glows:
a pending proposal, an unanswered restriction check-in, or a player who has
never met the coach; highest priority first, None otherwise.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.coach_chat import CoachChatMessage, CoachChatRole
from app.models.exercise import MovementPattern
from app.models.coach_chat_proposed_action import (
    CoachActionStatus,
    CoachActionType,
    CoachChatProposedAction,
)
from app.models.user import User
from app.models.user_temporary_restriction import UserTemporaryRestriction
from app.repositories.coachmark_repository import CoachmarkRepository
from app.services.coach_attention_service import COACH_CHAT_OPENED_HINT, CoachAttentionService

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
TODAY = date(2026, 9, 25)


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"attention_{unique}",
        email=f"attention_{unique}@example.com",
        password_hash="irrelevant",
        timezone="UTC",
    )


async def _user(db_session) -> User:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    return user


def _restriction(user: User, expires_at: date, **extra) -> UserTemporaryRestriction:
    # Exactly one target is required (movement pattern or muscle group).
    return UserTemporaryRestriction(
        id=uuid.uuid4(), user_id=user.id, movement_pattern=MovementPattern.SQUAT, expires_at=expires_at, **extra
    )


def _message(user: User, role: CoachChatRole, at: datetime) -> CoachChatMessage:
    return CoachChatMessage(id=uuid.uuid4(), user_id=user.id, role=role, content="…", created_at=at)


async def _reason(db_session, user: User):
    return await CoachAttentionService(db_session).get_reason(user, now=NOW)


@pytest.mark.asyncio
async def test_new_player_glows_until_the_chat_is_opened(db_session) -> None:
    user = await _user(db_session)
    assert await _reason(db_session, user) == "first_visit"

    await CoachmarkRepository(db_session).mark_seen(user.id, COACH_CHAT_OPENED_HINT)
    assert await _reason(db_session, user) is None


@pytest.mark.asyncio
async def test_player_who_already_wrote_to_the_coach_is_not_a_first_visit(db_session) -> None:
    user = await _user(db_session)
    db_session.add(_message(user, CoachChatRole.USER, NOW - timedelta(days=30)))
    await db_session.flush()
    assert await _reason(db_session, user) is None


@pytest.mark.asyncio
async def test_pending_proposal_glows_and_outranks_everything(db_session) -> None:
    user = await _user(db_session)
    reply = _message(user, CoachChatRole.ASSISTANT, NOW - timedelta(hours=2))
    db_session.add(reply)
    await db_session.flush()
    action = CoachChatProposedAction(
        id=uuid.uuid4(),
        message_id=reply.id,
        user_id=user.id,
        action_type=CoachActionType.SET_TOURNAMENT_DATE,
        payload={"tournament_date": "2026-11-01"},
        status=CoachActionStatus.PENDING,
        created_at=NOW - timedelta(hours=2),
    )
    db_session.add(action)
    # Also an unanswered check-in -- the proposal still wins.
    db_session.add(
        _restriction(user, TODAY - timedelta(days=1), reason="плечо")
    )
    await db_session.flush()
    assert await _reason(db_session, user) == "pending_action"

    action.status = CoachActionStatus.CONFIRMED
    await db_session.flush()
    assert await _reason(db_session, user) == "checkin"


@pytest.mark.asyncio
async def test_stale_pending_proposal_stops_glowing(db_session) -> None:
    user = await _user(db_session)
    db_session.add(_message(user, CoachChatRole.USER, NOW - timedelta(days=20)))
    reply = _message(user, CoachChatRole.ASSISTANT, NOW - timedelta(days=20))
    db_session.add(reply)
    await db_session.flush()
    db_session.add(
        CoachChatProposedAction(
            id=uuid.uuid4(),
            message_id=reply.id,
            user_id=user.id,
            action_type=CoachActionType.SET_TOURNAMENT_DATE,
            payload={"tournament_date": "2026-11-01"},
            status=CoachActionStatus.PENDING,
            created_at=NOW - timedelta(days=20),
        )
    )
    await db_session.flush()
    assert await _reason(db_session, user) is None


@pytest.mark.asyncio
async def test_expired_restriction_glows_until_the_player_writes_to_the_coach(db_session) -> None:
    user = await _user(db_session)
    # Wrote to the coach long before -- that doesn't answer this check-in.
    db_session.add(_message(user, CoachChatRole.USER, NOW - timedelta(days=10)))
    db_session.add(
        _restriction(user, TODAY - timedelta(days=1), reason="колено")
    )
    await db_session.flush()
    assert await _reason(db_session, user) == "checkin"

    db_session.add(_message(user, CoachChatRole.USER, NOW - timedelta(hours=1)))
    await db_session.flush()
    assert await _reason(db_session, user) is None


@pytest.mark.asyncio
async def test_active_lifted_or_old_restrictions_do_not_glow(db_session) -> None:
    user = await _user(db_session)
    db_session.add(_message(user, CoachChatRole.USER, NOW - timedelta(days=60)))
    db_session.add_all(
        [
            # Still active.
            _restriction(user, TODAY + timedelta(days=3)),
            # Lifted early by the player.
            _restriction(user, TODAY - timedelta(days=1), lifted_at=NOW - timedelta(days=3)),
            # Ran out weeks ago.
            _restriction(user, TODAY - timedelta(days=20)),
        ]
    )
    await db_session.flush()
    assert await _reason(db_session, user) is None
