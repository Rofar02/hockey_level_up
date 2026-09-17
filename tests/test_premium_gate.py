"""require_premium (app/routers/deps.py): gates GET /users/me/analytics/*
on User.has_premium, same shape as require_admin gates /admin/* routes.
Tested by calling the dependency function directly with a plain User
object -- same convention require_admin-gated behavior would use if it had
a direct test (it currently doesn't; this is the first).

2026-09-17 (audit item #7): the coach-chat endpoints no longer use this --
CoachChatService.send_message applies its own smaller free-trial monthly
cap for has_premium=False instead of a flat 403 (see
FREE_TRIAL_MESSAGE_LIMIT in that module, exercised by
test_coach_chat_service.py), so every logged-in user reaches them now.
"""
import uuid

import pytest
from fastapi import HTTPException

from app.models.user import User
from app.routers.deps import require_premium


def _make_user(*, has_premium: bool) -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"premium_{unique}",
        email=f"premium_{unique}@example.com",
        password_hash="irrelevant",
        has_premium=has_premium,
    )


@pytest.mark.asyncio
async def test_require_premium_blocks_without_premium() -> None:
    user = _make_user(has_premium=False)

    with pytest.raises(HTTPException) as exc_info:
        await require_premium(user)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Эта функция доступна с премиум-подпиской"


@pytest.mark.asyncio
async def test_require_premium_allows_with_premium() -> None:
    user = _make_user(has_premium=True)

    result = await require_premium(user)

    assert result is user
