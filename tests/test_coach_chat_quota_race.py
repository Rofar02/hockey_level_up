"""Coach chat quota under parallel sends (2026-10-13, А9): five requests
fired at once by a player one message short of the limit -- exactly one
gets through. And a send the LLM never answers doesn't eat the quota."""
import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings
from app.models.coach_chat import CoachChatMessage, CoachChatRole
from app.models.user import User
from app.services import coach_chat_service
from app.services.coach_chat_service import FREE_TRIAL_MESSAGE_LIMIT, CoachChatService, ZaiReply


def _user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"race_{unique}",
        email=f"race_{unique}@example.com",
        password_hash="irrelevant",
        has_premium=False,
        timezone="UTC",
    )


@pytest.mark.asyncio
async def test_parallel_sends_cannot_slip_past_the_limit(monkeypatch) -> None:
    # Real commits from separate connections -- the savepoint fixture can't
    # show a race. Everything written is deleted at the end.
    engine = create_async_engine(get_settings().database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    user = _user()
    async with factory() as session:
        session.add(user)
        await session.flush()
        now = datetime.now(timezone.utc)
        session.add_all(
            CoachChatMessage(user_id=user.id, role=CoachChatRole.USER, content=f"m{i}", created_at=now)
            for i in range(FREE_TRIAL_MESSAGE_LIMIT - 1)
        )
        await session.commit()

    async def _slow_reply(*_args, **_kwargs) -> ZaiReply:
        await asyncio.sleep(0.3)
        return ZaiReply(text="ответ")

    monkeypatch.setattr(coach_chat_service, "_call_zai", _slow_reply)
    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: Settings(zai_api_key="test-key"))

    async def _send(index: int) -> str:
        async with factory() as session:
            player = await session.get(User, user.id)
            try:
                await CoachChatService(session).send_message(player, f"параллельно {index}")
                return "ok"
            except HTTPException as exc:
                return str(exc.status_code)

    try:
        results = await asyncio.gather(*(_send(i) for i in range(5)))
        assert sorted(results) == ["429", "429", "429", "429", "ok"]
        async with factory() as session:
            sent = await session.scalar(
                select(func.count()).where(CoachChatMessage.user_id == user.id, CoachChatMessage.role == CoachChatRole.USER)
            )
        assert sent == FREE_TRIAL_MESSAGE_LIMIT
    finally:
        async with factory() as session:
            await session.execute(delete(User).where(User.id == user.id))
            await session.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_failed_reply_does_not_eat_the_quota(db_session, monkeypatch) -> None:
    user = _user()
    user_id = user.id
    db_session.add(user)
    await db_session.flush()

    async def _down(*_args, **_kwargs):
        raise HTTPException(status_code=502, detail="down")

    monkeypatch.setattr(coach_chat_service, "_call_zai", _down)
    monkeypatch.setattr(coach_chat_service, "get_settings", lambda: Settings(zai_api_key="test-key"))

    with pytest.raises(HTTPException):
        await CoachChatService(db_session).send_message(user, "вопрос")
    count = await db_session.scalar(select(func.count()).where(CoachChatMessage.user_id == user_id))
    assert count == 0
