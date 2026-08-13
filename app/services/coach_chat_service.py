"""AI coach chat (POST /users/me/coach-chat). Gated by require_premium at
the router layer; this service adds a second, independent gate on top --
whether the feature is technically switched on at all (settings.anthropic_api_key
configured) -- which is why a premium user with no key configured still
gets a 503, not a 403 (see app/core/config.py's anthropic_api_key comment).

The Anthropic call itself is a plain module-level function (`_call_anthropic`,
mirroring push_service.send_push / webpush_async) so tests can monkeypatch
it and assert on exactly what was sent, with no real network call.
"""
import uuid
from datetime import datetime, timedelta, timezone

import anthropic
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.training_block import BlockPhase, get_phase
from app.models.coach_chat import CoachChatMessage, CoachChatRole
from app.models.exercise import TargetStat
from app.models.progress import StatHistory, UserStat
from app.models.user import User
from app.repositories.coach_chat_repository import CoachChatRepository
from app.repositories.progress_repository import ProgressRepository
from app.repositories.training_block_repository import TrainingBlockRepository
from app.schemas.coach_chat import CoachChatMessageRead
from app.services.skill_service import SkillService

MODEL = "claude-haiku-4-5-20251001"

MONTHLY_MESSAGE_LIMIT = 150
# How many prior turns get replayed back to Claude as dialogue context --
# a rolling window, not the full history (which the /history endpoint
# exposes separately, unbounded by this).
HISTORY_REPLAY_TURNS = 10

MAX_RESPONSE_TOKENS = 1024

TOP_MILESTONES_COUNT = 3
RECENT_HISTORY_COUNT = 5

STAT_LABELS: dict[TargetStat, str] = {
    TargetStat.STRENGTH: "Сила",
    TargetStat.AGILITY: "Ловкость",
    TargetStat.INTELLECT: "Интеллект",
    TargetStat.ENDURANCE: "Выносливость",
    TargetStat.ON_ICE_SKATING: "Скорость на льду",
    TargetStat.PUCK_HANDLING: "Владение шайбой",
}

PHASE_LABELS: dict[BlockPhase, str] = {
    BlockPhase.ACCUMULATION: "накопление",
    BlockPhase.INTENSIFICATION: "интенсификация",
    BlockPhase.DELOAD: "разгрузка",
}

SYSTEM_PROMPT_GUARDRAILS = (
    "Ограничения: ты тренер по физической подготовке хоккеиста, а не врач. "
    "Никогда не ставь медицинские диагнозы и не интерпретируй симптомы. "
    "Если пользователь жалуется на боль, травму или плохое самочувствие -- "
    "прямо порекомендуй обратиться к врачу или спортивному врачу и не давай "
    "тренировочных советов по этому поводу, пока травма не будет осмотрена "
    "специалистом. Никогда не советуй конкретные лекарства, БАДы или их "
    "дозировки. Оставайся в рамках тренировочных рекомендаций: нагрузка, "
    "техника, периодизация, восстановление, мотивация."
)


def _format_stats_section(stats: list[UserStat]) -> str:
    if not stats:
        return "Текущие характеристики: данных пока нет."
    parts = [
        f"{STAT_LABELS.get(stat.stat_type, stat.stat_type.value)}: {stat.current_value:.1f}"
        for stat in stats
    ]
    return "Текущие характеристики: " + "; ".join(parts) + "."


def _format_milestones_section(entries: list[tuple[str, float, int]]) -> str:
    if not entries:
        return "Ближайшие пороги навыков: нет активных порогов."
    parts = [
        f"{name} (осталось {points_remaining:.1f} до порога {threshold})"
        for name, points_remaining, threshold in entries
    ]
    return "Ближайшие пороги навыков (топ-3): " + "; ".join(parts) + "."


def _format_streak_section(current_streak: int) -> str:
    return f"Текущий стрик тренировок: {current_streak} дн. подряд."


def _format_phase_section(phase: BlockPhase | None, week_in_block: int | None) -> str:
    if phase is None:
        return "Фаза периодизации: блок ещё не начат."
    label = PHASE_LABELS.get(phase, phase.value)
    return f"Фаза периодизации: {label} (неделя {week_in_block} из блока)."


def _format_history_section(entries: list[StatHistory]) -> str:
    if not entries:
        return "Последние изменения характеристик: нет записей."
    parts = [
        f"{entry.recorded_at.date().isoformat()} "
        f"{STAT_LABELS.get(entry.stat_type, entry.stat_type.value)} -> {entry.value:.1f} "
        f"({entry.reason})"
        for entry in entries
    ]
    return "Последние изменения характеристик: " + "; ".join(parts) + "."


async def _call_anthropic(
    api_key: str, system_prompt: str, messages: list[dict[str, str]]
) -> str:
    client = anthropic.AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model=MODEL,
        max_tokens=MAX_RESPONSE_TOKENS,
        system=system_prompt,
        messages=messages,
    )
    return next((block.text for block in response.content if block.type == "text"), "")


class CoachChatService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._chat = CoachChatRepository(session)
        self._progress = ProgressRepository(session)
        self._training_blocks = TrainingBlockRepository(session)
        self._skills = SkillService(session)

    async def send_message(self, user: User, message: str) -> CoachChatMessageRead:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Функция скоро будет доступна",
            )

        month_start = datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        sent_this_month = await self._chat.count_user_messages_since(user.id, month_start)
        if sent_this_month >= MONTHLY_MESSAGE_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Достигнут лимит сообщений ИИ-тренеру на этот месяц "
                    f"({MONTHLY_MESSAGE_LIMIT}). Попробуйте в следующем месяце."
                ),
            )

        system_prompt = await self._build_system_prompt(user)
        history = await self._chat.list_recent(user.id, HISTORY_REPLAY_TURNS)
        api_messages = [{"role": entry.role.value, "content": entry.content} for entry in history]
        api_messages.append({"role": "user", "content": message})

        reply_text = await _call_anthropic(settings.anthropic_api_key, system_prompt, api_messages)

        # Explicit, strictly-increasing timestamps for the two rows --
        # they're inserted in the same transaction, and relying on the
        # column's own wall-clock default for tie-breaking is not safe on
        # a coarse-resolution system clock (see CoachChatRepository.add).
        turn_time = datetime.now(timezone.utc)
        self._chat.add(user.id, CoachChatRole.USER, message, created_at=turn_time)
        assistant_message = self._chat.add(
            user.id,
            CoachChatRole.ASSISTANT,
            reply_text,
            created_at=turn_time + timedelta(microseconds=1),
        )
        await self._session.commit()
        await self._session.refresh(assistant_message)
        return CoachChatMessageRead.model_validate(assistant_message)

    async def list_history(self, user_id: uuid.UUID, limit: int) -> list[CoachChatMessageRead]:
        entries = await self._chat.list_recent(user_id, limit)
        return [CoachChatMessageRead.model_validate(entry) for entry in entries]

    async def _build_system_prompt(self, user: User) -> str:
        now = datetime.now(timezone.utc)

        stats = await self._progress.list_user_stats(user.id)
        stats_section = _format_stats_section(stats)

        skills = await self._skills.list_skills_for_user(user.id)
        milestone_entries = sorted(
            (
                (skill.name, skill.next_milestone.points_remaining, skill.next_milestone.threshold)
                for skill in skills
                if skill.next_milestone is not None
            ),
            key=lambda entry: entry[1],
        )[:TOP_MILESTONES_COUNT]
        milestones_section = _format_milestones_section(milestone_entries)

        streak = await self._progress.get_streak(user.id)
        streak_section = _format_streak_section(streak.current_streak if streak is not None else 0)

        block = await self._training_blocks.get_active_for_user(user.id)
        phase = get_phase(block.week_in_block) if block is not None else None
        phase_section = _format_phase_section(phase, block.week_in_block if block is not None else None)

        recent_history = await self._progress.list_recent_history(user.id, RECENT_HISTORY_COUNT)
        history_section = _format_history_section(recent_history)

        return (
            "Ты -- персональный AI-тренер по хоккею в приложении IceLevel. "
            "Отвечай по-русски, по делу, дружелюбно и кратко. Используй приведённую "
            "ниже сводку данных пользователя, чтобы давать конкретные, персональные "
            "советы по тренировкам, а не общие фразы.\n\n"
            f"Сводка данных пользователя (на {now.date().isoformat()}):\n"
            f"{stats_section}\n"
            f"{milestones_section}\n"
            f"{streak_section}\n"
            f"{phase_section}\n"
            f"{history_section}\n\n"
            f"{SYSTEM_PROMPT_GUARDRAILS}"
        )
