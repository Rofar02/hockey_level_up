import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.training_block import (
    SESSIONS_TO_ADVANCE_PHASE,
    is_macrocycle_deload_block,
    next_phase,
    phase_transition_due,
)
from app.models.schedule import TrainingBlock
from app.models.user import User
from app.repositories.training_block_repository import TrainingBlockRepository
from app.schemas.training_block import TrainingBlockRead


class TrainingBlockService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._blocks = TrainingBlockRepository(session)

    async def get_current(self, user_id: uuid.UUID, *, today: date | None = None) -> TrainingBlockRead:
        block = await self.resolve_active_block(user_id, today=today)
        if block is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No training block yet -- declare a weekly plan first",
            )
        # resolve_active_block may have mutated/rolled over the block (a GET
        # catching up periodization state that should have already advanced
        # by now) -- commit here since, unlike create_weekly_plan's own
        # request, nothing else in this read path would otherwise persist it.
        await self._session.commit()
        sessions_completed = await self.count_sessions_completed_in_phase(block)
        return TrainingBlockRead(
            block_number=block.block_number,
            phase=block.phase,
            sessions_completed_in_phase=sessions_completed,
            sessions_to_advance=SESSIONS_TO_ADVANCE_PHASE,
            is_macrocycle_deload=block.is_macrocycle_deload,
        )

    async def get_by_id(self, block_id: uuid.UUID) -> TrainingBlock | None:
        return await self._blocks.get_by_id(block_id)

    async def count_sessions_completed_in_phase(self, block: TrainingBlock) -> int:
        return await self._blocks.count_completed_real_sessions(block.id, since=block.phase_started_at)

    async def resolve_active_block(
        self, user_id: uuid.UUID, *, today: date | None = None
    ) -> TrainingBlock | None:
        """The user's active TrainingBlock, advancing its phase (or rolling
        over to a new block on deload's completion) as many times as
        already-elapsed session counts/calendar time justify. Returns None
        if the user has no TrainingBlock at all yet -- this method only
        advances an existing one, it never creates the first one (see
        get_or_create_and_resolve for that).

        Idempotent and safe to call from a read path: advancing is driven
        entirely by querying real state (completed sessions, elapsed
        calendar time), not by a counter that could double-advance on a
        repeat call.

        `today` defaults to date.today() for every real caller -- injectable
        purely so tests can simulate the passage of time between phase
        transitions without waiting on the wall clock (see
        test_training_block_progression.py).
        """
        block = await self._blocks.get_active_for_user(user_id)
        if block is None:
            return None
        return await self._catch_up(block, today or date.today())

    async def get_or_create_and_resolve(
        self, user_id: uuid.UUID, *, today: date | None = None
    ) -> TrainingBlock:
        """Same as resolve_active_block, but creates block_number=1/
        phase=ACCUMULATION when the user has no TrainingBlock yet -- used by
        ScheduleService, which (unlike a bare GET) needs a block to assemble
        a session against even for a brand-new user's very first week.
        """
        block = await self.resolve_active_block(user_id, today=today)
        if block is not None:
            return block
        return await self._blocks.create(
            TrainingBlock(user_id=user_id, block_number=1, phase_started_at=today or date.today())
        )

    async def _catch_up(self, block: TrainingBlock, today: date) -> TrainingBlock:
        while True:
            sessions_completed = await self.count_sessions_completed_in_phase(block)
            weeks_elapsed = (today - block.phase_started_at).days // 7
            if not phase_transition_due(
                sessions_completed_in_phase=sessions_completed, weeks_since_phase_started=weeks_elapsed
            ):
                return block
            block = await self._advance(block, today)

    async def _advance(self, block: TrainingBlock, today: date) -> TrainingBlock:
        upcoming = next_phase(block.phase)
        if upcoming is not None:
            block.phase = upcoming
            block.phase_started_at = today
            return block

        # Deload just completed -> roll over to a brand-new mesocycle. Same
        # dual reassessment-flag trigger as the old week4->new-block edge:
        # a mesocycle boundary is where a retest is "honest" (not
        # exhausted, not stale).
        user = await self._session.get(User, block.user_id)
        user.suggested_reassessment = True
        user.suggested_onice_reassessment = True
        new_block_number = block.block_number + 1
        return await self._blocks.create(
            TrainingBlock(
                user_id=block.user_id,
                block_number=new_block_number,
                phase_started_at=today,
                is_macrocycle_deload=is_macrocycle_deload_block(new_block_number),
            )
        )
