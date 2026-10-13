"""The offline workout queue against the real API (Б2, 2026-10-13).

The phone keeps every workout write in a queue and resends it until it hears
a 2xx, each with its own Idempotency-Key. These run the real app over HTTP on
real, committed data (separate connections -- the savepoint fixture can't show
a race); the player is deleted at the end, cascading everything they wrote.

- the same queue sent three times in a row, and three times in parallel ->
  every set, every completion once, XP (the block_completed event) once;
- cut off halfway and sent again -> nothing doubled, nothing lost;
- a set done at 23:50 and sent at 00:10 -> it's yesterday's, the streak holds;
- an action for a day that was rebuilt -> a clear 404, the rest goes through.
"""
import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.core.training_day import effective_performed_at
from app.db.session import engine as app_engine
from app.events.handlers.block_completed import streak_consumer
from app.main import app
from app.models.idempotency_key import IdempotencyKey
from app.models.outbox import OutboxEvent
from app.models.processed_event import ProcessedEvent
from app.models.progress import TrainingStreak
from app.models.schedule import SessionBlock
from app.models.set_completion import SetCompletion
from app.models.user import User

TZ = "Europe/Moscow"


@asynccontextmanager
async def _closing(client: httpx.AsyncClient):
    try:
        yield client
    finally:
        await client.aclose()


@pytest_asyncio.fixture
async def real_db():
    # The app's own engine pools connections per event loop -- each test
    # runs on a fresh loop, so it starts and ends with an empty pool.
    await app_engine.dispose()
    engine = create_async_engine(get_settings().database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    created: list[uuid.UUID] = []
    try:
        yield factory, created
    finally:
        try:
            await _delete_players(factory, created)
        finally:
            await engine.dispose()
            await app_engine.dispose()


async def _delete_players(factory, created: list[uuid.UUID]) -> None:
    # The dev backend's own consumers may be busy with these players' events
    # right now (stats, muscle load) -- a delete can deadlock with them, so
    # their outbox goes first and the delete is retried.
    for attempt in range(5):
        try:
            async with factory() as session:
                for user_id in created:
                    await session.execute(
                        delete(OutboxEvent).where(OutboxEvent.payload["user_id"].astext == str(user_id))
                    )
                    await session.execute(delete(User).where(User.id == user_id))
                await session.commit()
            return
        except DBAPIError:
            if attempt == 4:
                raise
            await asyncio.sleep(0.5)


async def _player(factory, created) -> tuple[User, httpx.AsyncClient]:
    unique = uuid.uuid4().hex[:8]
    user = User(
        id=uuid.uuid4(),
        username=f"queue_{unique}",
        email=f"queue_{unique}@example.com",
        password_hash=hash_password("password123"),
        timezone=TZ,
    )
    async with factory() as session:
        session.add(user)
        await session.commit()
    created.append(user.id)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {create_access_token(str(user.id))}"},
        timeout=30,
    )
    response = await client.post("/assessment/start-from-scratch")
    assert response.status_code in (200, 201), response.text
    return user, client


def _today() -> date:
    return datetime.now(ZoneInfo(TZ)).date()


async def _plan_today(client: httpx.AsyncClient) -> dict:
    today = _today()
    monday = today - timedelta(days=today.weekday())
    days = [
        {"date": (monday + timedelta(days=i)).isoformat(), "session_type": "off_ice" if monday + timedelta(days=i) == today else "rest"}
        for i in range(7)
    ]
    response = await client.post("/schedule/weekly", json={"days": days})
    assert response.status_code == 201, response.text
    plan = (await client.get(f"/schedule/day-plan?date={today.isoformat()}")).json()
    full = (await client.get(f"/schedule/day-plans/{plan['id']}")).json()
    assert full["training_session"]["blocks"], "an off-ice day comes with exercises"
    return full


def _queue_for(day: dict) -> list[dict]:
    """What the phone queues for a whole workout: one set per exercise, its
    feedback, the completion -- each action with its own key."""
    session_id = day["training_session"]["id"]
    actions: list[dict] = []
    for block in day["training_session"]["blocks"]:
        exercise = block["exercise"]
        body = {"exercise_id": exercise["id"], "training_session_id": session_id, "set_number": 1, "reps_completed": 10}
        if exercise.get("tracks_weight"):
            body["weight_kg"] = 10
        if exercise.get("tracks_duration"):
            body = {**body, "reps_completed": None, "duration_seconds_completed": 30}
        actions.append({"key": str(uuid.uuid4()), "method": "POST", "path": "/set-completions", "body": body})
        actions.append(
            {
                "key": str(uuid.uuid4()),
                "method": "POST",
                "path": "/set-completions/feedback",
                "body": {"exercise_id": exercise["id"], "training_session_id": session_id, "feedback": "normal"},
            }
        )
        actions.append({"key": str(uuid.uuid4()), "method": "POST", "path": f"/session-blocks/{block['id']}/complete", "body": {}})
    return actions


async def _send(client: httpx.AsyncClient, action: dict) -> httpx.Response:
    return await client.request(
        action["method"], action["path"], json=action["body"], headers={"Idempotency-Key": action["key"]}
    )


async def _send_all(client: httpx.AsyncClient, actions: list[dict]) -> list[int]:
    codes = []
    for action in actions:
        codes.append((await _send(client, action)).status_code)
    return codes


async def _counts(factory, user: User, day: dict) -> tuple[int, int, int]:
    session_id = uuid.UUID(day["training_session"]["id"])
    async with factory() as session:
        sets = await session.scalar(select(func.count()).select_from(SetCompletion).where(SetCompletion.user_id == user.id))
        done = await session.scalar(
            select(func.count())
            .select_from(SessionBlock)
            .where(SessionBlock.session_id == session_id, SessionBlock.completed_at.is_not(None))
        )
        xp_events = await session.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.event_type == "block_completed", OutboxEvent.payload["user_id"].astext == str(user.id))
        )
    return sets, done, xp_events


@pytest.mark.asyncio
async def test_the_same_queue_three_times_in_parallel_then_in_a_row(real_db) -> None:
    factory, created = real_db
    user, client = await _player(factory, created)
    async with _closing(client):
        day = await _plan_today(client)
        actions = _queue_for(day)
        blocks = len(day["training_session"]["blocks"])

        # Three copies of one queue at once, same keys (two tabs and a
        # retry, say) -- on a fresh day, so nothing is done yet.
        results = await asyncio.gather(*(_send_all(client, actions) for _ in range(3)))
        assert all(200 <= code < 300 for codes in results for code in codes), results
        assert await _counts(factory, user, day) == (blocks, blocks, blocks)

        for _ in range(3):
            codes = await _send_all(client, actions)
            assert all(200 <= code < 300 for code in codes), codes
        # Every set and completion once, the XP event once per exercise.
        assert await _counts(factory, user, day) == (blocks, blocks, blocks)
        async with factory() as session:
            keys = await session.scalar(
                select(func.count()).select_from(IdempotencyKey).where(IdempotencyKey.user_id == user.id)
            )
        assert keys == len(actions)


@pytest.mark.asyncio
async def test_a_repeat_gets_the_first_answer_back(real_db) -> None:
    factory, created = real_db
    user, client = await _player(factory, created)
    async with _closing(client):
        day = await _plan_today(client)
        action = _queue_for(day)[0]
        first = await _send(client, action)
        second = await _send(client, action)
        assert first.status_code == second.status_code == 201
        assert first.json() == second.json()
        async with factory() as session:
            keys = await session.scalar(
                select(func.count()).select_from(IdempotencyKey).where(IdempotencyKey.user_id == user.id)
            )
        assert keys == 1

        # The same key on a different request is the client's bug.
        clash = await client.post(
            f"/session-blocks/{day['training_session']['blocks'][0]['id']}/complete",
            json={},
            headers={"Idempotency-Key": action["key"]},
        )
        assert clash.status_code == 422


@pytest.mark.asyncio
async def test_cut_off_halfway_then_sent_again(real_db) -> None:
    factory, created = real_db
    user, client = await _player(factory, created)
    async with _closing(client):
        day = await _plan_today(client)
        actions = _queue_for(day)
        blocks = len(day["training_session"]["blocks"])
        half = len(actions) // 2
        await _send_all(client, actions[:half])
        # The connection dropped here; the queue still holds everything from
        # the last unconfirmed action on -- resent from the start to be safe.
        codes = await _send_all(client, actions)
        assert all(200 <= code < 300 for code in codes), codes
        assert await _counts(factory, user, day) == (blocks, blocks, blocks)


@pytest.mark.asyncio
async def test_a_set_at_23_50_sent_at_00_10_counts_for_yesterday(real_db) -> None:
    factory, created = real_db
    user, client = await _player(factory, created)
    async with _closing(client):
        day = await _plan_today(client)
        block = day["training_session"]["blocks"][0]
        # 23:50 the evening before, in the player's zone -- within 48 h.
        local_yesterday = _today() - timedelta(days=1)
        performed = datetime.combine(local_yesterday, datetime.min.time(), ZoneInfo(TZ)) + timedelta(hours=23, minutes=50)
        response = await client.post(
            f"/session-blocks/{block['id']}/complete",
            json={"performed_at": performed.isoformat()},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert response.status_code == 200, response.text
        assert datetime.fromisoformat(response.json()["completed_at"]) == performed

    async with factory() as session:
        event = await session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "block_completed",
                OutboxEvent.payload["session_block_id"].astext == block["id"],
            )
        )
    assert event.payload["activity_date"] == local_yesterday.isoformat()


@pytest.mark.asyncio
async def test_the_streak_follows_the_day_the_work_was_done(real_db, monkeypatch) -> None:
    """streak_consumer, fed the event of a workout finished yesterday at
    23:50 and synced today: yesterday is the active day, and the streak that
    ended the day before yesterday goes on instead of restarting."""
    factory, created = real_db
    user, client = await _player(factory, created)
    yesterday = _today() - timedelta(days=1)
    async with _closing(client):
        day = await _plan_today(client)
    block_id = day["training_session"]["blocks"][0]["id"]
    async with factory() as session:
        session.add(
            TrainingStreak(user_id=user.id, current_streak=4, longest_streak=4, last_activity_date=yesterday - timedelta(days=1))
        )
        await session.commit()

    from app.events.handlers import block_completed

    async def _fully_done(*_args) -> bool:
        return True

    async def _no_gap(*_args) -> bool:
        return False

    monkeypatch.setattr(block_completed, "is_session_fully_completed", _fully_done)
    monkeypatch.setattr(block_completed, "has_missed_training_day", _no_gap)
    event_id = uuid.uuid4()
    await streak_consumer(
        {"user_id": str(user.id), "session_block_id": block_id, "activity_date": yesterday.isoformat()}, event_id
    )
    async with factory() as session:
        streak = await session.scalar(select(TrainingStreak).where(TrainingStreak.user_id == user.id))
        await session.execute(delete(ProcessedEvent).where(ProcessedEvent.event_id == event_id))
        await session.commit()
    assert streak.last_activity_date == yesterday
    assert streak.current_streak == 5


@pytest.mark.asyncio
async def test_an_action_for_a_rebuilt_day_fails_clearly_the_rest_goes_through(real_db) -> None:
    factory, created = real_db
    user, client = await _player(factory, created)
    async with _closing(client):
        day = await _plan_today(client)
        actions = _queue_for(day)
        gone = {"key": str(uuid.uuid4()), "method": "POST", "path": f"/session-blocks/{uuid.uuid4()}/complete", "body": {}}
        codes = await _send_all(client, [actions[0], gone, *actions[1:]])
        assert codes[1] == 404
        assert all(200 <= code < 300 for i, code in enumerate(codes) if i != 1), codes
        blocks = len(day["training_session"]["blocks"])
        assert await _counts(factory, user, day) == (blocks, blocks, blocks)


def test_performed_at_is_trusted_only_within_reason() -> None:
    now = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
    assert effective_performed_at(None, now) == now
    assert effective_performed_at(now - timedelta(hours=3), now) == now - timedelta(hours=3)
    assert effective_performed_at(now + timedelta(minutes=3), now) == now  # clock a bit ahead: capped
    assert effective_performed_at(now + timedelta(hours=1), now) == now  # the future: server time
    assert effective_performed_at(now - timedelta(hours=49), now) == now  # too old: server time
