"""AI coach chat (CoachChatService / POST /users/me/coach-chat):

- 2026-09-17 (audit item #7): the router no longer gates this endpoint on
  require_premium at all -- every logged-in user reaches send_message,
  which applies its own monthly cap: FREE_TRIAL_MESSAGE_LIMIT for
  has_premium=False, the much larger MONTHLY_MESSAGE_LIMIT for True. The
  require_premium test below now just exercises that dependency function
  directly (mirrors test_premium_gate.py's convention) -- it's kept
  because the function itself still exists and still gates analytics, not
  because this endpoint still calls it.
- with access granted but no z.ai key configured, the service itself
  refuses with 503 ("feature not technically on yet") rather than a hard
  block -- a different state than "no messages left this month".
- exceeding the monthly quota (either tier) is a 429, and the z.ai client
  is never called to get there.
- the system prompt actually carries the user's real stats/milestones/
  streak/phase/history, not a generic template.
- the system prompt's persona block changes with the user's
  coach_personality, while the data-summary/guardrails part stays intact
  regardless.
- both turns (user + assistant) land in coach_chat_messages, retrievable
  via list_history in ascending order.

No real z.ai call is ever made -- `_call_zai` is
monkeypatched at the module level in every test that reaches it, same
convention test_push_subscription.py uses for webpush_async.
"""
import logging
import uuid
from datetime import date, datetime, timedelta, timezone

import httpx2
import pytest
from fastapi import HTTPException
from openai import APIConnectionError, APIError, APITimeoutError, AuthenticationError, RateLimitError

from app.core.config import Settings
from app.models.coach_chat import CoachChatMessage, CoachChatRole
from app.models.exercise import Exercise, ExerciseCategory, MovementPattern, TargetStat, TrainingPhase
from app.models.progress import StatHistory, TrainingStreak, UserStat
from app.models.schedule import BlockPhase, DayPlan, DaySessionType, TrainingBlock, TrainingSession, WeeklyPlan
from app.models.skill import Skill, SkillMilestone, SkillStatWeight, SkillTag, UserSkillPreference
from app.models.training_diary import TrainingDiaryEntry
from app.models.user import CoachPersonality, User
from app.models.user_temporary_restriction import UserTemporaryRestriction
from app.routers.deps import require_premium
from app.services import coach_chat_service
from app.services.coach_chat_service import (
    ANALYTICS_SUMMARY_WINDOW_DAYS,
    COACH_UNAVAILABLE_DETAIL,
    FREE_TRIAL_MESSAGE_LIMIT,
    MONTHLY_MESSAGE_LIMIT,
    CoachChatService,
    _call_zai,
)
from app.services.coach_personality_prompts import PERSONALITY_SYSTEM_PROMPTS


def _make_user(*, has_premium: bool = True, coach_personality: CoachPersonality | None = None) -> User:
    unique = uuid.uuid4().hex[:8]
    kwargs = {}
    if coach_personality is not None:
        kwargs["coach_personality"] = coach_personality
    return User(
        id=uuid.uuid4(),
        username=f"coach_{unique}",
        email=f"coach_{unique}@example.com",
        password_hash="irrelevant",
        has_premium=has_premium,
        **kwargs,
    )


def _settings_with_key(api_key: str | None) -> Settings:
    return Settings(zai_api_key=api_key)


def _install_fake_call(monkeypatch, *, reply: str = "Тестовый ответ тренера"):
    """Replaces the z.ai call with a fake that records exactly what
    it was sent and returns a canned reply -- no network call, ever."""
    captured: dict = {}

    async def _fake_call_zai(
        api_key: str, base_url: str, model: str, system_prompt: str, messages: list[dict]
    ) -> str:
        captured["api_key"] = api_key
        captured["base_url"] = base_url
        captured["model"] = model
        captured["system_prompt"] = system_prompt
        captured["messages"] = messages
        return reply

    monkeypatch.setattr(coach_chat_service, "_call_zai", _fake_call_zai)
    return captured


def _fail_if_called(monkeypatch):
    async def _boom(*_args, **_kwargs):
        raise AssertionError("z.ai client must not be called")

    monkeypatch.setattr(coach_chat_service, "_call_zai", _boom)


# -- access gating --


@pytest.mark.asyncio
async def test_require_premium_blocks_regardless_of_zai_key() -> None:
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
async def test_send_message_over_monthly_limit_returns_429_without_calling_zai(
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


@pytest.mark.asyncio
async def test_non_premium_user_hits_the_free_trial_limit_not_the_premium_one(
    db_session, monkeypatch
) -> None:
    """2026-09-17 (audit item #7): a non-premium user is capped at
    FREE_TRIAL_MESSAGE_LIMIT, far below MONTHLY_MESSAGE_LIMIT -- and the
    request never even reaches z.ai once the cap is hit, same as the
    premium 429 case above."""
    user = _make_user(has_premium=False)
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
            for i in range(FREE_TRIAL_MESSAGE_LIMIT)
        ]
    )
    await db_session.flush()

    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: _settings_with_key("test-key"))
    _fail_if_called(monkeypatch)

    service = CoachChatService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.send_message(user, "Ещё один вопрос")

    assert exc_info.value.status_code == 429
    assert "премиум" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_non_premium_user_under_the_free_trial_limit_succeeds(db_session, monkeypatch) -> None:
    user = _make_user(has_premium=False)
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
            for i in range(FREE_TRIAL_MESSAGE_LIMIT - 1)
        ]
    )
    await db_session.flush()

    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: _settings_with_key("test-key"))
    captured = _install_fake_call(monkeypatch)

    service = CoachChatService(db_session)
    reply = await service.send_message(user, "Последний бесплатный вопрос")

    assert reply.role == CoachChatRole.ASSISTANT
    assert captured["messages"][-1] == {"role": "user", "content": "Последний бесплатный вопрос"}


@pytest.mark.asyncio
async def test_premium_user_is_not_capped_by_the_free_trial_limit(db_session, monkeypatch) -> None:
    """A premium user who has already sent more than FREE_TRIAL_MESSAGE_
    LIMIT messages this month must still succeed -- has_premium picks the
    much larger MONTHLY_MESSAGE_LIMIT, not the free-trial one."""
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
            for i in range(FREE_TRIAL_MESSAGE_LIMIT + 5)
        ]
    )
    await db_session.flush()

    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: _settings_with_key("test-key"))
    _install_fake_call(monkeypatch)

    service = CoachChatService(db_session)
    # Should not raise -- well past the free-trial cap, nowhere near the
    # premium one.
    await service.send_message(user, "Премиум продолжает работать")


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
    assert "7 дн. подряд" in prompt  # current streak
    assert "лучший за всё время: 10 дн." in prompt  # longest streak (season memory)
    assert "интенсификация" in prompt  # periodization phase label
    assert "блок 1" in prompt  # block number (season memory)
    assert "quest_completed" in prompt  # StatHistory reason
    # Guardrails must always be present.
    assert "врачу" in prompt
    assert "диагноз" in prompt.lower()
    assert "дозировк" in prompt.lower()


@pytest.mark.asyncio
async def test_system_prompt_persona_follows_the_users_coach_personality(
    db_session, monkeypatch
) -> None:
    """Each CoachPersonality gets a distinct persona block up front, while
    the data-summary/guardrails assembly underneath it is unaffected --
    same UserStat/streak/phase machinery test_system_prompt_carries_real_
    user_context already covers, just checked here for two different
    personalities to prove it isn't personality-specific."""
    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: _settings_with_key("test-key"))

    prompts_by_personality: dict[CoachPersonality, str] = {}
    for personality in (CoachPersonality.STRICT, CoachPersonality.VIBE):
        user = _make_user(coach_personality=personality)
        db_session.add(user)
        await db_session.flush()

        captured = _install_fake_call(monkeypatch)
        service = CoachChatService(db_session)
        await service.send_message(user, "Как настроиться на тренировку?")
        prompts_by_personality[personality] = captured["system_prompt"]

    strict_prompt = prompts_by_personality[CoachPersonality.STRICT]
    vibe_prompt = prompts_by_personality[CoachPersonality.VIBE]

    # Each prompt opens with its own persona text, and not the other one's.
    assert strict_prompt.startswith(PERSONALITY_SYSTEM_PROMPTS[CoachPersonality.STRICT])
    assert vibe_prompt.startswith(PERSONALITY_SYSTEM_PROMPTS[CoachPersonality.VIBE])
    assert PERSONALITY_SYSTEM_PROMPTS[CoachPersonality.VIBE] not in strict_prompt
    assert PERSONALITY_SYSTEM_PROMPTS[CoachPersonality.STRICT] not in vibe_prompt

    # The rest of the assembly (data summary + guardrails) is identical
    # between the two prompts regardless of personality -- both users are
    # freshly created with no UserStat/TrainingStreak/TrainingBlock/
    # StatHistory rows, so every per-user section falls back the same way
    # for both (milestones aren't "no data" here -- see
    # test_system_prompt_carries_real_user_context's own comment: the
    # catalog's seeded skills always have a next milestone, even at zero
    # stats -- which is exactly why this compares the two prompts to each
    # other rather than hardcoding that section's text).
    for prompt in (strict_prompt, vibe_prompt):
        assert "Сводка данных пользователя" in prompt
        assert "Текущие характеристики: данных пока нет." in prompt
        assert "Текущий стрик тренировок: 0 дн. подряд (лучший за всё время: 0 дн.)." in prompt
        assert "Фаза периодизации: блок ещё не начат." in prompt
        assert "Последние изменения характеристик: нет записей." in prompt
        assert "врачу" in prompt

    def _strip_persona(prompt: str, personality: CoachPersonality) -> str:
        return prompt.removeprefix(PERSONALITY_SYSTEM_PROMPTS[personality])

    assert _strip_persona(strict_prompt, CoachPersonality.STRICT) == _strip_persona(
        vibe_prompt, CoachPersonality.VIBE
    )


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


# -- extended context: restrictions, diary, upcoming session --


async def _add_on_ice_day(
    db_session, user: User, *, on_date: date, week_start: date, main_exercise_names: list[str] | None = None
) -> TrainingSession:
    """Same bypass-ScheduleService shape as other test files' helpers
    (e.g. test_training_block_progression.py's _complete_real_session) --
    only the real DayPlan/TrainingSession/SessionBlock graph matters here,
    not how ScheduleService would have assembled it."""
    from app.models.schedule import SessionBlock

    blocks = []
    for name in main_exercise_names or []:
        exercise = Exercise(
            id=uuid.uuid4(), name=name, category=ExerciseCategory.ON_ICE,
            phase=TrainingPhase.MAIN, difficulty_level=1,
        )
        db_session.add(exercise)
        await db_session.flush()
        blocks.append(SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=len(blocks)))

    training_session = TrainingSession(id=uuid.uuid4(), blocks=blocks)
    weekly_plan = WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=week_start)
    weekly_plan.day_plans.append(
        DayPlan(id=uuid.uuid4(), date=on_date, session_type=DaySessionType.ON_ICE, training_session=training_session)
    )
    db_session.add(weekly_plan)
    await db_session.flush()
    return training_session


@pytest.mark.asyncio
async def test_system_prompt_includes_active_restriction(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    db_session.add(
        UserTemporaryRestriction(
            id=uuid.uuid4(),
            user_id=user.id,
            movement_pattern=MovementPattern.SHOULDER_MOBILITY,
            reason="побаливает плечо",
            expires_at=date.today() + timedelta(days=10),
        )
    )
    await db_session.flush()

    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: _settings_with_key("test-key"))
    captured = _install_fake_call(monkeypatch)

    service = CoachChatService(db_session)
    await service.send_message(user, "Как тренироваться сегодня?")

    prompt = captured["system_prompt"]
    assert "Мобильность плечевого пояса" in prompt
    assert "побаливает плечо" in prompt


@pytest.mark.asyncio
async def test_system_prompt_includes_recent_diary_entries_capped_and_notes_only(
    db_session, monkeypatch
) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    # 4 entries with notes (only the 3 most recent -- DIARY_ENTRIES_IN_PROMPT
    # -- should appear) + 1 with no note at all (must never appear).
    week_base = date(2020, 1, 6)
    for i in range(4):
        session = await _add_on_ice_day(
            db_session, user, on_date=date(2020, 1, 1) + timedelta(days=i), week_start=week_base + timedelta(weeks=i)
        )
        db_session.add(
            TrainingDiaryEntry(id=uuid.uuid4(), user_id=user.id, training_session_id=session.id, note=f"заметка{i}")
        )
    no_note_session = await _add_on_ice_day(
        db_session, user, on_date=date(2020, 2, 1), week_start=week_base + timedelta(weeks=10)
    )
    db_session.add(
        TrainingDiaryEntry(id=uuid.uuid4(), user_id=user.id, training_session_id=no_note_session.id, note=None)
    )
    await db_session.flush()

    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: _settings_with_key("test-key"))
    captured = _install_fake_call(monkeypatch)

    service = CoachChatService(db_session)
    await service.send_message(user, "Как прошла последняя тренировка?")

    prompt = captured["system_prompt"]
    # Most recent 3 (i=1,2,3 -- newest first per list_for_user's own
    # ordering) present, oldest (i=0) dropped by the DIARY_ENTRIES_IN_PROMPT cap.
    assert "заметка1" in prompt
    assert "заметка2" in prompt
    assert "заметка3" in prompt
    assert "заметка0" not in prompt


@pytest.mark.asyncio
async def test_system_prompt_includes_todays_session_when_it_exists(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    today = date.today()
    await _add_on_ice_day(
        db_session, user, on_date=today, week_start=today - timedelta(days=today.weekday()),
        main_exercise_names=["Слалом с шайбой"],
    )

    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: _settings_with_key("test-key"))
    captured = _install_fake_call(monkeypatch)

    service = CoachChatService(db_session)
    await service.send_message(user, "Что у меня сегодня?")

    prompt = captured["system_prompt"]
    assert "Сегодня: Лёд, тренировка ещё не начата" in prompt
    assert "Слалом с шайбой" in prompt
    # Today itself still has unstarted work -- no "next session" line
    # should be fetched/shown, that question isn't relevant yet.
    assert "Ближайшая предстоящая тренировка" not in prompt


@pytest.mark.asyncio
async def test_system_prompt_falls_back_to_next_real_session_when_today_has_none(
    db_session, monkeypatch
) -> None:
    """No DayPlan at all for today (e.g. an undeclared week) -- must look
    ahead rather than reporting nothing, same as a user opening the app
    today would see on the Week screen."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    today = date.today()
    upcoming_date = today + timedelta(days=3)
    await _add_on_ice_day(
        db_session, user, on_date=upcoming_date, week_start=today - timedelta(days=today.weekday()),
        main_exercise_names=["Катание на скорость"],
    )

    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: _settings_with_key("test-key"))
    captured = _install_fake_call(monkeypatch)

    service = CoachChatService(db_session)
    await service.send_message(user, "Что у меня дальше по плану?")

    prompt = captured["system_prompt"]
    assert upcoming_date.isoformat() in prompt
    assert "Катание на скорость" in prompt


@pytest.mark.asyncio
async def test_system_prompt_shows_todays_session_as_completed_and_finds_next(
    db_session, monkeypatch
) -> None:
    """The coach previously couldn't tell "already trained today" from
    "still to come" at all (found 2026-09-14, live use) -- this is the
    concrete regression case: every block today is done, so the coach
    should say so AND look ahead for what's next, instead of repeating
    today's already-finished exercise list as if it were still pending."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    today_session = await _add_on_ice_day(
        db_session, user, on_date=today, week_start=week_start,
        main_exercise_names=["Слалом с шайбой"],
    )
    for block in today_session.blocks:
        block.completed_at = datetime.now(timezone.utc)
    await db_session.flush()

    next_date = today + timedelta(days=2)
    await _add_on_ice_day(
        db_session, user, on_date=next_date, week_start=week_start + timedelta(weeks=1),
        main_exercise_names=["Катание на скорость"],
    )

    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: _settings_with_key("test-key"))
    captured = _install_fake_call(monkeypatch)

    service = CoachChatService(db_session)
    await service.send_message(user, "Как прошла сегодняшняя тренировка?")

    prompt = captured["system_prompt"]
    assert "Сегодня: Лёд, тренировка завершена" in prompt
    assert f"Ближайшая предстоящая тренировка: {next_date.isoformat()}" in prompt
    assert "Катание на скорость" in prompt


@pytest.mark.asyncio
async def test_system_prompt_shows_todays_session_in_progress(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    today = date.today()
    today_session = await _add_on_ice_day(
        db_session, user, on_date=today, week_start=today - timedelta(days=today.weekday()),
        main_exercise_names=["Слалом с шайбой", "Броски по воротам"],
    )
    today_session.blocks[0].completed_at = datetime.now(timezone.utc)
    await db_session.flush()

    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: _settings_with_key("test-key"))
    captured = _install_fake_call(monkeypatch)

    service = CoachChatService(db_session)
    await service.send_message(user, "Как у меня дела сегодня?")

    prompt = captured["system_prompt"]
    assert "Сегодня: Лёд, тренировка в процессе (1 из 2 упражнений)" in prompt


@pytest.mark.asyncio
async def test_system_prompt_shows_rest_day_and_finds_next_session(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    weekly_plan = WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=week_start)
    weekly_plan.day_plans.append(
        DayPlan(id=uuid.uuid4(), date=today, session_type=DaySessionType.REST)
    )
    db_session.add(weekly_plan)
    await db_session.flush()

    next_date = today + timedelta(days=1)
    await _add_on_ice_day(
        db_session, user, on_date=next_date, week_start=week_start + timedelta(weeks=1),
        main_exercise_names=["Катание на скорость"],
    )

    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: _settings_with_key("test-key"))
    captured = _install_fake_call(monkeypatch)

    service = CoachChatService(db_session)
    await service.send_message(user, "Что сегодня?")

    prompt = captured["system_prompt"]
    assert "Сегодня: день отдыха." in prompt
    assert f"Ближайшая предстоящая тренировка: {next_date.isoformat()}" in prompt


@pytest.mark.asyncio
async def test_system_prompt_includes_analytics_summary(db_session, monkeypatch) -> None:
    """AnalyticsService.get_summary is the exact same data
    AnalyticsPage.tsx itself shows -- this only checks it actually reaches
    the prompt with the real computed delta, not AnalyticsService's own
    selection logic (already covered by test_analytics_summary.py)."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=ANALYTICS_SUMMARY_WINDOW_DAYS)

    # STRENGTH: 50 -> 80 (+30, well outside the baseline window so it
    # doesn't get clamped) -- the only stat with any data, so it's
    # guaranteed to be top_gainer.
    db_session.add_all(
        [
            StatHistory(
                id=uuid.uuid4(),
                user_id=user.id,
                stat_type=TargetStat.STRENGTH,
                value=50.0,
                recorded_at=since - timedelta(days=1),
                reason="baseline",
            ),
            UserStat(
                id=uuid.uuid4(),
                user_id=user.id,
                stat_type=TargetStat.STRENGTH,
                current_value=80.0,
                last_updated_at=now,
            ),
        ]
    )
    await db_session.flush()

    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: _settings_with_key("test-key"))
    captured = _install_fake_call(monkeypatch)

    service = CoachChatService(db_session)
    await service.send_message(user, "Как мои успехи?")

    prompt = captured["system_prompt"]
    assert f"Аналитика за {ANALYTICS_SUMMARY_WINDOW_DAYS} дн." in prompt
    assert "Сила" in prompt
    assert "+30.0" in prompt


# -- season memory + "why this workout" (2026-09-14) --


@pytest.mark.asyncio
async def test_system_prompt_notes_macrocycle_deload(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    db_session.add(
        TrainingBlock(
            id=uuid.uuid4(),
            user_id=user.id,
            block_number=4,
            phase=BlockPhase.DELOAD,
            is_macrocycle_deload=True,
        )
    )
    await db_session.flush()

    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: _settings_with_key("test-key"))
    captured = _install_fake_call(monkeypatch)

    service = CoachChatService(db_session)
    await service.send_message(user, "Что сегодня?")

    prompt = captured["system_prompt"]
    assert "блок 4" in prompt
    assert "восстановительный макроцикл" in prompt


@pytest.mark.asyncio
async def test_system_prompt_includes_resolved_restriction_history(db_session, monkeypatch) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    db_session.add(
        UserTemporaryRestriction(
            id=uuid.uuid4(),
            user_id=user.id,
            movement_pattern=MovementPattern.SHOULDER_MOBILITY,
            expires_at=date.today() - timedelta(days=5),  # already expired -- resolved, not active
        )
    )
    await db_session.flush()

    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: _settings_with_key("test-key"))
    captured = _install_fake_call(monkeypatch)

    service = CoachChatService(db_session)
    await service.send_message(user, "Как дела с плечом?")

    prompt = captured["system_prompt"]
    assert "История прошлых ограничений" in prompt
    assert "Мобильность плечевого пояса" in prompt
    assert "истекло по сроку" in prompt


@pytest.mark.asyncio
async def test_system_prompt_includes_priority_skill_focus_for_upcoming_session(
    db_session, monkeypatch
) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    skill_name = f"Навык {uuid.uuid4().hex[:8]}"
    skill = Skill(id=uuid.uuid4(), name=skill_name, required_level=1)
    db_session.add(skill)
    await db_session.flush()
    db_session.add(UserSkillPreference(user_id=user.id, skill_id=skill.id))

    today = date.today()
    session = await _add_on_ice_day(
        db_session,
        user,
        on_date=today,
        week_start=today - timedelta(days=today.weekday()),
        main_exercise_names=["Тестовое упражнение"],
    )
    db_session.add(
        SkillTag(
            id=uuid.uuid4(),
            exercise_id=session.blocks[0].exercise_id,
            skill_id=skill.id,
            transfer_note="test",
        )
    )
    await db_session.flush()

    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: _settings_with_key("test-key"))
    captured = _install_fake_call(monkeypatch)

    service = CoachChatService(db_session)
    await service.send_message(user, "Почему сегодня такая тренировка?")

    prompt = captured["system_prompt"]
    assert "приоритетные навыки игрока" in prompt
    assert skill_name in prompt


# -- _call_zai's own error handling (2026-09-18, round 2 audit item #4) --
#
# client.chat.completions.create used to go completely unwrapped: any
# openai-client exception (expired key, exhausted quota, an invalid
# configured model name, a timeout, ...) reached the caller raw, and with
# no global exception handler in app/main.py, Starlette's default plain-
# text 500 response reached the frontend (which expects JSON) as an
# opaque "Request failed". These tests exercise _call_zai directly (not
# through send_message -- it's the function under test) with a fake
# AsyncOpenAI client whose chat.completions.create raises each real
# openai-client exception type, and check both halves of the fix: the
# HTTPException the caller actually sees, and that the real exception
# was logged, not silently swallowed.

_FAKE_REQUEST = httpx2.Request("POST", "https://api.z.ai/v1/chat/completions")


def _install_broken_client(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    class _FakeCompletions:
        async def create(self, **_kwargs):
            raise error

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    monkeypatch.setattr(
        coach_chat_service, "AsyncOpenAI", lambda *, api_key, base_url: _FakeClient()
    )


async def _assert_call_zai_maps_to_unavailable(
    caplog: pytest.LogCaptureFixture, error: Exception
) -> None:
    with caplog.at_level(logging.ERROR, logger="app.services.coach_chat_service"):
        with pytest.raises(HTTPException) as exc_info:
            await _call_zai("test-key", "https://api.z.ai/v1", "glm-4.7-flash", "system", [])

    # 502, not 503 -- CoachPage.tsx already treats a 503 from this endpoint
    # as "feature not configured at all" (permanently swaps to a
    # ComingSoonCard, never shows the error text). A mid-flight z.ai
    # failure is a different situation and must not collide with that.
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == COACH_UNAVAILABLE_DETAIL

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelno == logging.ERROR
    # exc_info attached (not just the message) -- the real exception,
    # including its type and traceback, is what actually got logged.
    assert record.exc_info is not None
    assert record.exc_info[0] is type(error)


@pytest.mark.asyncio
async def test_call_zai_maps_rate_limit_error_to_502(monkeypatch, caplog) -> None:
    response = httpx2.Response(
        429, request=_FAKE_REQUEST, json={"error": {"message": "quota exceeded"}}
    )
    error = RateLimitError("quota exceeded", response=response, body=None)
    _install_broken_client(monkeypatch, error)

    await _assert_call_zai_maps_to_unavailable(caplog, error)


@pytest.mark.asyncio
async def test_call_zai_maps_authentication_error_to_502(monkeypatch, caplog) -> None:
    response = httpx2.Response(
        401, request=_FAKE_REQUEST, json={"error": {"message": "invalid api key"}}
    )
    error = AuthenticationError("invalid api key", response=response, body=None)
    _install_broken_client(monkeypatch, error)

    await _assert_call_zai_maps_to_unavailable(caplog, error)


@pytest.mark.asyncio
async def test_call_zai_maps_timeout_error_to_502(monkeypatch, caplog) -> None:
    error = APITimeoutError(request=_FAKE_REQUEST)
    _install_broken_client(monkeypatch, error)

    await _assert_call_zai_maps_to_unavailable(caplog, error)


@pytest.mark.asyncio
async def test_call_zai_maps_connection_error_to_502(monkeypatch, caplog) -> None:
    error = APIConnectionError(message="connection failed", request=_FAKE_REQUEST)
    _install_broken_client(monkeypatch, error)

    await _assert_call_zai_maps_to_unavailable(caplog, error)


@pytest.mark.asyncio
async def test_call_zai_maps_generic_api_error_to_502(monkeypatch, caplog) -> None:
    """Covers cases with no dedicated exception subclass, e.g. an invalid
    configured model name (settings.coach_chat_model pointing at something
    z.ai doesn't recognize) -- still just an APIError under the hood."""
    error = APIError("model not found", _FAKE_REQUEST, body=None)
    _install_broken_client(monkeypatch, error)

    await _assert_call_zai_maps_to_unavailable(caplog, error)


@pytest.mark.asyncio
async def test_call_zai_success_path_is_unaffected(monkeypatch, caplog) -> None:
    """Sanity check: the try/except wrapper doesn't swallow or alter a
    normal successful response."""
    class _FakeMessage:
        content = "Тестовый ответ"

    class _FakeChoice:
        message = _FakeMessage()

    class _FakeResponse:
        choices = [_FakeChoice()]

    class _FakeCompletions:
        async def create(self, **_kwargs):
            return _FakeResponse()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    monkeypatch.setattr(
        coach_chat_service, "AsyncOpenAI", lambda *, api_key, base_url: _FakeClient()
    )

    with caplog.at_level(logging.ERROR, logger="app.services.coach_chat_service"):
        result = await _call_zai("test-key", "https://api.z.ai/v1", "glm-4.7-flash", "system", [])

    assert result == "Тестовый ответ"
    assert caplog.records == []
