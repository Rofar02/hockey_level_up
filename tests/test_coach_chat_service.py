"""AI coach chat (CoachChatService / POST /users/me/coach-chat):

- require_premium gates access regardless of the Anthropic key state (403,
  key irrelevant -- mirrors test_premium_gate.py's convention, scoped to
  this feature).
- with premium access granted but no Anthropic key configured, the service
  itself refuses with 503 ("feature not technically on yet") rather than
  403 -- a different state than "no access at all".
- exceeding the monthly quota is a 429, and the Anthropic client is never
  called to get there.
- the system prompt actually carries the user's real stats/milestones/
  streak/phase/history, not a generic template.
- both turns (user + assistant) land in coach_chat_messages, retrievable
  via list_history in ascending order.

No real Anthropic call is ever made -- `_call_anthropic` is monkeypatched
at the module level in every test that reaches it, same convention
test_push_subscription.py uses for webpush_async.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.models.coach_chat import CoachChatMessage, CoachChatRole
from app.models.exercise import TargetStat
from app.models.progress import StatHistory, TrainingStreak, UserStat
from app.models.schedule import BlockPhase, TrainingBlock
from app.models.skill import Skill, SkillMilestone, SkillStatWeight
from app.models.user import User
from app.routers.deps import require_premium
from app.services import coach_chat_service
from app.services.coach_chat_service import MONTHLY_MESSAGE_LIMIT, CoachChatService


def _make_user(*, has_premium: bool = True) -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"coach_{unique}",
        email=f"coach_{unique}@example.com",
        password_hash="irrelevant",
        has_premium=has_premium,
    )


def _settings_with_key(api_key: str | None) -> Settings:
    return Settings(anthropic_api_key=api_key)


def _install_fake_call(monkeypatch, *, reply: str = "Тестовый ответ тренера"):
    """Replaces the Anthropic call with a fake that records exactly what it
    was sent and returns a canned reply -- no network call, ever."""
    captured: dict = {}

    async def _fake_call_anthropic(api_key: str, system_prompt: str, messages: list[dict]) -> str:
        captured["api_key"] = api_key
        captured["system_prompt"] = system_prompt
        captured["messages"] = messages
        return reply

    monkeypatch.setattr(coach_chat_service, "_call_anthropic", _fake_call_anthropic)
    return captured


def _fail_if_called(monkeypatch):
    async def _boom(*_args, **_kwargs):
        raise AssertionError("Anthropic client must not be called")

    monkeypatch.setattr(coach_chat_service, "_call_anthropic", _boom)


# -- access gating --


@pytest.mark.asyncio
async def test_require_premium_blocks_regardless_of_anthropic_key() -> None:
    """require_premium never looks at settings -- a configured key changes
    nothing for a non-premium user, which is the point: 403 (no access at
    all) is a different failure than 503 (access granted, feature off)."""
    user = _make_user(has_premium=False)

    with pytest.raises(HTTPException) as exc_info:
        await require_premium(user)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_send_message_without_api_key_returns_503_even_for_premium_user(
    db_session, monkeypatch
) -> None:
    user = _make_user(has_premium=True)
    db_session.add(user)
    await db_session.flush()

    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: _settings_with_key(None))
    _fail_if_called(monkeypatch)

    service = CoachChatService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.send_message(user, "Привет!")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Функция скоро будет доступна"


# -- monthly quota --


@pytest.mark.asyncio
async def test_send_message_over_monthly_limit_returns_429_without_calling_anthropic(
    db_session, monkeypatch
) -> None:
    user = _make_user(has_premium=True)
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            CoachChatMessage(
                id=uuid.uuid4(),
                user_id=user.id,
                role=CoachChatRole.USER,
                content=f"message {i}",
                created_at=now,
            )
            for i in range(MONTHLY_MESSAGE_LIMIT)
        ]
    )
    await db_session.flush()

    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: _settings_with_key("test-key"))
    _fail_if_called(monkeypatch)

    service = CoachChatService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.send_message(user, "Ещё один вопрос")

    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_send_message_under_monthly_limit_succeeds(db_session, monkeypatch) -> None:
    user = _make_user(has_premium=True)
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            CoachChatMessage(
                id=uuid.uuid4(),
                user_id=user.id,
                role=CoachChatRole.USER,
                content=f"message {i}",
                created_at=now,
            )
            for i in range(MONTHLY_MESSAGE_LIMIT - 1)
        ]
    )
    await db_session.flush()

    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: _settings_with_key("test-key"))
    captured = _install_fake_call(monkeypatch)

    service = CoachChatService(db_session)
    reply = await service.send_message(user, "Последнее в этом месяце")

    assert reply.role == CoachChatRole.ASSISTANT
    assert captured["messages"][-1] == {"role": "user", "content": "Последнее в этом месяце"}


@pytest.mark.asyncio
async def test_messages_from_a_prior_month_do_not_count_toward_the_limit(
    db_session, monkeypatch
) -> None:
    user = _make_user(has_premium=True)
    db_session.add(user)
    await db_session.flush()

    last_month = datetime.now(timezone.utc) - timedelta(days=45)
    db_session.add_all(
        [
            CoachChatMessage(
                id=uuid.uuid4(),
                user_id=user.id,
                role=CoachChatRole.USER,
                content=f"old message {i}",
                created_at=last_month,
            )
            for i in range(MONTHLY_MESSAGE_LIMIT)
        ]
    )
    await db_session.flush()

    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: _settings_with_key("test-key"))
    _install_fake_call(monkeypatch)

    service = CoachChatService(db_session)
    # Should not raise -- last month's 150 messages are outside this
    # calendar month's window.
    await service.send_message(user, "Новый месяц, новый лимит")


# -- system prompt context assembly --


@pytest.mark.asyncio
async def test_system_prompt_carries_real_user_context(db_session, monkeypatch) -> None:
    user = _make_user(has_premium=True)
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(timezone.utc)

    # Current stats.
    db_session.add(
        UserStat(
            id=uuid.uuid4(),
            user_id=user.id,
            stat_type=TargetStat.STRENGTH,
            current_value=55.5,
            last_updated_at=now,
        )
    )

    # A skill close to its next milestone -- unique name so this never
    # collides with a real skill already seeded in the dev database (skill
    # names are globally unique; see uq on Skill.name).
    skill_name = f"Катание {uuid.uuid4().hex[:8]}"
    skill = Skill(id=uuid.uuid4(), name=skill_name, required_level=1)
    db_session.add(skill)
    await db_session.flush()
    db_session.add(SkillStatWeight(id=uuid.uuid4(), skill_id=skill.id, stat_type=TargetStat.STRENGTH, weight=1.0))
    db_session.add(
        SkillMilestone(
            id=uuid.uuid4(), skill_id=skill.id, threshold=56, title="Порог", description="test"
        )
    )

    # Streak.
    db_session.add(
        TrainingStreak(
            id=uuid.uuid4(), user_id=user.id, current_streak=7, longest_streak=10, last_activity_date=now.date()
        )
    )

    # Periodization phase, persisted directly (Phase 4).
    db_session.add(
        TrainingBlock(
            id=uuid.uuid4(), user_id=user.id, block_number=1, phase=BlockPhase.INTENSIFICATION
        )
    )

    # Recent StatHistory with a reason.
    db_session.add(
        StatHistory(
            id=uuid.uuid4(),
            user_id=user.id,
            stat_type=TargetStat.STRENGTH,
            value=55.5,
            recorded_at=now,
            reason="quest_completed",
        )
    )
    await db_session.flush()

    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: _settings_with_key("test-key"))
    captured = _install_fake_call(monkeypatch)

    service = CoachChatService(db_session)
    await service.send_message(user, "Как мне улучшить катание?")

    prompt = captured["system_prompt"]
    assert "55.5" in prompt  # current stat value
    assert skill_name in prompt and "0.5" in prompt  # skill name + points_remaining to threshold
    assert "7 дн. подряд" in prompt  # streak
    assert "интенсификация" in prompt  # periodization phase label
    assert "quest_completed" in prompt  # StatHistory reason
    # Guardrails must always be present.
    assert "врачу" in prompt
    assert "диагноз" in prompt.lower()
    assert "дозировк" in prompt.lower()


@pytest.mark.asyncio
async def test_system_prompt_replays_recent_dialogue_history(db_session, monkeypatch) -> None:
    user = _make_user(has_premium=True)
    db_session.add(user)
    await db_session.flush()

    # Explicit, strictly-increasing created_at -- two rows flushed together
    # can tie on the column's own wall-clock default (see
    # CoachChatRepository.add), which would make list_recent's ordering
    # nondeterministic here.
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            CoachChatMessage(
                id=uuid.uuid4(),
                user_id=user.id,
                role=CoachChatRole.USER,
                content="Первый вопрос",
                created_at=now,
            ),
            CoachChatMessage(
                id=uuid.uuid4(),
                user_id=user.id,
                role=CoachChatRole.ASSISTANT,
                content="Первый ответ",
                created_at=now + timedelta(microseconds=1),
            ),
        ]
    )
    await db_session.flush()

    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: _settings_with_key("test-key"))
    captured = _install_fake_call(monkeypatch)

    service = CoachChatService(db_session)
    await service.send_message(user, "Второй вопрос")

    assert captured["messages"] == [
        {"role": "user", "content": "Первый вопрос"},
        {"role": "assistant", "content": "Первый ответ"},
        {"role": "user", "content": "Второй вопрос"},
    ]


# -- persistence --


@pytest.mark.asyncio
async def test_send_message_persists_both_turns_and_history_returns_them_in_order(
    db_session, monkeypatch
) -> None:
    user = _make_user(has_premium=True)
    db_session.add(user)
    await db_session.flush()

    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: _settings_with_key("test-key"))
    _install_fake_call(monkeypatch, reply="Держись в темпе, всё получится.")

    service = CoachChatService(db_session)
    reply = await service.send_message(user, "Как настроиться на тренировку?")

    assert reply.role == CoachChatRole.ASSISTANT
    assert reply.content == "Держись в темпе, всё получится."

    history = await service.list_history(user.id, limit=50)
    assert [(entry.role, entry.content) for entry in history] == [
        (CoachChatRole.USER, "Как настроиться на тренировку?"),
        (CoachChatRole.ASSISTANT, "Держись в темпе, всё получится."),
    ]
    # Ascending order -- the first message really is the older one.
    assert history[0].created_at <= history[1].created_at
