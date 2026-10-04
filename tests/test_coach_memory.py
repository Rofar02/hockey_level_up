"""Coach memory ("заметки тренера", 2026-10-04): messages that leave the
replayed history window are summarized into short notes about the player
(CoachMemoryService), premium only, shown to the coach at the end of its
prompt and to the player in Settings. No real z.ai call -- _call_zai is faked.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import Settings
from app.models.coach_chat import CoachChatMessage, CoachChatRole
from app.models.coach_memory import CoachMemoryFact
from app.models.user import CoachPersonality, User
from app.services import coach_chat_service, coach_memory_service
from app.services.coach_chat_service import (
    HISTORY_REPLAY_TURNS,
    CoachChatService,
    ZaiReply,
)
from app.services.coach_memory_service import (
    MEMORY_MAX_FACTS,
    SUMMARIZE_BATCH,
    CoachMemoryService,
    _parse_facts,
)


def _make_user(*, has_premium: bool = True) -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"memory_{unique}",
        email=f"memory_{unique}@example.com",
        password_hash="irrelevant",
        has_premium=has_premium,
    )


def _add_messages(db_session, user: User, count: int, start: datetime | None = None) -> list[CoachChatMessage]:
    start = start or datetime.now(timezone.utc) - timedelta(days=1)
    messages = [
        CoachChatMessage(
            id=uuid.uuid4(),
            user_id=user.id,
            role=CoachChatRole.USER if index % 2 == 0 else CoachChatRole.ASSISTANT,
            content=f"сообщение {index}",
            created_at=start + timedelta(minutes=index),
        )
        for index in range(count)
    ]
    db_session.add_all(messages)
    return messages


def _install_summarizer(monkeypatch, reply_text: str) -> dict:
    captured: dict = {"calls": 0}

    async def _fake_call_zai(api_key, base_url, model, system_prompt, messages, tools=None) -> ZaiReply:
        captured["calls"] += 1
        captured["system_prompt"] = system_prompt
        captured["messages"] = messages
        return ZaiReply(text=reply_text)

    monkeypatch.setattr(coach_chat_service, "_call_zai", _fake_call_zai)
    monkeypatch.setattr(coach_memory_service, "get_settings", lambda: Settings(zai_api_key="test-key"))
    return captured


def test_history_window_is_twelve() -> None:
    assert HISTORY_REPLAY_TURNS == 12
    assert SUMMARIZE_BATCH == HISTORY_REPLAY_TURNS


def test_parse_facts_accepts_fenced_json_and_caps_count_and_length() -> None:
    raw = "```json\n" + json.dumps({"facts": ["  Защитник  ", "", 5] + ["x" * 500] * 30}) + "\n```"
    facts = _parse_facts(raw)
    assert facts is not None
    assert facts[0] == "Защитник"
    assert len(facts) == MEMORY_MAX_FACTS
    assert all(len(fact) <= coach_memory_service.FACT_MAX_CHARS for fact in facts)


def test_parse_facts_rejects_garbage() -> None:
    assert _parse_facts("не JSON") is None
    assert _parse_facts('{"facts": "строка"}') is None


@pytest.mark.asyncio
async def test_nothing_is_due_while_everything_fits_the_window(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    _add_messages(db_session, user, HISTORY_REPLAY_TURNS + SUMMARIZE_BATCH - 1)
    await db_session.flush()
    captured = _install_summarizer(monkeypatch, '{"facts": ["факт"]}')

    assert await CoachMemoryService(db_session).summarize(user) is False
    assert captured["calls"] == 0


@pytest.mark.asyncio
async def test_summarize_writes_notes_and_only_reads_messages_outside_the_window(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    _add_messages(db_session, user, HISTORY_REPLAY_TURNS + SUMMARIZE_BATCH)
    await db_session.flush()
    captured = _install_summarizer(monkeypatch, '{"facts": ["Защитник, 14 лет", "Не любит длинный бег"]}')

    service = CoachMemoryService(db_session)
    assert await service.summarize(user) is True

    assert [fact.text for fact in await service.list_facts(user.id)] == ["Защитник, 14 лет", "Не любит длинный бег"]
    transcript = captured["messages"][0]["content"]
    assert "сообщение 0" in transcript and f"сообщение {SUMMARIZE_BATCH - 1}" in transcript
    assert f"сообщение {SUMMARIZE_BATCH}\n" not in transcript  # still in the window
    # Marker moved to the last summarized message: nothing is due any more.
    assert await service.due_messages(user.id) == []


@pytest.mark.asyncio
async def test_next_pass_sees_current_notes_and_replaces_them(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    start = datetime.now(timezone.utc) - timedelta(days=2)
    _add_messages(db_session, user, HISTORY_REPLAY_TURNS + SUMMARIZE_BATCH, start=start)
    await db_session.flush()
    _install_summarizer(monkeypatch, '{"facts": ["Болит правое колено"]}')
    service = CoachMemoryService(db_session)
    await service.summarize(user)

    _add_messages(db_session, user, SUMMARIZE_BATCH, start=start + timedelta(hours=5))
    await db_session.flush()
    captured = _install_summarizer(monkeypatch, '{"facts": ["Колено прошло, врач разрешил нагрузку"]}')
    assert await service.summarize(user) is True

    assert "Болит правое колено" in captured["messages"][0]["content"]
    assert [fact.text for fact in await service.list_facts(user.id)] == ["Колено прошло, врач разрешил нагрузку"]


@pytest.mark.asyncio
async def test_unusable_summarizer_reply_changes_nothing(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    _add_messages(db_session, user, HISTORY_REPLAY_TURNS + SUMMARIZE_BATCH)
    await db_session.flush()
    _install_summarizer(monkeypatch, "извини, не могу")

    service = CoachMemoryService(db_session)
    assert await service.summarize(user) is False
    assert await service.list_facts(user.id) == []
    assert len(await service.due_messages(user.id)) == SUMMARIZE_BATCH  # retried next tick


@pytest.mark.asyncio
async def test_forget_all_clears_notes_and_skips_what_was_already_said(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    _add_messages(db_session, user, HISTORY_REPLAY_TURNS + SUMMARIZE_BATCH)
    db_session.add(CoachMemoryFact(user_id=user.id, text="Факт", position=0))
    await db_session.flush()

    service = CoachMemoryService(db_session)
    await service.forget_all(user.id)

    assert await service.list_facts(user.id) == []
    assert await service.due_messages(user.id) == []


@pytest.mark.asyncio
async def test_delete_fact_only_touches_own_notes(db_session) -> None:
    owner, stranger = _make_user(), _make_user()
    db_session.add_all([owner, stranger])
    await db_session.flush()
    fact = CoachMemoryFact(user_id=owner.id, text="Факт", position=0)
    db_session.add(fact)
    await db_session.flush()

    service = CoachMemoryService(db_session)
    assert await service.delete_fact(stranger.id, fact.id) is False
    assert await service.delete_fact(owner.id, fact.id) is True
    assert await service.list_facts(owner.id) == []


@pytest.mark.asyncio
async def test_users_due_is_premium_only_and_needs_a_full_batch(db_session) -> None:
    premium_due, premium_short, free_due = _make_user(), _make_user(), _make_user(has_premium=False)
    db_session.add_all([premium_due, premium_short, free_due])
    await db_session.flush()
    _add_messages(db_session, premium_due, HISTORY_REPLAY_TURNS + SUMMARIZE_BATCH)
    _add_messages(db_session, premium_short, HISTORY_REPLAY_TURNS + SUMMARIZE_BATCH - 1)
    _add_messages(db_session, free_due, HISTORY_REPLAY_TURNS + SUMMARIZE_BATCH)
    await db_session.flush()

    due_ids = {user.id for user in await CoachMemoryService(db_session).users_due(limit=1000)}

    assert premium_due.id in due_ids
    assert premium_short.id not in due_ids
    assert free_due.id not in due_ids


@pytest.mark.asyncio
async def test_coach_prompt_shows_notes_to_premium_players_only(db_session) -> None:
    premium, free = _make_user(), _make_user(has_premium=False)
    db_session.add_all([premium, free])
    await db_session.flush()
    db_session.add_all(
        [
            CoachMemoryFact(user_id=premium.id, text="Не любит длинный бег", position=0),
            CoachMemoryFact(user_id=free.id, text="Не любит длинный бег", position=0),
        ]
    )
    await db_session.flush()

    service = CoachChatService(db_session)
    premium_prompt = await service._build_system_prompt(premium, CoachPersonality.CALM)
    free_prompt = await service._build_system_prompt(free, CoachPersonality.CALM)

    assert "Заметки тренера об игроке" in premium_prompt
    assert premium_prompt.rstrip().endswith("- Не любит длинный бег")
    assert "Не любит длинный бег" not in free_prompt
