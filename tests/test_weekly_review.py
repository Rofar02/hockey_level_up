"""Weekly coach review ("Разбор недели", 2026-10-04, premium): written on
Monday morning for the previous Mon-Sun week -- numbers from the analytics
overview, text from the model (faked here), posted to the coach chat and
shown on Home until closed."""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.models.coach_chat import CoachChatMessage, CoachChatRole
from app.models.exercise import TargetStat
from app.models.user import User
from app.models.weekly_review import WeeklyReview
from app.services import coach_chat_service, weekly_review_service
from app.services.analytics_overview_service import AnalyticsOverviewService
from app.services.coach_chat_service import ZaiReply
from app.services.weekly_review_service import WeeklyReviewService, due_week_start
from tests.test_analytics_overview_service import TODAY, _exercise, _Plans, _user

LAST_MONDAY = TODAY - timedelta(days=TODAY.weekday() + 7)


def _install_model(monkeypatch, text: str = "Хорошая неделя. Держи темп.") -> dict:
    captured: dict = {"calls": 0}

    async def _fake_call_zai(api_key, base_url, model, system_prompt, messages, tools=None) -> ZaiReply:
        captured["calls"] += 1
        captured["system_prompt"] = system_prompt
        captured["content"] = messages[0]["content"]
        return ZaiReply(text=text)

    monkeypatch.setattr(coach_chat_service, "_call_zai", _fake_call_zai)
    monkeypatch.setattr(weekly_review_service, "get_settings", lambda: Settings(zai_api_key="test-key"))
    return captured


async def _user_with_last_week(db_session) -> User:
    user = _user()
    squat, squat_rows = _exercise("Присед", TargetStat.STRENGTH)
    db_session.add_all([user, squat])
    await db_session.flush()
    db_session.add_all(squat_rows)
    plans = _Plans(db_session, user)
    await plans.day(LAST_MONDAY, [(squat, "done")])
    await plans.day(LAST_MONDAY + timedelta(days=2), [(squat, "done")])
    await plans.day(LAST_MONDAY + timedelta(days=4), [(squat, "open")])
    return user


def _utc(local_day, hour: int) -> datetime:
    return datetime.combine(local_day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=hour)


def test_review_window_is_monday_morning_to_wednesday() -> None:
    user = User(timezone="UTC")
    monday = TODAY - timedelta(days=TODAY.weekday())
    assert due_week_start(user, _utc(monday, 7)) is None
    assert due_week_start(user, _utc(monday, 9)) == monday - timedelta(days=7)
    assert due_week_start(user, _utc(monday + timedelta(days=2), 23)) == monday - timedelta(days=7)
    assert due_week_start(user, _utc(monday + timedelta(days=3), 9)) is None


@pytest.mark.asyncio
async def test_overview_until_ends_the_period_on_that_day(db_session) -> None:
    user = await _user_with_last_week(db_session)

    overview = await AnalyticsOverviewService(db_session).get_overview(user, 7, until=LAST_MONDAY + timedelta(days=6))

    assert overview.regularity.planned_sessions == 3
    assert overview.regularity.completed_sessions == 2


@pytest.mark.asyncio
async def test_generate_stores_numbers_posts_to_chat_and_is_written_once(db_session, monkeypatch) -> None:
    user = await _user_with_last_week(db_session)
    captured = _install_model(monkeypatch)

    service = WeeklyReviewService(db_session)
    review = await service.generate(user, LAST_MONDAY)

    assert review is not None
    assert (review.sessions_completed, review.sessions_planned) == (2, 3)
    assert review.text == "Хорошая неделя. Держи темп."
    assert "выполнено 2 из 3" in captured["content"]
    message = await db_session.get(CoachChatMessage, review.message_id)
    assert message.role == CoachChatRole.ASSISTANT
    assert message.content == review.text

    assert await service.generate(user, LAST_MONDAY) is None
    assert captured["calls"] == 1


@pytest.mark.asyncio
async def test_no_review_for_an_empty_week(db_session, monkeypatch) -> None:
    user = _user()
    db_session.add(user)
    await db_session.flush()
    captured = _install_model(monkeypatch)

    assert await WeeklyReviewService(db_session).generate(user, LAST_MONDAY) is None
    assert captured["calls"] == 0
    assert (await db_session.scalars(select(WeeklyReview).where(WeeklyReview.user_id == user.id))).first() is None


@pytest.mark.asyncio
async def test_home_card_shows_review_until_read_and_only_to_its_owner(db_session, monkeypatch) -> None:
    user = await _user_with_last_week(db_session)
    stranger = _user()
    db_session.add(stranger)
    await db_session.flush()
    _install_model(monkeypatch)
    service = WeeklyReviewService(db_session)
    review = await service.generate(user, LAST_MONDAY)

    assert (await service.latest_for_card(user)).id == review.id
    assert await service.mark_read(stranger, review.id) is False
    assert await service.mark_read(user, review.id) is True
    assert await service.latest_for_card(user) is None


@pytest.mark.asyncio
async def test_empty_replies_stop_after_max_attempts(db_session, monkeypatch) -> None:
    user = await _user_with_last_week(db_session)
    user.has_premium = True
    await db_session.flush()
    _install_model(monkeypatch, text="   ")
    monkeypatch.setattr(weekly_review_service, "_failed_attempts", {})
    monkeypatch.setattr(
        weekly_review_service, "due_week_start", lambda u, now: LAST_MONDAY if u.id == user.id else None
    )

    @asynccontextmanager
    async def _session():
        yield db_session

    monkeypatch.setattr(weekly_review_service, "AsyncSessionLocal", _session)
    real_generate = WeeklyReviewService.generate
    generate_calls = 0

    async def _counting_generate(self, u, week_start):
        nonlocal generate_calls
        if u.id == user.id:
            generate_calls += 1
        return await real_generate(self, u, week_start)

    monkeypatch.setattr(WeeklyReviewService, "generate", _counting_generate)

    for _ in range(10):
        await weekly_review_service._review_tick()

    assert generate_calls == weekly_review_service.MAX_ATTEMPTS_PER_WEEK == 3
    assert (await db_session.scalars(select(WeeklyReview).where(WeeklyReview.user_id == user.id))).first() is None
