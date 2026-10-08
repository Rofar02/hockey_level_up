""""Путь новичка" (2026-10-08): tasks complete from what the player did, XP
once per task plus the finish bonus, a veteran's history is claimed without
XP on the first sync, and dismiss hides the card."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.coach_chat import CoachChatMessage, CoachChatRole
from app.models.schedule import WeeklyPlan
from app.models.user import User
from app.services.onboarding_service import FINISH_BONUS_XP, TASKS, OnboardingService
from tests.dates import utc_today

XP = {task.id: task.xp for task in TASKS}


async def _user(db_session, *, age_days: int = 0) -> User:
    unique = uuid.uuid4().hex[:8]
    user = User(
        id=uuid.uuid4(),
        username=f"onb_{unique}",
        email=f"onb_{unique}@example.com",
        password_hash="x",
        created_at=datetime.now(timezone.utc) - timedelta(days=age_days),
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _plan_week(db_session, user: User) -> None:
    db_session.add(WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=utc_today()))
    await db_session.flush()


@pytest.mark.asyncio
async def test_a_new_player_is_paid_once_per_task(db_session) -> None:
    user = await _user(db_session)
    service = OnboardingService(db_session)

    empty = await service.sync(user)
    assert empty.visible and empty.xp_awarded == 0 and not any(task.done for task in empty.tasks)

    await _plan_week(db_session, user)
    db_session.add(CoachChatMessage(user_id=user.id, role=CoachChatRole.USER, content="Привет"))
    await db_session.flush()
    paid = await service.sync(user)
    assert set(paid.newly_done) == {"plan_week", "ask_coach"}
    assert paid.xp_awarded == XP["plan_week"] + XP["ask_coach"]

    again = await service.sync(user)
    assert again.newly_done == [] and again.xp_awarded == 0
    await db_session.refresh(user)
    assert user.xp == XP["plan_week"] + XP["ask_coach"]


@pytest.mark.asyncio
async def test_a_veterans_history_is_claimed_without_xp(db_session) -> None:
    user = await _user(db_session, age_days=30)
    await _plan_week(db_session, user)

    first = await OnboardingService(db_session).sync(user)

    assert next(task for task in first.tasks if task.id == "plan_week").done
    assert first.newly_done == [] and first.xp_awarded == 0


@pytest.mark.asyncio
async def test_finishing_everything_pays_the_bonus_and_hides_the_card(db_session, monkeypatch) -> None:
    user = await _user(db_session)
    service = OnboardingService(db_session)
    await service.sync(user)

    async def _all_done(self, _user):
        return {task.id for task in TASKS}

    monkeypatch.setattr(OnboardingService, "_done_tasks", _all_done)
    finished = await service.sync(user)

    assert not finished.visible
    assert finished.xp_awarded == sum(XP.values()) + FINISH_BONUS_XP
    assert (await service.sync(user)).xp_awarded == 0


@pytest.mark.asyncio
async def test_dismiss_hides_the_card(db_session) -> None:
    user = await _user(db_session)
    service = OnboardingService(db_session)

    await service.dismiss(user)

    assert not (await service.sync(user)).visible
