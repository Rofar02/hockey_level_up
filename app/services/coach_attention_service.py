"""Why the AI coach button in the tab bar should glow right now, if at all --
GET /users/me/coach-attention. One reason at most, highest priority first:

1. pending_action -- the coach proposed a change in chat and it's still
   waiting for the player to confirm or dismiss it.
2. checkin -- a temporary restriction ran out recently and the player
   hasn't talked to the coach since (the same moment checkin_scheduler
   pushes "Проверка самочувствия"; the glow is the in-app side of it, and
   doesn't need a push subscription).
3. first_visit -- the player has never written to the coach and never
   opened the chat.

Everything here is derived from existing rows; nothing is stored for the
glow itself except the "chat opened" marker, which reuses the coachmark
table (COACH_CHAT_OPENED_HINT).
"""
from datetime import datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.coach_chat import CoachChatMessage, CoachChatRole
from app.models.coach_chat_proposed_action import CoachActionStatus, CoachChatProposedAction
from app.models.user import User
from app.models.user_temporary_restriction import UserTemporaryRestriction
from app.repositories.coachmark_repository import CoachmarkRepository

CoachAttentionReason = Literal["pending_action", "checkin", "first_visit"]

# Marked seen by the frontend when the coach chat is opened (same endpoint
# as every other coachmark) -- ends the first_visit glow.
COACH_CHAT_OPENED_HINT = "coach-chat-opened"

# A proposal or a check-in older than this has gone stale -- no point
# nagging about it forever (proposals only expire when a newer one is made).
ATTENTION_WINDOW = timedelta(days=7)


class CoachAttentionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._coachmarks = CoachmarkRepository(session)

    async def get_reason(self, user: User, now: datetime | None = None) -> CoachAttentionReason | None:
        now = now or datetime.now(ZoneInfo("UTC"))
        if await self._has_pending_action(user, now):
            return "pending_action"
        if await self._has_unanswered_checkin(user, now):
            return "checkin"
        if await self._is_first_visit(user):
            return "first_visit"
        return None

    async def _has_pending_action(self, user: User, now: datetime) -> bool:
        result = await self._session.execute(
            select(func.count())
            .select_from(CoachChatProposedAction)
            .where(
                CoachChatProposedAction.user_id == user.id,
                CoachChatProposedAction.status == CoachActionStatus.PENDING,
                CoachChatProposedAction.created_at >= now - ATTENTION_WINDOW,
            )
        )
        return result.scalar_one() > 0

    async def _has_unanswered_checkin(self, user: User, now: datetime) -> bool:
        tz = ZoneInfo(user.timezone or "UTC")
        today = now.astimezone(tz).date()
        result = await self._session.execute(
            select(UserTemporaryRestriction).where(
                UserTemporaryRestriction.user_id == user.id,
                # Lifted early by the player = nothing to check on.
                UserTemporaryRestriction.lifted_at.is_(None),
                UserTemporaryRestriction.expires_at <= today,
                UserTemporaryRestriction.expires_at >= today - ATTENTION_WINDOW,
            )
        )
        expired = result.scalars().all()
        if not expired:
            return False
        # "Answered" = the player wrote to the coach after the latest of
        # those restrictions ran out (start of that day, their time).
        since = max(datetime.combine(r.expires_at, time.min, tzinfo=tz) for r in expired)
        return not await self._has_user_message(user, since=since)

    async def _is_first_visit(self, user: User) -> bool:
        if await self._has_user_message(user):
            return False
        seen = await self._coachmarks.list_seen_hint_ids(user.id)
        return COACH_CHAT_OPENED_HINT not in seen

    async def _has_user_message(self, user: User, since: datetime | None = None) -> bool:
        query = (
            select(func.count())
            .select_from(CoachChatMessage)
            .where(CoachChatMessage.user_id == user.id, CoachChatMessage.role == CoachChatRole.USER)
        )
        if since is not None:
            query = query.where(CoachChatMessage.created_at >= since)
        result = await self._session.execute(query)
        return result.scalar_one() > 0
