"""Coach chat proposed actions (CoachChatProposedAction): the model can
propose exactly 3 actions as native tool calls (see
coach_chat_service._coach_tools; until 2026-10-04 a <!--ACTION:{...}-->
text marker), which only ever gets applied through
POST /users/me/coach-chat/actions/{id}/confirm -- never silently, never
bypassing the real service method the corresponding Settings screen would
call itself.

Covers: tool-call validation (a valid call resolves; invalid/unknown/
ambiguous calls are silently dropped, the text is still shown; a bare call
with no text gets a readable fallback), the one-pending-action-at-a-time rule,
list_history attaching the right proposed_action to the right message, and
confirm_action actually dispatching to SkillService.add_priority_skill /
UserService.update_profile / UserTemporaryRestrictionService.report for
each of the 3 action types -- plus ownership/status guards and that
confirm-time re-validation (e.g. a since-filled skill-slot cap) reuses the
target service's own error, not bespoke logic.
"""
import json
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import Settings
from app.core.level_unlocks import max_skill_slots_for_level
from app.models.coach_chat import CoachChatMessage
from app.models.coach_chat_proposed_action import CoachActionStatus, CoachActionType
from app.models.exercise import MovementPattern
from app.models.skill import Skill, UserSkillPreference
from app.models.user import User
from app.models.user_temporary_restriction import UserTemporaryRestriction
from app.services import coach_chat_service
from app.services.coach_chat_service import CoachChatService, ZaiReply, ZaiUsage


def _make_user(*, has_premium: bool = True, level: int = 1) -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"coachaction_{unique}",
        email=f"coachaction_{unique}@example.com",
        password_hash="irrelevant",
        has_premium=has_premium,
        level=level,
    )


def _make_skill(*, required_level: int = 1) -> Skill:
    return Skill(id=uuid.uuid4(), name=f"Навык {uuid.uuid4().hex[:8]}", required_level=required_level)


def _settings_with_key() -> Settings:
    return Settings(zai_api_key="test-key")


def _reply_with_tool(action: dict, text: str = "Вот что предлагаю.") -> ZaiReply:
    arguments = {key: value for key, value in action.items() if key != "type"}
    return ZaiReply(text=text, tool_call=(action["type"], json.dumps(arguments, ensure_ascii=False)))


def _install_fake_call(monkeypatch, *, reply: str | ZaiReply):
    async def _fake_call_zai(api_key, base_url, model, system_prompt, messages, tools=None) -> ZaiReply:
        return reply if isinstance(reply, ZaiReply) else ZaiReply(text=reply)

    monkeypatch.setattr(coach_chat_service, "_call_zai", _fake_call_zai)


async def _send(db_session, monkeypatch, user: User, reply: str | ZaiReply, message: str = "сообщение"):
    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: _settings_with_key())
    _install_fake_call(monkeypatch, reply=reply)
    return await CoachChatService(db_session).send_message(user, message)


# -- tool-call validation --


@pytest.mark.asyncio
async def test_tournament_date_tool_call_creates_pending_action(
    db_session, monkeypatch
) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    reply = await _send(
        db_session,
        monkeypatch,
        user,
        _reply_with_tool(
            {"type": "set_tournament_date", "tournament_date": "2027-03-15"},
            text="Записал дату турнира.",
        ),
    )

    assert reply.content == "Записал дату турнира."
    assert reply.proposed_action is not None
    assert reply.proposed_action.action_type == CoachActionType.SET_TOURNAMENT_DATE
    assert reply.proposed_action.status == CoachActionStatus.PENDING
    assert reply.proposed_action.payload == {"tournament_date": "2027-03-15"}
    assert "15.03.2027" in reply.proposed_action.summary


@pytest.mark.asyncio
async def test_skill_priority_tool_call_resolves_real_skill_by_name(db_session, monkeypatch) -> None:
    user = _make_user()
    skill = _make_skill()
    db_session.add_all([user, skill])
    await db_session.flush()

    reply = await _send(
        db_session,
        monkeypatch,
        user,
        _reply_with_tool({"type": "skill_priority_add", "skill_name": skill.name}),
    )

    assert reply.proposed_action is not None
    assert reply.proposed_action.action_type == CoachActionType.SKILL_PRIORITY_ADD
    assert reply.proposed_action.payload == {"skill_id": str(skill.id), "skill_name": skill.name}
    assert skill.name in reply.proposed_action.summary


@pytest.mark.asyncio
async def test_skill_priority_tool_call_unknown_name_creates_no_action(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    reply = await _send(
        db_session,
        monkeypatch,
        user,
        _reply_with_tool(
            {"type": "skill_priority_add", "skill_name": "Несуществующий навык 12345"},
            text="Хочу предложить кое-что.",
        ),
    )

    assert reply.content == "Хочу предложить кое-что."  # text still shown
    assert reply.proposed_action is None  # but not created -- name didn't resolve


@pytest.mark.asyncio
async def test_malformed_tool_arguments_create_no_action_but_text_is_shown(
    db_session, monkeypatch
) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    reply = await _send(
        db_session,
        monkeypatch,
        user,
        ZaiReply(text="Обычный ответ.", tool_call=("set_tournament_date", "{not valid json")),
    )

    assert reply.content == "Обычный ответ."
    assert reply.proposed_action is None


@pytest.mark.asyncio
async def test_unknown_action_type_creates_no_action(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    reply = await _send(
        db_session,
        monkeypatch,
        user,
        _reply_with_tool({"type": "delete_account", "target": "everything"}),
    )

    assert reply.proposed_action is None


@pytest.mark.asyncio
async def test_reply_with_no_tool_call_is_unaffected(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    reply = await _send(db_session, monkeypatch, user, "Просто обычный ответ без предложений.")

    assert reply.content == "Просто обычный ответ без предложений."
    assert reply.proposed_action is None


@pytest.mark.asyncio
async def test_restriction_tool_call_both_targets_creates_no_action(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    reply = await _send(
        db_session,
        monkeypatch,
        user,
        _reply_with_tool(
            {
                "type": "report_restriction",
                "movement_pattern": "shoulder_mobility",
                "muscle_group": "shoulders",
            }
        ),
    )

    assert reply.proposed_action is None


@pytest.mark.asyncio
async def test_restriction_tool_call_neither_target_creates_no_action(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    reply = await _send(
        db_session, monkeypatch, user, _reply_with_tool({"type": "report_restriction", "reason": "болит"})
    )

    assert reply.proposed_action is None


@pytest.mark.asyncio
async def test_restriction_tool_call_valid_movement_pattern_resolves(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    reply = await _send(
        db_session,
        monkeypatch,
        user,
        _reply_with_tool(
            {
                "type": "report_restriction",
                "movement_pattern": "shoulder_mobility",
                "reason": "побаливает плечо",
            }
        ),
    )

    assert reply.proposed_action is not None
    assert reply.proposed_action.payload == {
        "movement_pattern": "shoulder_mobility",
        "muscle_group": None,
        "reason": "побаливает плечо",
    }
    assert "Мобильность плечевого пояса" in reply.proposed_action.summary


# -- one pending action at a time --


@pytest.mark.asyncio
async def test_new_proposal_expires_previous_pending_one(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    first_reply = await _send(
        db_session,
        monkeypatch,
        user,
        _reply_with_tool({"type": "set_tournament_date", "tournament_date": "2027-01-01"}),
        message="первое",
    )
    first_action_id = first_reply.proposed_action.id

    await _send(
        db_session,
        monkeypatch,
        user,
        _reply_with_tool({"type": "set_tournament_date", "tournament_date": "2027-06-01"}),
        message="второе",
    )

    service = CoachChatService(db_session)
    # Confirming the now-expired first action must be refused, same as any
    # other non-pending status.
    with pytest.raises(HTTPException) as exc_info:
        await service.confirm_action(user, first_action_id)
    assert exc_info.value.status_code == 400


# -- list_history attaches the right proposed_action --


@pytest.mark.asyncio
async def test_list_history_attaches_proposed_action_to_the_right_message(
    db_session, monkeypatch
) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    await _send(db_session, monkeypatch, user, "Просто ответ, без предложения.", message="первое")
    await _send(
        db_session,
        monkeypatch,
        user,
        _reply_with_tool({"type": "set_tournament_date", "tournament_date": "2027-03-15"}),
        message="второе",
    )

    service = CoachChatService(db_session)
    history = await service.list_history(user.id, limit=50)

    assistant_messages = [entry for entry in history if entry.role.value == "assistant"]
    assert len(assistant_messages) == 2
    assert assistant_messages[0].proposed_action is None
    assert assistant_messages[1].proposed_action is not None
    assert assistant_messages[1].proposed_action.status == CoachActionStatus.PENDING


# -- confirm_action dispatches to the real service methods --


@pytest.mark.asyncio
async def test_confirm_tournament_date_action_sets_user_field(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    reply = await _send(
        db_session,
        monkeypatch,
        user,
        _reply_with_tool({"type": "set_tournament_date", "tournament_date": "2027-03-15"}),
    )

    service = CoachChatService(db_session)
    result = await service.confirm_action(user, reply.proposed_action.id)

    assert result.status == CoachActionStatus.CONFIRMED
    assert user.tournament_date == date(2027, 3, 15)


@pytest.mark.asyncio
async def test_confirm_skill_priority_action_adds_preference(db_session, monkeypatch) -> None:
    user = _make_user()
    skill = _make_skill()
    db_session.add_all([user, skill])
    await db_session.flush()

    reply = await _send(
        db_session,
        monkeypatch,
        user,
        _reply_with_tool({"type": "skill_priority_add", "skill_name": skill.name}),
    )

    service = CoachChatService(db_session)
    await service.confirm_action(user, reply.proposed_action.id)

    prefs = (
        await db_session.execute(
            select(UserSkillPreference).where(UserSkillPreference.user_id == user.id)
        )
    ).scalars().all()
    assert {pref.skill_id for pref in prefs} == {skill.id}


@pytest.mark.asyncio
async def test_confirm_restriction_action_creates_restriction_row(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    reply = await _send(
        db_session,
        monkeypatch,
        user,
        _reply_with_tool(
            {
                "type": "report_restriction",
                "movement_pattern": "shoulder_mobility",
                "reason": "побаливает плечо",
            }
        ),
    )

    service = CoachChatService(db_session)
    await service.confirm_action(user, reply.proposed_action.id)

    rows = (
        await db_session.execute(
            select(UserTemporaryRestriction).where(UserTemporaryRestriction.user_id == user.id)
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].movement_pattern == MovementPattern.SHOULDER_MOBILITY
    assert rows[0].reason == "побаливает плечо"


# -- ownership / status guards --


@pytest.mark.asyncio
async def test_confirm_action_owned_by_another_user_returns_404(db_session, monkeypatch) -> None:
    owner = _make_user()
    intruder = _make_user()
    db_session.add_all([owner, intruder])
    await db_session.flush()

    reply = await _send(
        db_session,
        monkeypatch,
        owner,
        _reply_with_tool({"type": "set_tournament_date", "tournament_date": "2027-03-15"}),
    )

    service = CoachChatService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.confirm_action(intruder, reply.proposed_action.id)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_confirm_already_confirmed_action_returns_400(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    reply = await _send(
        db_session,
        monkeypatch,
        user,
        _reply_with_tool({"type": "set_tournament_date", "tournament_date": "2027-03-15"}),
    )

    service = CoachChatService(db_session)
    await service.confirm_action(user, reply.proposed_action.id)

    with pytest.raises(HTTPException) as exc_info:
        await service.confirm_action(user, reply.proposed_action.id)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_confirm_reraises_the_real_slot_cap_error_when_since_exceeded(
    db_session, monkeypatch
) -> None:
    """Proves the "re-validation is free" design property: confirm_action
    doesn't duplicate SkillService's own slot-cap logic, it just calls it
    -- so a cap that's since been filled (by the player themselves, via
    Settings, between the proposal and the confirmation) is caught the
    exact same way a direct PUT /users/me/skill-preferences call would be,
    with no extra code needed here."""
    user = _make_user(level=1)  # max_skill_slots_for_level(1) == 3
    proposed_skill = _make_skill()
    filler_skills = [_make_skill() for _ in range(max_skill_slots_for_level(user.level))]
    db_session.add_all([user, proposed_skill, *filler_skills])
    await db_session.flush()

    reply = await _send(
        db_session,
        monkeypatch,
        user,
        _reply_with_tool({"type": "skill_priority_add", "skill_name": proposed_skill.name}),
    )

    # Fill every slot with OTHER skills after the proposal was made, same
    # as if the player had gone and done this themselves in Settings.
    db_session.add_all(
        [UserSkillPreference(user_id=user.id, skill_id=skill.id) for skill in filler_skills]
    )
    await db_session.flush()

    service = CoachChatService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.confirm_action(user, reply.proposed_action.id)
    assert exc_info.value.status_code == 400
    assert "Доступно не более" in exc_info.value.detail


@pytest.mark.asyncio
async def test_dismiss_action_marks_dismissed_without_applying(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    reply = await _send(
        db_session,
        monkeypatch,
        user,
        _reply_with_tool({"type": "set_tournament_date", "tournament_date": "2027-03-15"}),
    )

    service = CoachChatService(db_session)
    result = await service.dismiss_action(user, reply.proposed_action.id)

    assert result.status == CoachActionStatus.DISMISSED
    assert user.tournament_date is None


@pytest.mark.asyncio
async def test_bare_tool_call_without_text_gets_a_readable_fallback(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    reply = await _send(
        db_session,
        monkeypatch,
        user,
        _reply_with_tool({"type": "set_tournament_date", "tournament_date": "2027-03-15"}, text=""),
    )

    assert reply.proposed_action is not None
    assert "15.03.2027" in reply.content
    assert "кнопкой" in reply.content


@pytest.mark.asyncio
async def test_restriction_tool_call_with_empty_other_target_resolves(db_session, monkeypatch) -> None:
    """A tool call may fill the unused target with "" instead of leaving it out."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    reply = await _send(
        db_session,
        monkeypatch,
        user,
        _reply_with_tool({"type": "report_restriction", "movement_pattern": "squat", "muscle_group": ""}),
    )

    assert reply.proposed_action is not None
    assert reply.proposed_action.payload["movement_pattern"] == MovementPattern.SQUAT.value
    assert reply.proposed_action.payload["muscle_group"] is None


@pytest.mark.asyncio
async def test_token_usage_is_stored_on_the_assistant_message(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    reply = await _send(
        db_session,
        monkeypatch,
        user,
        ZaiReply(
            text="Ответ.",
            usage=ZaiUsage(prompt_tokens=2800, cached_tokens=2500, completion_tokens=140, reasoning_tokens=30),
        ),
    )

    stored = await db_session.get(CoachChatMessage, reply.id)
    assert (stored.prompt_tokens, stored.cached_tokens, stored.completion_tokens, stored.reasoning_tokens) == (
        2800,
        2500,
        140,
        30,
    )
    assert stored.llm_model == _settings_with_key().coach_chat_model


# -- occasional reply feedback (2026-10-04) --


@pytest.mark.asyncio
async def test_feedback_is_asked_on_every_fifth_reply_and_not_again_within_three_days(
    db_session, monkeypatch
) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    replies = [await _send(db_session, monkeypatch, user, f"Ответ {i}") for i in range(10)]

    asked = [reply.feedback_requested for reply in replies]
    assert asked[4] is True  # 5th reply
    assert asked.count(True) == 1  # the 10th is within 3 days of the 5th


@pytest.mark.asyncio
async def test_feedback_is_saved_only_on_own_requested_reply(db_session, monkeypatch) -> None:
    user, stranger = _make_user(), _make_user()
    db_session.add_all([user, stranger])
    await db_session.flush()
    replies = [await _send(db_session, monkeypatch, user, f"Ответ {i}") for i in range(5)]
    requested, plain = replies[4], replies[0]
    service = CoachChatService(db_session)

    with pytest.raises(HTTPException):
        await service.set_feedback(stranger, requested.id, 1)
    with pytest.raises(HTTPException):
        await service.set_feedback(user, plain.id, 1)
    await service.set_feedback(user, requested.id, -1)

    stored = await db_session.get(CoachChatMessage, requested.id)
    assert stored.feedback == -1
