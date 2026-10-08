"""TrainingDiaryService: a player's own free-text notebook entry for a
single ON_ICE or GAME TrainingSession -- the app has no structured content
for either, so this is the only way the player records what actually
happened, in their own words. Covers the save/get round-trip, upsert-in-
place on a second save, ownership (404 for someone else's session), the
ON_ICE/GAME-only gate (400 for OFF_ICE), list_entries (the "open my
diary" view across every session), and the report after an ice day or a
game (2026-10-08): what it stores, what it earns and when it earns nothing.
"""
import uuid
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.exercise import TargetStat
from app.models.progress import UserStat
from app.models.schedule import DayPlan, DaySessionType, TrainingSession, WeeklyPlan
from app.models.training_diary import GameResult, GameWorkOn, IceEffort, IceHighlight
from app.models.user import User
from app.schemas.training_diary import DiaryReportIn, TrainingDiaryEntryRead
from app.services.training_diary_service import (
    DIARY_STAT_REWARDS,
    REPORT_REWARD_WINDOW_DAYS,
    REPORT_XP,
    TrainingDiaryService,
    format_entry_for_coach,
    report_base_gains,
)
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


ICE_REPORT = DiaryReportIn(duration_minutes=60, effort=IceEffort.NORMAL)
GAME_REPORT = DiaryReportIn(game_result=GameResult.WIN, goals=1, assists=2, shots=4, self_rating=4)


async def _user(db_session) -> User:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.mark.asyncio
async def test_ice_report_credits_stats_and_xp_once(db_session) -> None:
    user = await _user(db_session)
    training_session = await _make_session(db_session, user, DaySessionType.ON_ICE)
    service = TrainingDiaryService(db_session)

    # A note alone (autosave while typing) earns nothing any more.
    first = await service.save_entry(user, training_session.id, "Хорошо покатался, обводка пошла")
    assert first.stat_rewards == {} and first.xp_reward == 0 and first.rewarded is False

    second = await service.save_entry(user, training_session.id, "Хорошо покатался", ICE_REPORT)
    assert second.stat_rewards == DIARY_STAT_REWARDS[DaySessionType.ON_ICE]  # 60 min, normal: base, no diminishing
    assert second.xp_reward == REPORT_XP[DaySessionType.ON_ICE]
    assert TrainingDiaryEntryRead.model_validate(second).rewarded is True
    assert second.reported_at is not None
    assert (second.duration_minutes, second.effort) == (60, IceEffort.NORMAL)
    await db_session.refresh(user)
    assert user.xp == REPORT_XP[DaySessionType.ON_ICE]

    # Re-submitting or editing the note never credits again.
    third = await service.save_entry(user, training_session.id, "Хорошо покатался!", ICE_REPORT)
    fourth = await service.save_entry(user, training_session.id, "Хорошо покатался!!")
    assert third.stat_rewards == {} and third.xp_reward == 0 and third.rewarded is True
    assert fourth.rewarded is True and fourth.duration_minutes == 60  # a note-only save keeps the report
    assert await _stats(db_session, user) == DIARY_STAT_REWARDS[DaySessionType.ON_ICE]
    await db_session.refresh(user)
    assert user.xp == REPORT_XP[DaySessionType.ON_ICE]


def test_ice_gains_scale_with_duration_effort_and_highlights() -> None:
    short_easy = report_base_gains(
        DaySessionType.ON_ICE, DiaryReportIn(duration_minutes=45, effort=IceEffort.EASY)
    )
    long_hard = report_base_gains(
        DaySessionType.ON_ICE, DiaryReportIn(duration_minutes=90, effort=IceEffort.HARD)
    )
    base = DIARY_STAT_REWARDS[DaySessionType.ON_ICE]
    for stat in base:
        assert short_easy[stat] < base[stat] < long_hard[stat]

    picked = report_base_gains(
        DaySessionType.ON_ICE,
        DiaryReportIn(
            duration_minutes=60,
            effort=IceEffort.NORMAL,
            highlights=[IceHighlight.PASSING, IceHighlight.SHOOTING, IceHighlight.GAME_READING],
        ),
    )
    assert picked[TargetStat.PUCK_HANDLING] == pytest.approx(base[TargetStat.PUCK_HANDLING] + 0.6)
    assert picked[TargetStat.INTELLECT] == pytest.approx(base[TargetStat.INTELLECT] + 0.3)
    assert picked[TargetStat.ON_ICE_SKATING] == base[TargetStat.ON_ICE_SKATING]


def test_game_gains_ignore_the_counters_and_the_self_rating() -> None:
    modest = DiaryReportIn(game_result=GameResult.LOSS, goals=0, assists=0, shots=0, self_rating=1)
    star = DiaryReportIn(game_result=GameResult.WIN, goals=4, assists=3, shots=12, self_rating=5)
    assert report_base_gains(DaySessionType.GAME, modest) == report_base_gains(DaySessionType.GAME, star)
    assert max(report_base_gains(DaySessionType.GAME, star), key=lambda s: report_base_gains(
        DaySessionType.GAME, star)[s]) == TargetStat.INTELLECT


@pytest.mark.asyncio
async def test_game_report_stores_counters_and_private_fields(db_session) -> None:
    user = await _user(db_session)
    training_session = await _make_session(db_session, user, DaySessionType.GAME)

    report = GAME_REPORT.model_copy(update={"work_on": [GameWorkOn.DEFENSE], "share_rating_with_coach": True})
    saved = await TrainingDiaryService(db_session).save_entry(user, training_session.id, None, report)

    assert (saved.game_result, saved.goals, saved.assists, saved.shots) == (GameResult.WIN, 1, 2, 4)
    assert saved.self_rating == 4 and saved.work_on == ["defense"] and saved.share_rating_with_coach is True
    assert saved.duration_minutes is None and saved.effort is None  # ice-only fields stay empty
    assert saved.xp_reward == REPORT_XP[DaySessionType.GAME]
    assert saved.stat_rewards[TargetStat.INTELLECT] == 2.0


@pytest.mark.asyncio
async def test_goalie_game_report_without_counters_is_accepted(db_session) -> None:
    user = await _user(db_session)
    training_session = await _make_session(db_session, user, DaySessionType.GAME)

    saved = await TrainingDiaryService(db_session).save_entry(
        user, training_session.id, None, DiaryReportIn(game_result=GameResult.DRAW, self_rating=3)
    )

    assert saved.goals is None and saved.assists is None and saved.shots is None
    assert saved.rewarded is True


@pytest.mark.asyncio
async def test_incomplete_report_is_rejected(db_session) -> None:
    user = await _user(db_session)
    ice = await _make_session(db_session, user, DaySessionType.ON_ICE)
    game = await _make_session(db_session, user, DaySessionType.GAME, day=utc_today() - timedelta(days=1))
    service = TrainingDiaryService(db_session)

    with pytest.raises(HTTPException) as ice_error:
        await service.save_entry(user, ice.id, None, DiaryReportIn(duration_minutes=60))
    with pytest.raises(HTTPException) as game_error:
        await service.save_entry(user, game.id, None, DiaryReportIn(game_result=GameResult.WIN))
    assert ice_error.value.status_code == game_error.value.status_code == 422


@pytest.mark.asyncio
async def test_skipped_day_is_closed_without_a_reward(db_session) -> None:
    user = await _user(db_session)
    training_session = await _make_session(db_session, user, DaySessionType.ON_ICE)

    saved = await TrainingDiaryService(db_session).save_entry(
        user, training_session.id, None, DiaryReportIn(skipped=True)
    )

    assert saved.skipped is True and saved.reported_at is not None
    assert saved.stat_rewards == {} and saved.xp_reward == 0 and saved.rewarded is False
    assert await _stats(db_session, user) == {}


@pytest.mark.asyncio
async def test_no_reward_for_a_future_day_or_after_the_window(db_session) -> None:
    user = await _user(db_session)
    future_session = await _make_session(
        db_session, user, DaySessionType.GAME, day=utc_today() + timedelta(days=3)
    )
    last_day = await _make_session(
        db_session, user, DaySessionType.ON_ICE, day=utc_today() - timedelta(days=REPORT_REWARD_WINDOW_DAYS)
    )
    too_late = await _make_session(
        db_session, user, DaySessionType.ON_ICE, day=utc_today() - timedelta(days=REPORT_REWARD_WINDOW_DAYS + 1)
    )
    service = TrainingDiaryService(db_session)

    future = await service.save_entry(user, future_session.id, None, GAME_REPORT)
    late = await service.save_entry(user, too_late.id, None, ICE_REPORT)
    in_time = await service.save_entry(user, last_day.id, None, ICE_REPORT)

    assert future.stat_rewards == {} and future.rewarded is False
    assert late.stat_rewards == {} and late.rewarded is False
    assert late.reported_at is not None  # still recorded, just not paid
    assert in_time.rewarded is True


@pytest.mark.asyncio
async def test_reports_reach_the_coach_as_plain_facts(db_session) -> None:
    user = await _user(db_session)
    ice = await _make_session(db_session, user, DaySessionType.ON_ICE, day=utc_today() - timedelta(days=1))
    game = await _make_session(db_session, user, DaySessionType.GAME)
    blank = await _make_session(db_session, user, DaySessionType.ON_ICE, day=utc_today() - timedelta(days=2))
    service = TrainingDiaryService(db_session)
    await service.save_entry(
        user, ice.id, None, ICE_REPORT.model_copy(update={"highlights": [IceHighlight.SKATING]})
    )
    await service.save_entry(
        user, game.id, "Ошибся во втором периоде", GAME_REPORT.model_copy(update={"work_on": [GameWorkOn.DEFENSE]})
    )
    await service.save_entry(user, blank.id, None)  # "Не буду писать" -- nothing to tell

    entries = await service.list_entries(user, only_with_content=True)

    assert [format_entry_for_coach(entry) for entry in entries] == [
        "победа, голы 1, передачи 2, броски 4, оценка себе 4/5, хочет поработать: игра в защите, "
        "«Ошибся во втором периоде»",
        "60 мин, нормально, лучше всего: катание",
    ]
