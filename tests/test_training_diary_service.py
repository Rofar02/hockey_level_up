"""TrainingDiaryService: a player's own free-text notebook entry for a
single ON_ICE or GAME TrainingSession -- the app has no structured content
for either, so this is the only way the player records what actually
happened, in their own words. Covers the save/get round-trip, upsert-in-
place on a second save, ownership (404 for someone else's session), the
ON_ICE/GAME-only gate (400 for OFF_ICE), list_entries (the "open my
diary" view across every session), and the stat reward a real note earns
for an ice/game day (2026-10-08).
"""
import uuid
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.exercise import TargetStat
from app.models.progress import UserStat
from app.models.schedule import DayPlan, DaySessionType, TrainingSession, WeeklyPlan
from app.models.user import User
from app.schemas.training_diary import TrainingDiaryEntryRead
from app.services.training_diary_service import DIARY_STAT_REWARDS, TrainingDiaryService
from tests.dates import utc_today


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"diary_{unique}",
        email=f"diary_{unique}@example.com",
        password_hash="irrelevant",
    )


async def _make_session(
    db_session, user: User, session_type: DaySessionType, *, day: date | None = None
) -> TrainingSession:
    day = day or utc_today()
    training_session = TrainingSession(id=uuid.uuid4(), blocks=[])
    day_plan = DayPlan(
        id=uuid.uuid4(), date=day, session_type=session_type, training_session=training_session
    )
    weekly_plan = WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=day, day_plans=[day_plan])
    db_session.add(weekly_plan)
    await db_session.flush()
    return training_session


@pytest.mark.asyncio
async def test_save_and_get_round_trip_for_on_ice_session(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    training_session = await _make_session(db_session, user, DaySessionType.ON_ICE)

    service = TrainingDiaryService(db_session)
    saved = await service.save_entry(
        user=user,
        training_session_id=training_session.id,
        note="Хорошо получалась обводка, но медленно катаюсь спиной вперёд",
    )
    assert saved.note is not None

    fetched = await service.get_entry(user, training_session.id)
    assert fetched is not None
    assert fetched.id == saved.id
    assert fetched.note == saved.note


@pytest.mark.asyncio
async def test_saved_entry_survives_pydantic_validation(db_session) -> None:
    """Regression test: created_at/updated_at are server-computed
    (func.now()/onupdate), never set in Python -- reading either straight
    off the object save_entry returns used to trigger an implicit lazy
    load outside any awaited context (SQLAlchemy's async mode requires
    that inside a greenlet), which blew up as MissingGreenlet the moment
    PUT /training-sessions/{id}/diary's router ran
    TrainingDiaryEntryRead.model_validate(entry) on it -- every real save
    500'd, live, while every prior test here only ever read Python-set
    attributes (note, id) and so never touched the broken path at all.
    The exact router call, not just an attribute poke, so this fails the
    same way the live bug did if the fix regresses."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    training_session = await _make_session(db_session, user, DaySessionType.ON_ICE)

    service = TrainingDiaryService(db_session)
    saved = await service.save_entry(
        user=user, training_session_id=training_session.id, note="проверка сериализации"
    )

    schema = TrainingDiaryEntryRead.model_validate(saved)
    assert schema.created_at is not None
    assert schema.updated_at is not None


@pytest.mark.asyncio
async def test_save_and_get_round_trip_for_game_session(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    training_session = await _make_session(db_session, user, DaySessionType.GAME)

    service = TrainingDiaryService(db_session)
    saved = await service.save_entry(
        user=user, training_session_id=training_session.id, note="2 гола, 1 передача"
    )

    fetched = await service.get_entry(user, training_session.id)
    assert fetched is not None
    assert fetched.note == saved.note


@pytest.mark.asyncio
async def test_get_entry_returns_none_when_nothing_saved_yet(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    training_session = await _make_session(db_session, user, DaySessionType.ON_ICE)

    service = TrainingDiaryService(db_session)
    assert await service.get_entry(user, training_session.id) is None


@pytest.mark.asyncio
async def test_second_save_upserts_in_place_not_a_new_row(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    training_session = await _make_session(db_session, user, DaySessionType.ON_ICE)

    service = TrainingDiaryService(db_session)
    first = await service.save_entry(
        user=user, training_session_id=training_session.id, note="черновик"
    )
    second = await service.save_entry(
        user=user, training_session_id=training_session.id, note="финальная версия"
    )

    assert second.id == first.id
    fetched = await service.get_entry(user, training_session.id)
    assert fetched is not None
    assert fetched.note == "финальная версия"


@pytest.mark.asyncio
async def test_save_entry_rejects_someone_elses_session(db_session) -> None:
    owner = _make_user()
    stranger = _make_user()
    db_session.add_all([owner, stranger])
    await db_session.flush()
    training_session = await _make_session(db_session, owner, DaySessionType.ON_ICE)

    service = TrainingDiaryService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.save_entry(user=stranger, training_session_id=training_session.id, note="not mine")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_entry_rejects_unknown_session(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = TrainingDiaryService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.get_entry(user, uuid.uuid4())
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_save_entry_rejects_off_ice_session(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    training_session = await _make_session(db_session, user, DaySessionType.OFF_ICE)

    service = TrainingDiaryService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.save_entry(
            user=user, training_session_id=training_session.id, note="off-ice notes"
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_get_entry_rejects_off_ice_session(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    training_session = await _make_session(db_session, user, DaySessionType.OFF_ICE)

    service = TrainingDiaryService(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.get_entry(user, training_session.id)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_list_entries_returns_newest_first_with_date_and_session_type(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    today = utc_today()
    older_session = await _make_session(
        db_session, user, DaySessionType.ON_ICE, day=today - timedelta(days=7)
    )
    newer_session = await _make_session(db_session, user, DaySessionType.GAME, day=today)

    service = TrainingDiaryService(db_session)
    await service.save_entry(user=user, training_session_id=older_session.id, note="старая запись")
    await service.save_entry(user=user, training_session_id=newer_session.id, note="новая запись")

    entries = await service.list_entries(user)

    assert [e.note for e in entries] == ["новая запись", "старая запись"]
    assert entries[0].date == today
    assert entries[0].session_type == DaySessionType.GAME
    assert entries[1].date == today - timedelta(days=7)
    assert entries[1].session_type == DaySessionType.ON_ICE


@pytest.mark.asyncio
async def test_list_entries_excludes_other_users_and_unwritten_sessions(db_session) -> None:
    user = _make_user()
    other = _make_user()
    db_session.add_all([user, other])
    await db_session.flush()
    mine = await _make_session(db_session, user, DaySessionType.ON_ICE)
    theirs = await _make_session(db_session, other, DaySessionType.ON_ICE)
    # Different day than `mine` -- same user, same day would collide on
    # WeeklyPlan's (user_id, week_start_date) unique constraint.
    await _make_session(
        db_session, user, DaySessionType.ON_ICE, day=utc_today() - timedelta(days=14)
    )  # never written to

    service = TrainingDiaryService(db_session)
    await service.save_entry(user=user, training_session_id=mine.id, note="mine")
    await service.save_entry(user=other, training_session_id=theirs.id, note="theirs")

    entries = await service.list_entries(user)

    assert [e.note for e in entries] == ["mine"]


@pytest.mark.asyncio
async def test_list_entries_empty_for_a_user_with_no_diary_yet(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = TrainingDiaryService(db_session)
    assert await service.list_entries(user) == []


async def _stats(db_session, user: User) -> dict[TargetStat, float]:
    rows = await db_session.execute(
        select(UserStat.stat_type, UserStat.current_value).where(UserStat.user_id == user.id)
    )
    return dict(rows.all())


@pytest.mark.asyncio
async def test_diary_note_credits_ice_day_stats_once(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    training_session = await _make_session(db_session, user, DaySessionType.ON_ICE)
    service = TrainingDiaryService(db_session)

    # Autosave mid-typing: too short to count yet.
    first = await service.save_entry(user=user, training_session_id=training_session.id, note="Покатался")
    assert first.stat_rewards == {}
    assert first.rewarded is False
    assert await _stats(db_session, user) == {}

    note = "Хорошо покатался, обводка пошла, устал к концу"
    second = await service.save_entry(user=user, training_session_id=training_session.id, note=note)
    assert second.stat_rewards == DIARY_STAT_REWARDS[DaySessionType.ON_ICE]  # from 0: no diminishing yet
    assert TrainingDiaryEntryRead.model_validate(second).rewarded is True
    assert await _stats(db_session, user) == DIARY_STAT_REWARDS[DaySessionType.ON_ICE]

    third = await service.save_entry(user=user, training_session_id=training_session.id, note=note + "!")
    assert third.stat_rewards == {}
    assert third.rewarded is True
    assert (await service.get_entry(user, training_session.id)).rewarded is True
    assert await _stats(db_session, user) == DIARY_STAT_REWARDS[DaySessionType.ON_ICE]


@pytest.mark.asyncio
async def test_game_diary_leans_on_intellect(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    training_session = await _make_session(db_session, user, DaySessionType.GAME)

    saved = await TrainingDiaryService(db_session).save_entry(
        user=user, training_session_id=training_session.id, note="Выиграли 3:2, я ошибся в защите во втором периоде"
    )

    assert saved.stat_rewards[TargetStat.INTELLECT] == 2.0
    assert max(saved.stat_rewards, key=saved.stat_rewards.get) == TargetStat.INTELLECT


@pytest.mark.asyncio
async def test_no_diary_reward_for_skip_or_future_day(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    today_session = await _make_session(db_session, user, DaySessionType.ON_ICE)
    future_session = await _make_session(
        db_session, user, DaySessionType.GAME, day=utc_today() + timedelta(days=3)
    )
    service = TrainingDiaryService(db_session)

    skipped = await service.save_entry(user=user, training_session_id=today_session.id, note=None)
    future = await service.save_entry(
        user=user, training_session_id=future_session.id, note="Планирую играть первым номером в звене"
    )

    assert skipped.stat_rewards == {} and skipped.rewarded is False
    assert future.stat_rewards == {} and future.rewarded is False
    assert await _stats(db_session, user) == {}
