import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import TrainingPhase
from app.models.schedule import SessionBlock
from app.models.user import User
from app.repositories.exercise_repository import ExerciseRepository
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.schedule_repository import ScheduleRepository
from app.schemas.exercise import exercise_to_read
from app.schemas.schedule import SessionBlockRead
from app.services.training_party_service import TrainingPartyService

BLOCK_COMPLETED_EVENT = "block_completed"
# Read directly from outbox_events for the friend activity feed
# (FriendActivityService) -- no consumer registered, nothing needs to react
# to it, only display it after the fact.
TRAINING_COMPLETED_EVENT = "training_completed"


class SessionBlockService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._schedule = ScheduleRepository(session)
        self._outbox = OutboxRepository(session)
        self._parties = TrainingPartyService(session)
        self._exercises = ExerciseRepository(session)

    async def complete_block(self, block_id: uuid.UUID, user: User) -> SessionBlockRead:
        block = await self._schedule.get_session_block_with_owner(block_id)
        if block is None or block.session.day_plan.weekly_plan.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Session block not found"
            )

        if block.completed_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="already completed"
            )

        block.completed_at = datetime.now(timezone.utc)
        target_stats = await self._exercises.list_target_stats(block.exercise_id)
        # Outbox pattern: the event row is written in the same transaction as
        # completed_at, instead of publishing to RabbitMQ directly here. That
        # way a broker outage can't leave the block "burned" (completed with
        # no event ever sent) -- either both commit or neither does. A
        # separate relay task (app/events/outbox_relay.py) delivers the row
        # to RabbitMQ afterwards, independent of this request.
        self._outbox.add(
            BLOCK_COMPLETED_EVENT,
            {
                "user_id": str(user.id),
                "session_block_id": str(block.id),
                "exercise_id": str(block.exercise_id),
                "target_stats": [stat.value for stat in target_stats],
                "difficulty_level": block.exercise.difficulty_level,
            },
        )
        await self._maybe_publish_training_completed(block, user)
        await self._session.commit()
        # response_model=SessionBlockRead needs exercise.target_stats, which
        # isn't a plain ORM attribute (see exercise_to_read's docstring) --
        # returning `block` directly here 500s on every call since FastAPI's
        # response validation can't populate it from from_attributes alone.
        return SessionBlockRead(
            id=block.id,
            phase=block.phase,
            order=block.order,
            completed_at=block.completed_at,
            skipped_at=block.skipped_at,
            exercise=exercise_to_read(block.exercise, target_stats),
        )

    async def skip_block(self, block_id: uuid.UUID, user: User) -> SessionBlockRead:
        block = await self._schedule.get_session_block_with_owner(block_id)
        if block is None or block.session.day_plan.weekly_plan.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Session block not found"
            )

        # Server-side enforcement of the warmup/cooldown-only rule (media-
        # player redesign, 2026-08-28) -- MAIN work must always be logged for
        # real, never trusted from a frontend-only guard.
        if block.phase not in (TrainingPhase.WARMUP, TrainingPhase.COOLDOWN):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="only warmup/cooldown blocks can be skipped",
            )

        if block.completed_at is not None or block.skipped_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="already resolved"
            )

        block.skipped_at = datetime.now(timezone.utc)
        # Deliberately no BLOCK_COMPLETED_EVENT outbox row here -- a skip
        # earns no stat/XP/muscle-load gain, that's the whole point. It still
        # resolves the block for session/streak-completion purposes though,
        # so the "any remaining unresolved blocks" check below (and every
        # other completed_at.is_(None) consumer updated alongside this
        # feature) treats skipped_at the same as completed_at.
        await self._maybe_publish_training_completed(block, user)
        await self._session.commit()
        target_stats = await self._exercises.list_target_stats(block.exercise_id)
        return SessionBlockRead(
            id=block.id,
            phase=block.phase,
            order=block.order,
            completed_at=block.completed_at,
            skipped_at=block.skipped_at,
            exercise=exercise_to_read(block.exercise, target_stats),
        )

    async def _maybe_publish_training_completed(self, block: SessionBlock, user: User) -> None:
        # Flush first so the count below sees *this* block's just-set
        # completed_at/skipped_at too -- it isn't persisted yet otherwise,
        # and every sibling block in the session would need to already be
        # resolved for the count to reach zero.
        await self._session.flush()
        remaining = await self._session.execute(
            select(func.count())
            .select_from(SessionBlock)
            .where(
                SessionBlock.session_id == block.session_id,
                SessionBlock.completed_at.is_(None),
                SessionBlock.skipped_at.is_(None),
            )
        )
        if remaining.scalar_one() > 0:
            return
        # A block can only ever transition incomplete -> complete once (the
        # already-completed check above 409s on a repeat), so "all blocks in
        # this session are complete" flips from false to true at exactly one
        # call across the session's lifetime -- this fires exactly once per
        # training, never on a later no-op re-check.
        self._outbox.add(
            TRAINING_COMPLETED_EVENT,
            {
                "user_id": str(user.id),
                "training_session_id": str(block.session_id),
                "day_plan_id": str(block.session.day_plan_id),
                "session_type": block.session.day_plan.session_type.value,
            },
        )
        # Same transaction as the event above -- if this user's completion
        # was the last piece a TrainingParty targeting today was waiting on,
        # it flips to COMPLETED and publishes party_completed right here too.
        await self._parties.try_complete_parties_for(user.id, block.session.day_plan.date)
