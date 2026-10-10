"""Weekly tasks from the coach (step 7) and the coach's ice theme (7.1),
2026-10-09.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.core.coach_tasks import CoachTaskSpec, CoachTaskType, parse_spec, task_title, template_specs
from app.core.ice_focus import FOCUS_BY_ID, pick_focus_with_priorities
from app.models.coach_chat_proposed_action import CoachActionType
from app.models.schedule import DayPlan, DaySessionType, TrainingSession, WeeklyPlan
from app.models.training_diary import TrainingDiaryEntry
from app.models.user import User
from app.services.coach_chat_service import CoachChatService, looks_like_unproposed_offer
from app.services.coach_task_service import CoachTaskService

MONDAY = date(2026, 3, 9)


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(id=uuid.uuid4(), username=f"ct_{unique}", email=f"ct_{unique}@example.com", password_hash="x", timezone="UTC")
    defaults.update(overrides)
    return User(**defaults)


def test_templates_follow_the_weeks_plan() -> None:
    specs = template_specs(trainings=3, ice_like=1)
    assert [s.type for s in specs] == [
        CoachTaskType.COMPLETE_TRAININGS,
        CoachTaskType.ICE_REPORTS,
        CoachTaskType.NO_MISSED_DAY,
    ]
    assert specs[0].count == 3 and specs[1].count == 1
    assert template_specs(0, 0) == []


def test_ai_tasks_are_typed_and_in_range_or_dropped() -> None:
    assert parse_spec({"type": "complete_trainings", "count": 3}) == CoachTaskSpec(CoachTaskType.COMPLETE_TRAININGS, 3)
    assert parse_spec({"type": "lift_heavier", "count": 3}) is None
    assert parse_spec({"type": "complete_trainings", "count": 40}) is None
    assert parse_spec({"type": "ice_focus", "count": 2, "focus_id": "nope"}) is None
    assert parse_spec({"type": "ice_focus", "count": 2, "focus_id": "skate_first_steps"}).focus_id == "skate_first_steps"
    assert parse_spec("not a dict") is None


def test_titles_read_naturally() -> None:
    assert task_title(CoachTaskSpec(CoachTaskType.COMPLETE_TRAININGS, 3)) == "Закрой 3 тренировки за неделю"
    assert "Взрывной старт" in task_title(CoachTaskSpec(CoachTaskType.ICE_FOCUS, 2, "skate_first_steps"))


async def _week(db_session, user, kinds_done: list[tuple[DaySessionType, bool]], start: date) -> list[DayPlan]:
    """A week of day plans with empty sessions -- enough for the planned
    counts and the diary-based tasks (the `done` flag is only a label)."""
    days = []
    for offset, (kind, _done) in enumerate(kinds_done):
        session = TrainingSession(id=uuid.uuid4(), blocks=[])
        days.append(DayPlan(id=uuid.uuid4(), date=start + timedelta(days=offset), session_type=kind, training_session=session))
    db_session.add(WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=start, day_plans=days))
    await db_session.flush()
    return days


@pytest.mark.asyncio
async def test_template_tasks_created_on_first_look_and_counted(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    days = await _week(
        db_session,
        user,
        [(DaySessionType.OFF_ICE, True), (DaySessionType.ON_ICE, True), (DaySessionType.REST, False)]
        + [(DaySessionType.REST, False)] * 4,
        MONDAY,
    )
    db_session.add(
        TrainingDiaryEntry(user_id=user.id, training_session_id=days[1].training_session.id, reported_at=datetime.now(timezone.utc))
    )
    await db_session.flush()

    tasks = await CoachTaskService(db_session).list_for_week(user, today=MONDAY + timedelta(days=2))

    by_type = {t.type: t for t in tasks}
    assert set(by_type) == {"complete_trainings", "ice_reports", "no_missed_day"}
    assert (by_type["ice_reports"].progress, by_type["ice_reports"].target) == (1, 1)
    assert by_type["ice_reports"].done is True
    assert all(t.source == "template" for t in tasks)


@pytest.mark.asyncio
async def test_ai_reply_saved_and_unknown_dropped(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    service = CoachTaskService(db_session)
    reply = 'Вот: [{"type": "complete_trainings", "count": 3}, {"type": "bench_100kg"}, {"type": "no_missed_day"}]'

    saved = await service.save_ai_reply(user.id, MONDAY, reply)
    tasks = await service.list_for_week(user, today=MONDAY)

    assert saved == 2
    assert {t.type for t in tasks} == {"complete_trainings", "no_missed_day"}
    assert all(t.source == "coach" for t in tasks)
    assert await service.save_ai_reply(user.id, MONDAY + timedelta(days=7), "no json here") == 0


@pytest.mark.asyncio
async def test_claim_only_when_done_and_once(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    service = CoachTaskService(db_session)
    today = datetime.now(timezone.utc).date()
    monday = today - timedelta(days=today.weekday())
    await service.save_specs(user.id, monday, [CoachTaskSpec(CoachTaskType.ICE_REPORTS, 1)], "template")
    task = (await service.list_for_week(user))[0]

    with pytest.raises(HTTPException):
        await service.claim(user, task.id)

    days = await _week(db_session, user, [(DaySessionType.ON_ICE, False)], monday)
    db_session.add(
        TrainingDiaryEntry(user_id=user.id, training_session_id=days[0].training_session.id, reported_at=datetime.now(timezone.utc))
    )
    await db_session.flush()
    claimed = await service.claim(user, task.id)
    assert claimed.claimed is True
    with pytest.raises(HTTPException):
        await service.claim(user, task.id)


# -- 7.1 --


def test_focus_order_coach_then_work_on_then_priority_then_stat() -> None:
    focus, reason = pick_focus_with_priorities(1, {}, ["skating"], ["puck_protect"], "20.10", ["Взрывной старт"])
    assert focus.id == "puck_protect" and reason == "Тренер поставил фокус до 20.10"

    focus, reason = pick_focus_with_priorities(1, {}, None, None, None, ["Взрывной старт"])
    assert focus.id in {"skate_first_steps", "skate_stops"} and reason == "Ваш приоритет — Взрывной старт"

    focus, reason = pick_focus_with_priorities(1, {}, None, None, None, ["Мобильность"])
    assert "самый низкий стат" in reason


def test_unproposed_offer_detection() -> None:
    assert looks_like_unproposed_offer("Могу записать ограничение на колено. Записать?")
    assert not looks_like_unproposed_offer("Хорошая неделя, так держать.")


@pytest.mark.asyncio
async def test_set_ice_focus_payload_is_validated_and_confirm_sets_theme(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    chat = CoachChatService(db_session)

    assert await chat._resolve_action_payload(CoachActionType.SET_ICE_FOCUS, {"focus_ids": ["made_up"]}) is None
    assert await chat._resolve_action_payload(CoachActionType.SET_ICE_FOCUS, {"focus_ids": []}) is None
    payload = await chat._resolve_action_payload(
        CoachActionType.SET_ICE_FOCUS, {"focus_ids": ["skate_first_steps", "skate_first_steps", "skate_stops"]}
    )
    assert payload["focus_ids"] == ["skate_first_steps", "skate_stops"]
    assert payload["titles"] == [FOCUS_BY_ID["skate_first_steps"].title, FOCUS_BY_ID["skate_stops"].title]

    from app.models.coach_chat import CoachChatMessage, CoachChatRole
    from app.models.coach_chat_proposed_action import CoachChatProposedAction

    message = CoachChatMessage(user_id=user.id, role=CoachChatRole.ASSISTANT, content="Поставлю фокус?")
    db_session.add(message)
    await db_session.flush()
    action = CoachChatProposedAction(
        message_id=message.id, user_id=user.id, action_type=CoachActionType.SET_ICE_FOCUS, payload=payload
    )
    db_session.add(action)
    await db_session.flush()

    await chat.confirm_action(user, action.id)

    refreshed = await db_session.get(User, user.id)
    assert refreshed.coach_ice_focus_ids == ["skate_first_steps", "skate_stops"]
    assert refreshed.coach_ice_focus_until == datetime.now(timezone.utc).date() + timedelta(days=14)
