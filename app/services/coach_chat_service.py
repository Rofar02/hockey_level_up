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
import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from openai import APIError, AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.training_block import sessions_to_advance_phase, taper_start_dates
from app.models.coach_chat import CoachChatMessage, CoachChatRole
from app.models.coach_memory import CoachMemoryFact
from app.models.coach_chat_proposed_action import (
    CoachActionStatus,
    CoachActionType,
    CoachChatProposedAction,
)
from app.models.exercise import MovementPattern, MuscleGroup, TargetStat, TrainingPhase
from app.models.progress import StatHistory, UserStat
from app.models.schedule import BlockPhase, DayPlan, DaySessionType, TrainingSession, WeeklyPlan
from app.models.set_completion import SetCompletion
from app.models.skill import SkillTag
from app.models.user import CoachPersonality, User
from app.models.user_temporary_restriction import UserTemporaryRestriction
from app.repositories.coach_chat_proposed_action_repository import CoachChatProposedActionRepository
from app.repositories.coach_chat_repository import CoachChatRepository
from app.repositories.progress_repository import ProgressRepository
from app.repositories.schedule_repository import ScheduleRepository
from app.repositories.set_completion_repository import SetCompletionRepository
from app.schemas.analytics import AnalyticsMoverRead, AnalyticsSummaryRead
from app.schemas.coach_chat import CoachChatMessageRead, ProposedActionRead
from app.schemas.training_diary import TrainingDiaryEntryListItem
from app.schemas.user import UserUpdate
from app.services.analytics_service import AnalyticsService
from app.services.coach_personality_prompts import PERSONALITY_SYSTEM_PROMPTS
from app.services.skill_service import SkillService
from app.services.training_block_service import TrainingBlockService
from app.services.training_diary_service import TrainingDiaryService
from app.services.user_service import UserService
from app.services.user_temporary_restriction_service import UserTemporaryRestrictionService

logger = logging.getLogger(__name__)

# 2026-09-18 fix (round 2 audit item #4): _call_zai's own catch-all for the
# openai client (expired key, exhausted quota, an invalid configured model
# name, a timeout, ...) -- one detail/status for every case rather than
# leaking whichever raw exception text the client happened to raise. There
# is no global exception handler in app/main.py, so an unhandled exception
# here used to reach the client as Starlette's default plain-text 500,
# which the frontend (expecting JSON) rendered as an opaque "Request
# failed".
#
# 2026-09-18 follow-up fix (same day, found live): this used to raise 503,
# same as send_message's own "feature not configured at all" guard above --
# but CoachPage.tsx already treats ANY 503 from this endpoint as that
# specific case (sets `unavailable`, permanently swaps to ComingSoonCard,
# never renders the error text at all). A z.ai call that fails mid-flight
# is a materially different situation -- the feature IS configured, this
# one attempt failed -- so it needs its own code the frontend doesn't
# already have a conflicting meaning for. 502 (this server successfully
# reached the upstream but got back a failure) is the correct REST
# semantics for that and doesn't collide with the "not configured" 503.
COACH_UNAVAILABLE_DETAIL = "Не получилось связаться с тренером, попробуй чуть позже"

MONTHLY_MESSAGE_LIMIT = 150
# 2026-09-17 (audit item #7): send_message no longer hard-walls non-premium
# users behind require_premium/403 -- a small free trial instead, same
# monthly-window infrastructure (count_user_messages_since) as the premium
# limit above, just a much smaller number for has_premium=False. Doesn't
# change anything about the feature itself (same model, same proposed-
# action flow) -- purely how many messages a non-premium user gets before
# hitting 429 this month.
FREE_TRIAL_MESSAGE_LIMIT = 5
# How many prior messages get replayed back to the model as dialogue
# context -- a rolling window, not the full history (which the /history
# endpoint exposes separately, unbounded by this). Raised from 10 to 30
# (2026-09-14, deliberate) -- cost impact is negligible on the current
# free-tier model and stays small even on a future paid model (~15
# messages of real back-and-forth is a much more honest "memory" than 5).
# 2026-10-04: down to 12 -- older messages now live on as coach memory
# notes (CoachMemoryService, premium), which keeps the prompt bounded.
HISTORY_REPLAY_TURNS = 12

# Generous on purpose: cheap insurance against a truncated reply, and
# glm-4.7-flash (the current default model) is free-tier, so there's no
# cost pressure to shrink it.
MAX_RESPONSE_TOKENS = 2048

# glm-5.3 (the paid model, see Settings.coach_chat_model) is always a
# reasoning model server-side -- z.ai rejects "disabled" outright ("This
# model always engages in thinking and cannot be disabled; please use
# low, high, or max") and silently defaults to something at least as deep
# as "max" when this isn't set at all. Confirmed live against prod's real
# system prompt (2026-09-19): with no reasoning_effort, every single call
# hit finish_reason="length" with 2047-2048/2048 tokens spent entirely on
# reasoning_content and an empty visible content -- the actual cause of
# "AI coach doesn't answer" despite a 200 OK and no logged exception.
# "high" reliably finishes with finish_reason="stop" well inside
# MAX_RESPONSE_TOKENS (~650-700 tokens total on the same prompt) and,
# unlike "low", still reliably emits the <!--ACTION:{...}--> marker when
# the guardrails call for one. glm-4.7-flash also does hidden reasoning
# (confirmed the same way -- a too-small max_tokens starves it too) but
# stays well within MAX_RESPONSE_TOKENS with this same param set, so one
# constant covers both models rather than branching on which is active.
COACH_REASONING_EFFORT = "high"
# 2026-10-04: with actions moved from the text marker to native tool calls,
# glm-5.x (prod) picks the right action 12/12 on a fixed scenario set at
# "low" too, with ~30% fewer output tokens -- the marker was the only thing
# "high" was buying. glm-4.7-flash (local dev) dropped to 9/12 at "low", so
# it keeps "high".
COACH_REASONING_EFFORT_LOW = "low"


def _reasoning_effort_for(model: str) -> str:
    return COACH_REASONING_EFFORT_LOW if model.startswith("glm-5") else COACH_REASONING_EFFORT

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

# Same wording as frontend/src/types/schedule.ts's DAY_SESSION_TYPE_LABELS.
DAY_SESSION_TYPE_LABELS: dict[DaySessionType, str] = {
    DaySessionType.ON_ICE: "Лёд",
    DaySessionType.OFF_ICE: "Сухая",
    DaySessionType.REST: "Отдых",
    DaySessionType.GAME: "Игра",
}

# How many of the player's own most recent diary notes get replayed into
# the prompt -- capped for the same reason HISTORY_REPLAY_TURNS is capped
# (cost), and because a coach explaining "how did the last session feel"
# only needs recent context, not the whole notebook (the full history is
# what /diary itself is for).
DIARY_ENTRIES_IN_PROMPT = 3
# Same default window AnalyticsPage.tsx itself opens with -- the coach's
# "what's trending" summary should describe the same period the player
# would see if they opened Analytics themselves, not a second, differently
# numbered window that could disagree with it.
ANALYTICS_SUMMARY_WINDOW_DAYS = 90
# How many past (lifted/expired) restrictions get replayed -- same
# cost-driven cap as DIARY_ENTRIES_IN_PROMPT above.
RESOLVED_RESTRICTIONS_IN_PROMPT = 3
# How many calendar days ahead of `today` to look for the next real
# training day if today itself is REST or has no plan yet -- one week is
# generous (a declared week is at most 7 days) without risking an
# unbounded scan.
UPCOMING_SESSION_SEARCH_DAYS = 7

# 2026-09-20 (player-requested: "план прошлой недели, план будущей...
# динамику упражнений"): how many recurring MAIN exercises (present in
# both last week's plan and this week's) get a weight/reps comparison in
# the prompt -- capped for the same cost reason as the other *_IN_PROMPT
# constants above, and because a coach only needs the most notable
# progressions, not a full log (the diary/history views are what fuller
# review is for).
PROGRESSION_EXERCISES_IN_PROMPT = 5

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
    MuscleGroup.ADDUCTORS: "Приводящие мышцы",
    MuscleGroup.HIP_FLEXORS: "Сгибатели бедра",
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
    "Но для трёх конкретных вещей у тебя есть функции (tools), которые "
    "ПРЕДЛАГАЮТ действие, -- оно применится, только когда игрок сам нажмёт "
    "кнопку подтверждения под твоим сообщением, никогда не молча. Никогда не "
    "говори, что уже сделал это. Всегда пиши игроку обычный текстовый ответ; "
    "если предлагаешь действие -- дополнительно вызови функцию и скажи в "
    "тексте, что подтвердить можно кнопкой ниже. Не больше одной функции на "
    "ответ, и только когда уверен, что игрок этого хочет; если неоднозначно "
    "(например, жалоба может относиться к разным навыкам) -- сначала задай "
    "один уточняющий вопрос, без вызова функции.\n"
    "- skill_priority_add: игрок жалуется на конкретную игровую проблему, "
    "которая явно указывает на один навык (\"часто отбирают шайбу под "
    "давлением\" ближе к Обводке, \"выталкивают силой\" -- к Силовой борьбе).\n"
    "- set_tournament_date: игрок называет дату предстоящего ТУРНИРА -- "
    "соревнования из нескольких игр за 1-5 дней, выездного турнира, финала "
    "или плей-офф, к которому он готовится неделями. Дата турнира включает "
    "подводку: за 3 недели до неё система снижает нагрузку. Точные даты "
    "подводки ты видишь в сводке, когда дата турнира уже записана; пока она "
    "не записана, сам конкретные числа не высчитывай -- говори \"примерно за "
    "3 недели до турнира\". Поэтому обычная игра -- матч чемпионата или "
    "первенства, товарищеская игра, игра на выходных -- это НЕ турнир, "
    "функцию для неё не вызывай. Вместо этого подскажи отметить этот день как "
    "\"Игра\" на вкладке \"Неделя\", когда игрок планирует неделю, -- тогда "
    "в этот день вместо тренировки будет только лёгкая предыгровая "
    "активация (соседние дни система не меняет). Если из слов игрока "
    "непонятно, турнир это или одна игра, "
    "сначала спроси.\n"
    "- report_restriction: игрок сообщает, что что-то болит или "
    "дискомфортно прямо сейчас -- ЭТО НЕ ОТМЕНЯЕТ правило выше про "
    "рекомендацию обратиться к врачу, оба ответа уместны вместе.\n\n"
    "Если ничего из этого не подходит -- просто отвечай текстом. Если игрок "
    "просит что-то, что не входит в эти три действия (например переставить "
    "упражнение, снять навык, изменить нагрузку) -- объясни, что план строит "
    "сама система, и подскажи, где в приложении можно на это повлиять: "
    "временные ограничения и приоритетные навыки тоже можно менять напрямую "
    "в Настройках, не только через тебя."
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


def _format_streak_section(current_streak: int, longest_streak: int) -> str:
    # longest_streak gives the coach real season-level framing ("твой
    # лучший стрик за сезон был X") instead of only ever seeing the
    # current-moment number, same reasoning as block_number below.
    return f"Текущий стрик тренировок: {current_streak} дн. подряд (лучший за всё время: {longest_streak} дн.)."


def _format_phase_section(
    phase: BlockPhase | None,
    sessions_completed: int,
    sessions_to_advance: int,
    block_number: int | None,
    is_macrocycle_deload: bool,
) -> str:
    if phase is None:
        return "Фаза периодизации: блок ещё не начат."
    label = PHASE_LABELS.get(phase, phase.value)
    # block_number gives the coach a sense of "how far into the season"
    # the player is, not just the current phase in isolation -- one of the
    # few cheap, already-computed signals that spans the whole season
    # rather than just the last HISTORY_REPLAY_TURNS messages.
    macrocycle_note = " (восстановительный макроцикл)" if is_macrocycle_deload else ""
    return (
        f"Фаза периодизации: блок {block_number}{macrocycle_note}, {label} "
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


def _analytics_mover_label(mover: AnalyticsMoverRead) -> str:
    # "stat" movers carry the bare TargetStat value (e.g. "strength") --
    # "skill" movers already carry the real skill name, no mapping needed.
    if mover.type == "stat":
        return STAT_LABELS.get(TargetStat(mover.name), mover.name)
    return mover.name


def _format_analytics_summary_section(summary: AnalyticsSummaryRead, days: int) -> str:
    """Same top_gainer/top_decliner/closest_to_milestone/decline_reason
    AnalyticsPage.tsx itself shows -- lets the coach proactively reference
    a real trend ("вижу, у тебя выросла ловкость") instead of only
    answering when asked, without duplicating AnalyticsService's own
    selection logic here."""
    parts = [f"Аналитика за {days} дн."]
    # top_gainer is never null in the response, but its delta can be <=0
    # if nothing actually grew this window (AnalyticsService's own
    # comment) -- don't claim a "biggest gain" that wasn't one.
    if summary.top_gainer.delta > 0:
        parts.append(
            f"больше всего выросло — {_analytics_mover_label(summary.top_gainer)} "
            f"(+{summary.top_gainer.delta:.1f})"
        )
    else:
        parts.append("заметного роста не было")

    if summary.top_decliner is not None:
        reason = f", вероятная причина: {summary.decline_reason}" if summary.decline_reason else ""
        parts.append(
            f"больше всего просело — {_analytics_mover_label(summary.top_decliner)} "
            f"({summary.top_decliner.delta:.1f}){reason}"
        )

    if summary.closest_to_milestone is not None:
        milestone = summary.closest_to_milestone
        parts.append(
            f"ближе всего к следующему порогу — {milestone.skill_name} "
            f"(осталось {milestone.points_remaining:.1f} до {milestone.threshold})"
        )

    return "; ".join(parts) + "."


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


def _format_restrictions_section(restrictions: list[UserTemporaryRestriction]) -> str:
    if not restrictions:
        return "Активные временные ограничения: нет."
    parts = []
    for restriction in restrictions:
        if restriction.movement_pattern is not None:
            target = MOVEMENT_PATTERN_LABELS.get(
                restriction.movement_pattern, restriction.movement_pattern.value
            )
        else:
            target = MUSCLE_GROUP_LABELS.get(restriction.muscle_group, restriction.muscle_group.value)
        reason_part = f" ({restriction.reason})" if restriction.reason else ""
        parts.append(f"{target}{reason_part}, до {restriction.expires_at.isoformat()}")
    return "Активные временные ограничения: " + "; ".join(parts) + "."


def _format_restriction_history_section(restrictions: list[UserTemporaryRestriction]) -> str:
    """Season-memory complement to _format_restrictions_section above --
    that one is "what's bothering the player right now", this is "what's
    come up and resolved over time", so the coach can reference a pattern
    across the whole season ("плечо уже второй раз за блок") instead of
    only ever seeing the current moment, which is all the rolling chat-
    history window (HISTORY_REPLAY_TURNS) can otherwise offer."""
    if not restrictions:
        return "История прошлых ограничений: нет записей."
    parts = []
    for restriction in restrictions:
        if restriction.movement_pattern is not None:
            target = MOVEMENT_PATTERN_LABELS.get(
                restriction.movement_pattern, restriction.movement_pattern.value
            )
        else:
            target = MUSCLE_GROUP_LABELS.get(restriction.muscle_group, restriction.muscle_group.value)
        resolution = "снято досрочно" if restriction.lifted_at is not None else "истекло по сроку"
        parts.append(f"{target} ({resolution} {restriction.expires_at.isoformat()})")
    return "История прошлых ограничений (недавние): " + "; ".join(parts) + "."


def _format_diary_section(entries: list[TrainingDiaryEntryListItem]) -> str:
    """`entries` is already filtered to only-with-notes and capped at the
    DB level (see CoachChatService._build_system_prompt's
    only_with_notes=True call) -- nothing left to filter here."""
    if not entries:
        return "Последние записи дневника: нет записей с заметками."
    parts = [
        f"{entry.date.isoformat()} ({DAY_SESSION_TYPE_LABELS.get(entry.session_type, entry.session_type.value)}): "
        f"«{entry.note}»"
        for entry in entries
    ]
    return "Последние записи дневника игрока: " + "; ".join(parts) + "."


def _session_exercise_names(training_session: TrainingSession) -> str:
    exercise_names = [
        block.exercise.name for block in training_session.blocks if block.phase == TrainingPhase.MAIN
    ] or [block.exercise.name for block in training_session.blocks]
    return ", ".join(exercise_names) if exercise_names else "упражнения ещё не назначены"


def _format_today_section(today_plan: DayPlan | None) -> str:
    """Whether the player has already trained today or not -- previously
    the coach couldn't tell at all (found 2026-09-14: it only ever said
    "ближайшая тренировка" with an exercise list, identical wording
    whether that session was still ahead, half-done, or already fully
    completed). Distinct from _format_next_session_section below, which
    only ever describes a day still to come."""
    if today_plan is None:
        return "Сегодня: план на сегодня не составлен (неделя не объявлена)."
    label = DAY_SESSION_TYPE_LABELS.get(today_plan.session_type, today_plan.session_type.value)
    if today_plan.session_type == DaySessionType.REST:
        return "Сегодня: день отдыха."
    if today_plan.training_session is None or not today_plan.training_session.blocks:
        return f"Сегодня: {label}, упражнения ещё не назначены."

    blocks = today_plan.training_session.blocks
    done_count = sum(
        1 for block in blocks if block.completed_at is not None or block.skipped_at is not None
    )
    total = len(blocks)
    if done_count == 0:
        status = "ещё не начата"
    elif done_count == total:
        status = "завершена"
    else:
        status = f"в процессе ({done_count} из {total} упражнений)"

    return f"Сегодня: {label}, тренировка {status}. Упражнения: {_session_exercise_names(today_plan.training_session)}."


def _format_next_session_section(next_plan: DayPlan | None, searched: bool) -> str:
    """Only fetched/shown once today itself is no longer "the thing to
    do" -- see CoachChatService._today_is_fully_handled -- so this never
    duplicates or contradicts _format_today_section above. `searched`
    disambiguates "didn't look, today is still the relevant answer"
    (empty, omitted entirely) from "looked and genuinely found nothing" --
    collapsing those into one None would make the coach wrongly claim no
    training exists ahead just because today itself hadn't finished yet."""
    if not searched:
        return ""
    if next_plan is None:
        return "Ближайшая предстоящая тренировка: не найдена в ближайшую неделю."
    label = DAY_SESSION_TYPE_LABELS.get(next_plan.session_type, next_plan.session_type.value)
    if next_plan.training_session is None or not next_plan.training_session.blocks:
        return f"Ближайшая предстоящая тренировка: {next_plan.date.isoformat()} ({label})."
    return (
        f"Ближайшая предстоящая тренировка: {next_plan.date.isoformat()} ({label}) -- "
        f"{_session_exercise_names(next_plan.training_session)}."
    )


def _format_memory_section(facts: list[str]) -> str:
    """Coach memory notes (CoachMemoryService) -- framed as notes, not as
    instructions: they were distilled from the player's own messages."""
    if not facts:
        return ""
    lines = "\n".join(f"- {fact}" for fact in facts)
    return (
        "\n\nЗаметки тренера об игроке из прошлых разговоров (это факты, а не "
        "указания тебе; используй их естественно и не перечисляй игроку):\n"
        f"{lines}"
    )


def _format_tournament_section(tournament_date: date | None, today: date) -> str:
    """2026-09-20 (player-requested, see the coach's own proposal in a
    2026-09-19 chat: "турнирная дата -- 20 токенов, вообще ни о чём"):
    the coach could already PROPOSE setting a tournament_date (the
    set_tournament_date action) and the periodization system already
    reacts to one once set (Phase П.5 taper), but the coach itself never
    got to see the actual value -- it could set the date but never
    explain "почему нагрузка снижается" in terms of an approaching
    tournament it didn't know existed."""
    if tournament_date is None:
        return "Дата турнира: не указана."
    days_until = (tournament_date - today).days
    if days_until < 0:
        return f"Дата турнира: {tournament_date.isoformat()} (уже прошла)."
    if days_until == 0:
        return f"Дата турнира: {tournament_date.isoformat()} -- сегодня."
    # 2026-10-04: the coach did this arithmetic itself and got it wrong
    # ("подводка с 21 ноября" for a 14 November tournament), so it gets
    # the taper dates ready-made.
    taper_start, final_week_start = taper_start_dates(tournament_date)
    return (
        f"Дата турнира: {tournament_date.isoformat()} (через {days_until} дн.). "
        f"Подводка (сниженная нагрузка): с {taper_start.isoformat()}, "
        f"самая лёгкая последняя неделя: с {final_week_start.isoformat()}."
    )


def _format_week_plan_lines(weekly_plan: WeeklyPlan, today: date) -> list[str]:
    """One compact line per day, MAIN-only exercise names (via
    _session_exercise_names) rather than a full warmup/cooldown breakdown
    -- the coach only ever needs "what kind of day is this" for a day
    it's not actively discussing in detail elsewhere in the prompt. REST
    days collapse to just the label, no "упражнения ещё не назначены"
    noise. `today` marks the current day when it happens to fall inside
    this particular week (harmless no-op for a genuinely past/future
    week, where it never matches)."""
    lines = []
    for day_plan in sorted(weekly_plan.day_plans, key=lambda dp: dp.date):
        label = DAY_SESSION_TYPE_LABELS.get(day_plan.session_type, day_plan.session_type.value)
        marker = " (сегодня)" if day_plan.date == today else ""
        if day_plan.session_type == DaySessionType.REST or day_plan.training_session is None:
            lines.append(f"{day_plan.date.isoformat()}{marker}: {label}")
        else:
            lines.append(
                f"{day_plan.date.isoformat()}{marker}: {label} -- "
                f"{_session_exercise_names(day_plan.training_session)}"
            )
    return lines


def _format_week_overview_section(weekly_plan: WeeklyPlan | None, today: date) -> str:
    """2026-09-20 (player-requested: "чтобы видел всю неделю, а не два
    дня"): _format_today_section/_format_next_session_section together
    only ever cover at most two of the week's seven days (today, plus
    whichever single day is next) -- a player asking "как у меня выглядит
    неделя" or "почему в четверг легче, чем во вторник" had nothing to
    ground that in."""
    if weekly_plan is None:
        return "План на текущую неделю: не составлен."
    return "План на текущую неделю:\n" + "\n".join(_format_week_plan_lines(weekly_plan, today))


def _format_last_week_section(weekly_plan: WeeklyPlan | None, today: date) -> str:
    """2026-09-20 (player-requested): lets the coach compare "как было" с
    "как сейчас" itself from the two week summaries side by side (e.g.
    notice a pattern moved days, or a session got lighter/heavier) without
    a separate, persisted change-log -- there isn't one
    (patch_week_for_eligibility_change applies its swaps silently), and
    diffing two plain-text week overviews is enough for the model to
    reason about, not something that needs its own dedicated audit
    table."""
    if weekly_plan is None:
        return "План прошлой недели: нет данных (не была сформирована)."
    return "План прошлой недели:\n" + "\n".join(_format_week_plan_lines(weekly_plan, today))


def _format_next_week_section(weekly_plan: WeeklyPlan | None, today: date) -> str:
    """Companion to _format_last_week_section above -- next week is often
    simply not generated yet (weeks are declared close to when they
    start, not far in advance), which is a normal, expected state, not a
    missing-data problem."""
    if weekly_plan is None:
        return "План следующей недели: ещё не сформирован."
    return "План следующей недели:\n" + "\n".join(_format_week_plan_lines(weekly_plan, today))


def _main_exercise_ids_by_name(weekly_plan: WeeklyPlan | None) -> dict[uuid.UUID, str]:
    """Every MAIN-phase exercise appearing anywhere in the week, keyed by
    id -- used to find exercises that recur between two weeks (see
    CoachChatService._format_progression_section)."""
    if weekly_plan is None:
        return {}
    result: dict[uuid.UUID, str] = {}
    for day_plan in weekly_plan.day_plans:
        if day_plan.training_session is None:
            continue
        for block in day_plan.training_session.blocks:
            if block.phase == TrainingPhase.MAIN:
                result[block.exercise_id] = block.exercise.name
    return result


def _format_progression_entry(name: str, older: SetCompletion, newer: SetCompletion) -> str | None:
    """One exercise's before/after, preferring weight (the primary
    double-progression signal, see weight_suggestion_service.py) and
    falling back to reps when weight isn't tracked for it -- None when
    neither field has data for both sets (nothing comparable to show)."""
    if older.weight_kg is not None and newer.weight_kg is not None:
        if older.weight_kg == newer.weight_kg:
            return f"{name}: без изменений в весе ({newer.weight_kg:g} кг)"
        return f"{name}: {older.weight_kg:g} кг -> {newer.weight_kg:g} кг"
    if older.reps_completed is not None and newer.reps_completed is not None:
        if older.reps_completed == newer.reps_completed:
            return f"{name}: без изменений в повторах ({newer.reps_completed})"
        return f"{name}: {older.reps_completed} -> {newer.reps_completed} повт."
    return None


def _format_progression_section(entries: list[str]) -> str:
    if not entries:
        return (
            "Динамика по повторяющимся упражнениям: нет данных для сравнения "
            "(нужна история минимум по двум разным тренировкам одного и того "
            "же упражнения)."
        )
    return (
        "Динамика по упражнениям, которые есть и в этой, и в прошлой неделе "
        "(сравнение последних двух отработанных тренировок): "
        + "; ".join(entries)
        + "."
    )


def _format_priority_skill_focus_section(
    day_plan: DayPlan | None,
    priority_skill_names_by_id: dict[uuid.UUID, str],
    tags: list[SkillTag],
) -> str:
    """Grounds "why this workout" answers in something real: which of the
    upcoming session's own exercises are tagged to a skill the player
    picked as a priority, per the real SkillTag rows (not guessed) -- so
    the coach can say "сегодня в фокусе Обводка, потому что ты выбрал её
    приоритетной" instead of a generic, unverifiable claim."""
    if day_plan is None or day_plan.training_session is None or not priority_skill_names_by_id:
        return ""
    exercise_ids_today = {block.exercise_id for block in day_plan.training_session.blocks}
    matched_names = sorted(
        {
            priority_skill_names_by_id[tag.skill_id]
            for tag in tags
            if tag.exercise_id in exercise_ids_today and tag.skill_id in priority_skill_names_by_id
        }
    )
    if not matched_names:
        return ""
    return (
        "Сегодняшняя/ближайшая тренировка развивает приоритетные навыки игрока: "
        + ", ".join(matched_names)
        + "."
    )


@dataclass(frozen=True)
class ZaiUsage:
    prompt_tokens: int | None = None
    cached_tokens: int | None = None
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None


@dataclass(frozen=True)
class ZaiReply:
    text: str
    # (function name, raw JSON arguments) of the first tool call, if any.
    tool_call: tuple[str, str] | None = None
    usage: ZaiUsage = field(default_factory=ZaiUsage)


def _coach_tools(skill_names: list[str]) -> list[dict]:
    """The three proposable actions as native tools (2026-10-04, replacing
    the <!--ACTION:{...}--> text marker). Allowed values travel as JSON
    schema enums instead of a reference section in the prompt -- the model
    can't invent a skill or pattern name, and _resolve_action_payload still
    re-validates every argument. Keep the list's content stable across users
    (skills sorted by name) so z.ai's prompt cache can reuse it."""
    pattern_hint = "; ".join(f"{p.value} = {label}" for p, label in MOVEMENT_PATTERN_LABELS.items())
    muscle_hint = "; ".join(f"{g.value} = {label}" for g, label in MUSCLE_GROUP_LABELS.items())
    skill_property: dict = {"type": "string"}
    if skill_names:
        skill_property["enum"] = skill_names
    return [
        {
            "type": "function",
            "function": {
                "name": CoachActionType.SKILL_PRIORITY_ADD.value,
                "description": "Предложить добавить навык в приоритетные.",
                "parameters": {
                    "type": "object",
                    "properties": {"skill_name": skill_property},
                    "required": ["skill_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": CoachActionType.SET_TOURNAMENT_DATE.value,
                "description": "Предложить записать дату начала турнира.",
                "parameters": {
                    "type": "object",
                    "properties": {"tournament_date": {"type": "string", "description": "ГГГГ-ММ-ДД"}},
                    "required": ["tournament_date"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": CoachActionType.REPORT_RESTRICTION.value,
                "description": (
                    "Предложить записать временное ограничение: ровно одно из "
                    "movement_pattern или muscle_group, никогда оба."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "movement_pattern": {
                            "type": "string",
                            "enum": [p.value for p in MOVEMENT_PATTERN_LABELS],
                            "description": pattern_hint,
                        },
                        "muscle_group": {
                            "type": "string",
                            "enum": [g.value for g in MUSCLE_GROUP_LABELS],
                            "description": muscle_hint,
                        },
                        "reason": {"type": "string", "description": "кратко своими словами, необязательно"},
                    },
                },
            },
        },
    ]


def _usage_from(response) -> ZaiUsage:
    usage = getattr(response, "usage", None)
    if usage is None:
        return ZaiUsage()
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    completion_details = getattr(usage, "completion_tokens_details", None)
    return ZaiUsage(
        prompt_tokens=getattr(usage, "prompt_tokens", None),
        cached_tokens=getattr(prompt_details, "cached_tokens", None),
        completion_tokens=getattr(usage, "completion_tokens", None),
        reasoning_tokens=getattr(completion_details, "reasoning_tokens", None),
    )


async def _call_zai(
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    messages: list[dict[str, str]],
    tools: list[dict] | None = None,
) -> ZaiReply:
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    extra: dict = {"tools": tools} if tools else {}
    try:
        response = await client.chat.completions.create(
            model=model,
            max_tokens=MAX_RESPONSE_TOKENS,
            reasoning_effort=_reasoning_effort_for(model),
            messages=[{"role": "system", "content": system_prompt}, *messages],
            **extra,
        )
    except APIError as exc:
        # Catches every openai-client failure mode (RateLimitError,
        # AuthenticationError, APITimeoutError, APIConnectionError, an
        # invalid configured model name, ...) -- all subclasses of this one
        # base, so a single handler covers the lot rather than enumerating
        # each and missing whichever one isn't on the list yet. The real
        # exception is logged here, server-side, before it's replaced with
        # a single stable, Russian-language message -- see
        # COACH_UNAVAILABLE_DETAIL's own comment for why this can't just
        # propagate unhandled.
        logger.error("z.ai chat completion call failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=COACH_UNAVAILABLE_DETAIL
        ) from exc
    message = response.choices[0].message
    tool_calls = getattr(message, "tool_calls", None) or []
    tool_call = (tool_calls[0].function.name, tool_calls[0].function.arguments or "{}") if tool_calls else None
    return ZaiReply(text=message.content or "", tool_call=tool_call, usage=_usage_from(response))


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
        self._diary = TrainingDiaryService(session)
        self._schedule = ScheduleRepository(session)
        self._analytics = AnalyticsService(session)
        self._sets = SetCompletionRepository(session)

    async def send_message(self, user: User, message: str) -> CoachChatMessageRead:
        settings = get_settings()
        if not settings.zai_api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Функция скоро будет доступна",
            )

        # Same class of bug as _build_system_prompt's own "today" fix below
        # -- the monthly quota should reset on the player's own calendar
        # month boundary, not the server's UTC one.
        month_start = datetime.now(ZoneInfo(user.timezone)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        sent_this_month = await self._chat.count_user_messages_since(user.id, month_start)
        message_limit = MONTHLY_MESSAGE_LIMIT if user.has_premium else FREE_TRIAL_MESSAGE_LIMIT
        if sent_this_month >= message_limit:
            detail = (
                f"Достигнут лимит сообщений ИИ-тренеру на этот месяц "
                f"({message_limit}). Попробуйте в следующем месяце."
                if user.has_premium
                else (
                    f"Бесплатный лимит сообщений ИИ-тренеру на этот месяц исчерпан "
                    f"({message_limit}). Оформите премиум-подписку, чтобы продолжить общение."
                )
            )
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)

        system_prompt = await self._build_system_prompt(user, user.coach_personality)
        history = await self._chat.list_recent(user.id, HISTORY_REPLAY_TURNS)
        api_messages = [{"role": entry.role.value, "content": entry.content} for entry in history]
        api_messages.append({"role": "user", "content": message})

        skill_names = sorted(skill.name for skill in await self._skills.list_skills_for_user(user.id))
        zai_reply = await _call_zai(
            settings.zai_api_key,
            settings.zai_base_url,
            settings.coach_chat_model,
            system_prompt,
            api_messages,
            tools=_coach_tools(skill_names),
        )
        resolved_action = await self._resolve_tool_call(zai_reply.tool_call)
        reply_text = zai_reply.text.strip()
        if not reply_text and resolved_action is not None:
            # The model is told to always write text, but a bare tool call
            # must still leave the player a readable message above the button.
            reply_text = f"{_build_action_summary(*resolved_action)} Подтверди кнопкой ниже."
        usage = zai_reply.usage
        logger.info(
            "coach reply: model=%s prompt=%s cached=%s completion=%s reasoning=%s tool=%s",
            settings.coach_chat_model,
            usage.prompt_tokens,
            usage.cached_tokens,
            usage.completion_tokens,
            usage.reasoning_tokens,
            zai_reply.tool_call[0] if zai_reply.tool_call else None,
        )

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
        assistant_message.llm_model = settings.coach_chat_model
        assistant_message.prompt_tokens = usage.prompt_tokens
        assistant_message.cached_tokens = usage.cached_tokens
        assistant_message.completion_tokens = usage.completion_tokens
        assistant_message.reasoning_tokens = usage.reasoning_tokens
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

    async def _resolve_tool_call(
        self, tool_call: tuple[str, str] | None
    ) -> tuple[CoachActionType, dict] | None:
        """Turns the model's tool call (function name, JSON arguments) into
        a (CoachActionType, payload-ready-to-store) pair if it is one of the
        three known, strictly-validated action shapes. An unknown function,
        unparseable arguments or invalid values are silently dropped -- the
        reply text is still shown, just without a proposed action -- never
        an error surfaced to the player."""
        if tool_call is None:
            return None
        name, arguments = tool_call
        try:
            action_type = CoachActionType(name)
            raw = json.loads(arguments)
        except (json.JSONDecodeError, ValueError, TypeError):
            return None
        if not isinstance(raw, dict):
            return None
        payload = await self._resolve_action_payload(action_type, raw)
        if payload is None:
            return None
        return action_type, payload

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
            # `or None`: a tool call may fill the unused one with "".
            movement_pattern_raw = raw.get("movement_pattern") or None
            muscle_group_raw = raw.get("muscle_group") or None
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
        # 2026-09-19: was datetime.now(timezone.utc) -- read the *server's*
        # calendar day, not the player's. Same class of bug already fixed
        # elsewhere (get_current_weekly_plan, ProgressService.get_streak,
        # ...) but missed here: for anyone east of UTC (e.g. a
        # Novokuznetsk, UTC+7, player), the coach's "today" flips over to
        # the next day up to 7 hours *before* the player's own midnight --
        # confirmed live, the coach insisted "today" was still an off-ice
        # day already patched to game for what was genuinely the player's
        # current day, because it was reading a UTC date that, for them,
        # had already ended hours earlier.
        now = datetime.now(ZoneInfo(user.timezone))

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
        streak_section = _format_streak_section(
            streak.current_streak if streak is not None else 0,
            streak.longest_streak if streak is not None else 0,
        )

        block = await self._training_blocks.resolve_active_block(user.id)
        if block is not None:
            sessions_completed = await self._training_blocks.count_sessions_completed_in_phase(block)
            phase_section = _format_phase_section(
                block.phase,
                sessions_completed,
                sessions_to_advance_phase(block.phase, user.season_period),
                block.block_number,
                block.is_macrocycle_deload,
            )
        else:
            phase_section = _format_phase_section(None, 0, sessions_to_advance_phase(None, user.season_period), None, False)

        recent_history = await self._progress.list_recent_history(user.id, RECENT_HISTORY_COUNT)
        history_section = _format_history_section(recent_history)

        active_restrictions, resolved_restrictions = await self._restrictions.list_for_coach_prompt(
            user, RESOLVED_RESTRICTIONS_IN_PROMPT
        )
        restrictions_section = _format_restrictions_section(active_restrictions)
        restriction_history_section = _format_restriction_history_section(resolved_restrictions)

        diary_entries = await self._diary.list_entries(
            user, limit=DIARY_ENTRIES_IN_PROMPT, only_with_notes=True
        )
        diary_section = _format_diary_section(diary_entries)

        tournament_section = _format_tournament_section(user.tournament_date, now.date())

        weekly_plan = await self._schedule.get_current(user.id, now.date())
        week_overview_section = _format_week_overview_section(weekly_plan, now.date())

        # 2026-09-20 (player-requested): the current-week overview above
        # only ever covers one week -- last week (for comparison, "как
        # было") and next week (if already generated) give the coach the
        # same before/after view the player themselves gets by paging
        # through the Week screen. `current_week_start` prefers the real
        # WeeklyPlan row's own value (authoritative) and only falls back
        # to a computed Monday when there's no current week at all (e.g.
        # a brand-new player, or an undeclared week) -- same Monday-
        # alignment ScheduleService._advance_week itself uses.
        current_week_start = (
            weekly_plan.week_start_date
            if weekly_plan is not None
            else now.date() - timedelta(days=now.date().weekday())
        )
        adjacent_week_starts = current_week_start - timedelta(days=7), current_week_start + timedelta(
            days=7
        )
        plans_by_week_start = await self._schedule.list_by_week_start_dates(
            user.id, list(adjacent_week_starts)
        )
        last_week_plan = plans_by_week_start.get(adjacent_week_starts[0])
        next_week_plan = plans_by_week_start.get(adjacent_week_starts[1])
        last_week_section = _format_last_week_section(last_week_plan, now.date())
        next_week_section = _format_next_week_section(next_week_plan, now.date())

        progression_section = _format_progression_section(
            await self._resolve_progression_entries(user.id, weekly_plan, last_week_plan)
        )

        today_plan = await self._schedule.get_day_plan_for_date(user.id, now.date())
        today_section = _format_today_section(today_plan)

        today_fully_handled = self._today_is_fully_handled(today_plan)
        next_plan = (
            await self._find_next_actionable_day_plan(user.id, now.date())
            if today_fully_handled
            else None
        )
        next_session_section = _format_next_session_section(next_plan, today_fully_handled)

        # Whichever plan the coach should treat as "what's coming up to
        # focus on" -- today's own session while it's still actionable,
        # otherwise the next real training day.
        focus_plan = next_plan if today_fully_handled else today_plan
        priority_preferences = await self._skills.list_user_preferences(user.id)
        priority_skill_names_by_id = {pref.skill_id: pref.name for pref in priority_preferences}
        all_tags = await self._skills.list_all_tags()
        priority_focus_section = _format_priority_skill_focus_section(
            focus_plan, priority_skill_names_by_id, all_tags
        )

        analytics_summary = await self._analytics.get_summary(user, ANALYTICS_SUMMARY_WINDOW_DAYS)
        analytics_section = _format_analytics_summary_section(
            analytics_summary, ANALYTICS_SUMMARY_WINDOW_DAYS
        )

        # Coach memory is a premium feature; notes left over after premium
        # ends stay stored (and visible in Settings) but aren't used.
        memory_facts: list[str] = []
        if user.has_premium:
            memory_result = await self._session.execute(
                select(CoachMemoryFact.text)
                .where(CoachMemoryFact.user_id == user.id)
                .order_by(CoachMemoryFact.position, CoachMemoryFact.created_at)
            )
            memory_facts = list(memory_result.scalars().all())
        memory_section = _format_memory_section(memory_facts)

        # Appended at the very end of the summary, only when there's
        # actually something to say.
        why_this_workout_hint = f"\n{priority_focus_section}" if priority_focus_section else ""

        # 2026-10-04: everything that is the same for every player with
        # this personality (persona, instructions, guardrails) comes first
        # and the player's own data last, so z.ai's automatic prompt cache
        # can reuse the long static prefix across players and days -- it
        # only ever matches an identical prefix.
        return (
            f"{PERSONALITY_SYSTEM_PROMPTS[coach_personality]}\n\n"
            "Отвечай по-русски, по делу и кратко. Используй приведённую "
            "ниже сводку данных пользователя, чтобы давать конкретные, персональные "
            "советы по тренировкам, а не общие фразы. Если в сводке аналитики "
            "есть заметный рост или спад, можешь упомянуть это сам, не "
            "дожидаясь вопроса -- это то, что реально знает хороший тренер "
            "про своего игрока. Если игрок спрашивает, почему сегодняшняя "
            "тренировка именно такая -- объясняй, опираясь на фазу "
            "периодизации из сводки (например, в интенсификации сложность "
            "выше, в разгрузке — ниже), на дату турнира, если она указана "
            "и близко (снижение нагрузки перед игрой -- это тейпер, а не "
            "ошибка системы), и, если есть, на связь упражнений с "
            "приоритетными навыками игрока.\n\n"
            f"{SYSTEM_PROMPT_GUARDRAILS}\n\n"
            f"Сводка данных пользователя (на {now.date().isoformat()}):\n"
            f"{stats_section}\n"
            f"{milestones_section}\n"
            f"{streak_section}\n"
            f"{phase_section}\n"
            f"{history_section}\n"
            f"{restrictions_section}\n"
            f"{restriction_history_section}\n"
            f"{diary_section}\n"
            f"{tournament_section}\n"
            f"{week_overview_section}\n"
            f"{last_week_section}\n"
            f"{next_week_section}\n"
            f"{progression_section}\n"
            f"{today_section}\n"
            f"{next_session_section}\n"
            f"{analytics_section}"
            f"{why_this_workout_hint}"
            f"{memory_section}"
        )

    async def _resolve_progression_entries(
        self,
        user_id: uuid.UUID,
        weekly_plan: WeeklyPlan | None,
        last_week_plan: WeeklyPlan | None,
    ) -> list[str]:
        """MAIN exercises present in both this week's and last week's plan
        -- a recurring exercise is exactly the signal that a before/after
        comparison is meaningful for, unlike a one-off exercise that just
        happened to be picked once. Capped and name-sorted (deterministic,
        not delta-ranked -- picking "most improved" first would need the
        query run for every recurring exercise before any could be
        dropped, for no real benefit to the coach)."""
        current_main = _main_exercise_ids_by_name(weekly_plan)
        last_week_main = _main_exercise_ids_by_name(last_week_plan)
        recurring_ids = sorted(
            current_main.keys() & last_week_main.keys(), key=lambda eid: current_main[eid]
        )[:PROGRESSION_EXERCISES_IN_PROMPT]

        entries: list[str] = []
        for exercise_id in recurring_ids:
            pair = await self._resolve_last_two_sessions(user_id, exercise_id)
            if pair is None:
                continue
            newer, older = pair
            entry = _format_progression_entry(current_main[exercise_id], older, newer)
            if entry is not None:
                entries.append(entry)
        return entries

    async def _resolve_last_two_sessions(
        self, user_id: uuid.UUID, exercise_id: uuid.UUID
    ) -> tuple[SetCompletion, SetCompletion] | None:
        """The last logged set of each of the two most recent distinct
        training sessions for this exercise (newest, then the one
        before), or None with fewer than two sessions of history. Same
        "last set = the working weight that session settled on"
        convention WeightSuggestionService's own get_last_for_user_exercise
        already relies on, just walked across two sessions instead of
        one. The 20-row window is a generous bound on "sets per exercise
        across two sessions" (typically 3-4 each) without an unbounded
        scan."""
        recent = await self._sets.list_recent_for_user_exercise(user_id, exercise_id, limit=20)
        last_set_by_session: dict[uuid.UUID, SetCompletion] = {}
        for set_completion in recent:  # already newest-first
            last_set_by_session.setdefault(set_completion.training_session_id, set_completion)
            if len(last_set_by_session) == 2:
                break
        if len(last_set_by_session) < 2:
            return None
        newer, older = last_set_by_session.values()
        return newer, older

    async def _find_next_actionable_day_plan(self, user_id: uuid.UUID, today: date) -> DayPlan | None:
        """Nearest day strictly AFTER `today` (never today itself -- see
        _format_today_section for that) within UPCOMING_SESSION_SEARCH_DAYS
        that actually has a real session, skipping REST days along the way
        (a rest day isn't "the next training"). One query per candidate
        date -- acceptable here since coach-chat is a low-volume,
        user-triggered path (rate-limited to MONTHLY_MESSAGE_LIMIT/month),
        not a hot loop.
        """
        for offset in range(1, UPCOMING_SESSION_SEARCH_DAYS + 1):
            candidate = await self._schedule.get_day_plan_for_date(
                user_id, today + timedelta(days=offset)
            )
            if candidate is not None and candidate.session_type != DaySessionType.REST:
                return candidate
        return None

    @staticmethod
    def _today_is_fully_handled(today_plan: DayPlan | None) -> bool:
        """True when there's nothing left to do today -- no plan at all,
        a rest day, or every block in today's real session is already
        completed/skipped -- meaning "what's next" is the relevant
        question instead of "what's today"."""
        if today_plan is None or today_plan.session_type == DaySessionType.REST:
            return True
        if today_plan.training_session is None or not today_plan.training_session.blocks:
            return True
        return all(
            block.completed_at is not None or block.skipped_at is not None
            for block in today_plan.training_session.blocks
        )
