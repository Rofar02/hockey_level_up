"""AI coach chat (POST /users/me/coach-chat). Gated by require_premium at
the router layer; this service adds a second, independent gate on top --
whether the feature is technically switched on at all
(settings.zai_api_key configured) -- which is why a premium user with no
key configured still gets a 503, not a 403 (see app/core/config.py's
zai_api_key comment).

Zhipu AI's (z.ai) own OpenAI-compatible endpoint, called directly -- the
actual model is a setting (Settings.coach_chat_model), not hardcoded here,
so swapping models (e.g. to a paid "glm-5.3") is a config change, not a
code change. `openai`'s own client works against it unchanged -- z.ai's
endpoint is a drop-in Chat Completions API, just a different base_url and
API key.

(2026-08-31: tried OpenRouter first -- its Cloudflare edge hard-blocks
every request from this server's IP/ASN with a 403 "Access denied by
security policy" before it ever reaches OpenRouter's own app layer,
confirmed via OpenRouter support as an IP/ASN-reputation issue on their
Cloudflare config, reproducible even on an unauthenticated GET with curl.
z.ai isn't behind that edge and has no such restriction from here -- same
reason Qwen/DashScope was originally chosen over Anthropic/OpenAI
directly, before this file briefly went through OpenRouter. See git
history for the OpenRouter-specific code if that block ever gets resolved
and it's worth revisiting.)

The z.ai call itself is a plain module-level function (`_call_zai`,
mirroring push_service.send_push / webpush_async) so tests can monkeypatch
it and assert on exactly what was sent, with no real network call.
"""
import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.training_block import SESSIONS_TO_ADVANCE_PHASE
from app.models.coach_chat import CoachChatMessage, CoachChatRole
from app.models.coach_chat_proposed_action import (
    CoachActionStatus,
    CoachActionType,
    CoachChatProposedAction,
)
from app.models.exercise import MovementPattern, MuscleGroup, TargetStat
from app.models.progress import StatHistory, UserStat
from app.models.schedule import BlockPhase
from app.models.user import CoachPersonality, User
from app.repositories.coach_chat_proposed_action_repository import CoachChatProposedActionRepository
from app.repositories.coach_chat_repository import CoachChatRepository
from app.repositories.progress_repository import ProgressRepository
from app.schemas.coach_chat import CoachChatMessageRead, ProposedActionRead
from app.schemas.user import UserUpdate
from app.services.coach_personality_prompts import PERSONALITY_SYSTEM_PROMPTS
from app.services.skill_service import SkillService
from app.services.training_block_service import TrainingBlockService
from app.services.user_service import UserService
from app.services.user_temporary_restriction_service import UserTemporaryRestrictionService

MONTHLY_MESSAGE_LIMIT = 150
# How many prior messages get replayed back to the model as dialogue
# context -- a rolling window, not the full history (which the /history
# endpoint exposes separately, unbounded by this). Raised from 10 to 30
# (2026-09-14, deliberate) -- cost impact is negligible on the current
# free-tier model and stays small even on a future paid model (~15
# messages of real back-and-forth is a much more honest "memory" than 5).
HISTORY_REPLAY_TURNS = 30

# Generous on purpose: cheap insurance against a truncated reply, and
# glm-4.7-flash (the current default model) is free-tier, so there's no
# cost pressure to shrink it. Revisit if/when Settings.coach_chat_model
# switches to a paid reasoning model that spends part of this budget on
# hidden chain-of-thought before the visible reply.
MAX_RESPONSE_TOKENS = 2048

TOP_MILESTONES_COUNT = 3
RECENT_HISTORY_COUNT = 5

# Matches a trailing <!--ACTION:{...}--> marker the model emits to propose
# one action (see SYSTEM_PROMPT_GUARDRAILS's own instructions for the exact
# format) -- DOTALL so the JSON body can itself contain newlines, anchored
# to the end of the reply so it can't be confused with an example of the
# format appearing mid-explanation.
_ACTION_MARKER_RE = re.compile(r"<!--ACTION:(\{.*\})-->\s*$", re.DOTALL)

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

# Same Russian wording as frontend/src/types/exercise.ts's
# MOVEMENT_PATTERN_LABELS/MUSCLE_GROUP_LABELS (RestrictionsPage's own
# player-facing copy) -- used to build a human-readable proposed-action
# summary for REPORT_RESTRICTION, kept consistent with what the player
# would see if they reported the same restriction manually via Settings.
MOVEMENT_PATTERN_LABELS: dict[MovementPattern, str] = {
    MovementPattern.HIP_HINGE: "Хип-хиндж",
    MovementPattern.SQUAT: "Присед",
    MovementPattern.PUSH: "Толчок",
    MovementPattern.PULL: "Тяга",
    MovementPattern.ROTATION: "Ротация",
    MovementPattern.ANKLE_MOBILITY: "Мобильность голеностопа",
    MovementPattern.HIP_MOBILITY: "Мобильность таза",
    MovementPattern.SHOULDER_MOBILITY: "Мобильность плечевого пояса",
    MovementPattern.WRIST_MOBILITY: "Мобильность запястья",
    MovementPattern.CORE: "Кор",
    MovementPattern.LOCOMOTION: "Локомоция",
    MovementPattern.STICK_HANDLING: "Владение клюшкой",
    MovementPattern.COORDINATION: "Координация и реакция",
}

MUSCLE_GROUP_LABELS: dict[MuscleGroup, str] = {
    MuscleGroup.QUADS: "Квадрицепс",
    MuscleGroup.HAMSTRINGS: "Задняя поверхность бедра",
    MuscleGroup.GLUTES: "Ягодицы",
    MuscleGroup.CHEST: "Грудь",
    MuscleGroup.BACK: "Спина",
    MuscleGroup.SHOULDERS: "Плечи",
    MuscleGroup.CORE: "Кор",
    MuscleGroup.CALVES: "Икры",
    MuscleGroup.FOREARMS: "Предплечья",
}

SYSTEM_PROMPT_GUARDRAILS = (
    "Ограничения: ты тренер по физической подготовке хоккеиста, а не врач. "
    "Никогда не ставь медицинские диагнозы и не интерпретируй симптомы. "
    "Если пользователь жалуется на боль, травму или плохое самочувствие -- "
    "прямо порекомендуй обратиться к врачу или спортивному врачу и не давай "
    "тренировочных советов по этому поводу, пока травма не будет осмотрена "
    "специалистом. Никогда не советуй конкретные лекарства, БАДы или их "
    "дозировки. Оставайся в рамках тренировочных рекомендаций: нагрузка, "
    "техника, периодизация, восстановление, мотивация.\n\n"
    "Важно о том, что ты реально можешь: ты НЕ управляешь тренировочным "
    "планом пользователя и не можешь изменить его напрямую -- ты только "
    "читаешь его текущие данные (сводка выше) и разговариваешь. Ты не "
    "можешь добавить, убрать или заменить упражнение, изменить вес/повторы, "
    "пропустить или перенести тренировку, ускорить смену фазы "
    "периодизации -- всё это решает детерминированная система приложения, "
    "а не ты. Никогда не говори и не подразумевай фразы вроде \"я изменил "
    "твой план\", \"сделаю упражнения полегче\" или \"учту это в следующей "
    "тренировке\" -- это неправда, у тебя нет такой возможности технически.\n\n"
    "Но для трёх конкретных вещей у тебя есть возможность ПРЕДЛОЖИТЬ "
    "действие, которое реально применится -- только после того, как игрок "
    "сам явно подтвердит его в интерфейсе (кнопкой), никогда не молча. "
    "Никогда не говори, что уже сделал это, пока игрок не подтвердил. "
    "Формат: в самом конце ответа, отдельной строкой, добавь маркер "
    "вида <!--ACTION:{...}--> с JSON внутри -- игрок его не увидит, это "
    "техническая метка для приложения. Не больше одного маркера на ответ, "
    "и только когда ты действительно уверен, что это то, чего хочет игрок "
    "-- если неоднозначно (например жалоба может относиться к разным "
    "навыкам), сначала задай ОДИН уточняющий вопрос обычным текстом, без "
    "маркера, и предложи действие только следующим сообщением, когда "
    "станет ясно. Три допустимых действия:\n\n"
    "1. Добавить навык в приоритетные (когда игрок жалуется на конкретную "
    "игровую проблему, которая явно указывает на один навык из списка "
    "навыков игрока выше -- например \"часто отбирают шайбу под "
    "давлением\" ближе к Обводке, а \"выталкивают силой\" -- к Силовой "
    "борьбе): <!--ACTION:{\"type\":\"skill_priority_add\","
    "\"skill_name\":\"<точное название навыка из списка выше>\"}-->\n"
    "2. Установить дату турнира (когда игрок упоминает конкретную дату "
    "предстоящего турнира/матча, к которому готовится): "
    "<!--ACTION:{\"type\":\"set_tournament_date\","
    "\"tournament_date\":\"<ГГГГ-ММ-ДД>\"}-->\n"
    "3. Зарегистрировать временное ограничение (когда игрок сообщает, что "
    "что-то болит или дискомфортно прямо сейчас -- ЭТО НЕ ОТМЕНЯЕТ "
    "правило выше про рекомендацию обратиться к врачу, оба ответа "
    "уместны вместе): <!--ACTION:{\"type\":\"report_restriction\","
    "\"movement_pattern\":\"<значение из списка движений>\" ИЛИ "
    "\"muscle_group\":\"<значение из списка групп мышц>\" (ровно одно из "
    "двух, никогда оба),\"reason\":\"<кратко своими словами, необязательно>"
    "\"}-->\n\n"
    "Если ничего из этого не подходит -- просто отвечай текстом, без "
    "маркера. Если игрок просит что-то, что не входит в эти три действия "
    "(например переставить упражнение, снять навык, изменить нагрузку) -- "
    "объясни, что план строит сама система, и подскажи, где в приложении "
    "можно на это повлиять: временные ограничения и приоритетные навыки "
    "тоже можно менять напрямую в Настройках, не только через тебя."
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


def _format_phase_section(
    phase: BlockPhase | None, sessions_completed: int, sessions_to_advance: int
) -> str:
    if phase is None:
        return "Фаза периодизации: блок ещё не начат."
    label = PHASE_LABELS.get(phase, phase.value)
    return (
        f"Фаза периодизации: {label} "
        f"({sessions_completed} из {sessions_to_advance} тренировок до смены фазы)."
    )


def _build_action_summary(action_type: CoachActionType, payload: dict) -> str:
    """Player-facing text for the confirm card -- see ProposedActionRead."""
    if action_type is CoachActionType.SKILL_PRIORITY_ADD:
        return f"Добавить «{payload['skill_name']}» в приоритетные навыки?"
    if action_type is CoachActionType.SET_TOURNAMENT_DATE:
        parsed_date = date.fromisoformat(payload["tournament_date"])
        return f"Установить дату турнира: {parsed_date.strftime('%d.%m.%Y')}?"
    if action_type is CoachActionType.REPORT_RESTRICTION:
        movement_pattern = payload.get("movement_pattern")
        muscle_group = payload.get("muscle_group")
        if movement_pattern is not None:
            target_label = MOVEMENT_PATTERN_LABELS.get(MovementPattern(movement_pattern), movement_pattern)
        else:
            target_label = MUSCLE_GROUP_LABELS.get(MuscleGroup(muscle_group), muscle_group)
        return f"Записать временное ограничение: {target_label}?"
    return "Предложенное действие"


def _format_action_reference_section(skill_names: list[str]) -> str:
    """Real, current values the model must pick from when proposing an
    action -- never invent a skill name or an enum value that isn't listed
    here, since _resolve_action_payload only accepts an exact match."""
    skills_line = ", ".join(skill_names) if skill_names else "нет данных"
    patterns_line = ", ".join(
        f"{pattern.value} ({label})" for pattern, label in MOVEMENT_PATTERN_LABELS.items()
    )
    muscles_line = ", ".join(
        f"{group.value} ({label})" for group, label in MUSCLE_GROUP_LABELS.items()
    )
    return (
        "Справочные значения для маркеров действий (используй только их, "
        "не выдумывай):\n"
        f"Навыки игрока: {skills_line}.\n"
        f"Значения movement_pattern: {patterns_line}.\n"
        f"Значения muscle_group: {muscles_line}."
    )


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


async def _call_zai(
    api_key: str, base_url: str, model: str, system_prompt: str, messages: list[dict[str, str]]
) -> str:
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    response = await client.chat.completions.create(
        model=model,
        max_tokens=MAX_RESPONSE_TOKENS,
        messages=[{"role": "system", "content": system_prompt}, *messages],
    )
    return response.choices[0].message.content or ""


class CoachChatService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._chat = CoachChatRepository(session)
        self._progress = ProgressRepository(session)
        self._training_blocks = TrainingBlockService(session)
        self._skills = SkillService(session)
        self._actions = CoachChatProposedActionRepository(session)
        self._users = UserService(session)
        self._restrictions = UserTemporaryRestrictionService(session)

    async def send_message(self, user: User, message: str) -> CoachChatMessageRead:
        settings = get_settings()
        if not settings.zai_api_key:
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

        system_prompt = await self._build_system_prompt(user, user.coach_personality)
        history = await self._chat.list_recent(user.id, HISTORY_REPLAY_TURNS)
        api_messages = [{"role": entry.role.value, "content": entry.content} for entry in history]
        api_messages.append({"role": "user", "content": message})

        raw_reply = await _call_zai(
            settings.zai_api_key,
            settings.zai_base_url,
            settings.coach_chat_model,
            system_prompt,
            api_messages,
        )
        reply_text, resolved_action = await self._extract_proposed_action(raw_reply)

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
        await self._session.flush()  # need assistant_message.id before it can be a FK target

        proposed_action_row: CoachChatProposedAction | None = None
        if resolved_action is not None:
            action_type, payload = resolved_action
            # Only one confirmable proposal per user at a time -- see
            # CoachChatProposedAction's own docstring.
            await self._actions.expire_pending_for_user(user.id)
            proposed_action_row = self._actions.create(
                CoachChatProposedAction(
                    message_id=assistant_message.id,
                    user_id=user.id,
                    action_type=action_type,
                    payload=payload,
                )
            )

        await self._session.commit()
        await self._session.refresh(assistant_message)

        message_read = CoachChatMessageRead.model_validate(assistant_message)
        if proposed_action_row is not None:
            await self._session.refresh(proposed_action_row)
            message_read = message_read.model_copy(
                update={"proposed_action": self._to_action_read(proposed_action_row)}
            )
        return message_read

    async def list_history(self, user_id: uuid.UUID, limit: int) -> list[CoachChatMessageRead]:
        entries = await self._chat.list_recent(user_id, limit)
        actions_by_message = {
            action.message_id: action
            for action in await self._actions.list_by_message_ids([entry.id for entry in entries])
        }
        results = []
        for entry in entries:
            message_read = CoachChatMessageRead.model_validate(entry)
            action = actions_by_message.get(entry.id)
            if action is not None:
                message_read = message_read.model_copy(
                    update={"proposed_action": self._to_action_read(action)}
                )
            results.append(message_read)
        return results

    async def confirm_action(
        self, user: User, action_id: uuid.UUID
    ) -> ProposedActionRead:
        action = await self._get_pending_action_or_404(user.id, action_id)

        if action.action_type is CoachActionType.SKILL_PRIORITY_ADD:
            await self._skills.add_priority_skill(user, uuid.UUID(action.payload["skill_id"]))
        elif action.action_type is CoachActionType.SET_TOURNAMENT_DATE:
            parsed_date = date.fromisoformat(action.payload["tournament_date"])
            await self._users.update_profile(user, UserUpdate(tournament_date=parsed_date))
        elif action.action_type is CoachActionType.REPORT_RESTRICTION:
            movement_pattern = action.payload.get("movement_pattern")
            muscle_group = action.payload.get("muscle_group")
            await self._restrictions.report(
                user,
                MovementPattern(movement_pattern) if movement_pattern is not None else None,
                MuscleGroup(muscle_group) if muscle_group is not None else None,
                action.payload.get("reason"),
            )

        action.status = CoachActionStatus.CONFIRMED
        action.decided_at = datetime.now(timezone.utc)
        await self._session.commit()
        await self._session.refresh(action)
        return self._to_action_read(action)

    async def dismiss_action(self, user: User, action_id: uuid.UUID) -> ProposedActionRead:
        action = await self._get_pending_action_or_404(user.id, action_id)
        action.status = CoachActionStatus.DISMISSED
        action.decided_at = datetime.now(timezone.utc)
        await self._session.commit()
        await self._session.refresh(action)
        return self._to_action_read(action)

    async def _get_pending_action_or_404(
        self, user_id: uuid.UUID, action_id: uuid.UUID
    ) -> CoachChatProposedAction:
        action = await self._actions.get_owned(user_id, action_id)
        if action is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")
        if action.status != CoachActionStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Это предложение уже не активно",
            )
        return action

    @staticmethod
    def _to_action_read(action: CoachChatProposedAction) -> ProposedActionRead:
        return ProposedActionRead(
            id=action.id,
            action_type=action.action_type,
            payload=action.payload,
            status=action.status,
            summary=_build_action_summary(action.action_type, action.payload),
        )

    async def _extract_proposed_action(
        self, reply_text: str
    ) -> tuple[str, tuple[CoachActionType, dict] | None]:
        """Strips a trailing <!--ACTION:{...}--> marker (if present) off the
        model's raw reply and, if it parses into one of the three known,
        strictly-validated action shapes, resolves it into a
        (CoachActionType, payload-ready-to-store) pair. Never trusts the
        rest of the reply text -- an unparseable/unknown/invalid marker is
        silently dropped (the cleaned reply is still shown to the user,
        just without a proposed action), not an error surfaced to the
        player."""
        match = _ACTION_MARKER_RE.search(reply_text)
        if match is None:
            return reply_text, None

        clean_text = reply_text[: match.start()].rstrip()
        try:
            raw = json.loads(match.group(1))
            action_type = CoachActionType(raw["type"])
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            return clean_text, None

        payload = await self._resolve_action_payload(action_type, raw)
        if payload is None:
            return clean_text, None
        return clean_text, (action_type, payload)

    async def _resolve_action_payload(
        self, action_type: CoachActionType, raw: dict
    ) -> dict | None:
        if action_type is CoachActionType.SKILL_PRIORITY_ADD:
            skill_name = raw.get("skill_name")
            if not isinstance(skill_name, str) or not skill_name.strip():
                return None
            # Resolve by exact name, never trust a model-supplied id -- a
            # hallucinated skill_id would be harder to distinguish from a
            # real one than a hallucinated name, which simply fails to
            # match anything.
            skill = await self._skills.find_skill_by_name(skill_name.strip())
            if skill is None:
                return None
            return {"skill_id": str(skill.id), "skill_name": skill.name}

        if action_type is CoachActionType.SET_TOURNAMENT_DATE:
            raw_date = raw.get("tournament_date")
            if not isinstance(raw_date, str):
                return None
            try:
                parsed_date = date.fromisoformat(raw_date)
            except ValueError:
                return None
            return {"tournament_date": parsed_date.isoformat()}

        if action_type is CoachActionType.REPORT_RESTRICTION:
            movement_pattern_raw = raw.get("movement_pattern")
            muscle_group_raw = raw.get("muscle_group")
            reason = raw.get("reason")
            try:
                movement_pattern = (
                    MovementPattern(movement_pattern_raw)
                    if movement_pattern_raw is not None
                    else None
                )
                muscle_group = (
                    MuscleGroup(muscle_group_raw) if muscle_group_raw is not None else None
                )
            except ValueError:
                return None
            # Exactly one of the two -- same rule UserTemporaryRestrictionIn
            # enforces at the manual-report boundary.
            if (movement_pattern is None) == (muscle_group is None):
                return None
            if reason is not None and not isinstance(reason, str):
                return None
            return {
                "movement_pattern": movement_pattern.value if movement_pattern else None,
                "muscle_group": muscle_group.value if muscle_group else None,
                "reason": reason,
            }

        return None

    async def _build_system_prompt(self, user: User, coach_personality: CoachPersonality) -> str:
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

        block = await self._training_blocks.resolve_active_block(user.id)
        if block is not None:
            sessions_completed = await self._training_blocks.count_sessions_completed_in_phase(block)
            phase_section = _format_phase_section(block.phase, sessions_completed, SESSIONS_TO_ADVANCE_PHASE)
        else:
            phase_section = _format_phase_section(None, 0, SESSIONS_TO_ADVANCE_PHASE)

        recent_history = await self._progress.list_recent_history(user.id, RECENT_HISTORY_COUNT)
        history_section = _format_history_section(recent_history)

        action_reference_section = _format_action_reference_section(
            [skill.name for skill in skills]
        )

        return (
            f"{PERSONALITY_SYSTEM_PROMPTS[coach_personality]}\n\n"
            "Отвечай по-русски, по делу и кратко. Используй приведённую "
            "ниже сводку данных пользователя, чтобы давать конкретные, персональные "
            "советы по тренировкам, а не общие фразы.\n\n"
            f"Сводка данных пользователя (на {now.date().isoformat()}):\n"
            f"{stats_section}\n"
            f"{milestones_section}\n"
            f"{streak_section}\n"
            f"{phase_section}\n"
            f"{history_section}\n\n"
            f"{SYSTEM_PROMPT_GUARDRAILS}\n\n"
            f"{action_reference_section}"
        )
