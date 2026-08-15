import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.overload import (
    STRUCTURAL_REPLAY_LOOKBACK,
    TACTICAL_BRAKE_WINDOW,
    SessionSignal,
    classify_session,
    compute_difficulty_throttle_steps,
    tactical_brake_engaged,
)
from app.models.schedule import BlockPhase
from app.models.user import User
from app.repositories.overload_repository import OverloadRepository


class OverloadService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._overload = OverloadRepository(session)

    async def apply_brakes(self, user: User, block_phase: BlockPhase) -> BlockPhase:
        """Refreshes user.difficulty_throttle_steps in place (structural
        brake -- read later by ScheduleService._apply_level_cap) and
        returns the EFFECTIVE block_phase for exercise assembly: forced to
        DELOAD if the tactical brake is currently engaged, otherwise
        `block_phase` unchanged.

        Both brakes are derived fresh from the user's session-signal
        history on every call (see app.core.overload) rather than
        incrementally event-driven state -- SetCompletion.feedback can be
        logged well after a session's blocks all complete (see
        SetCompletionService.save_feedback), so there's no single reliable
        "session just finished" trigger point to update incremental state
        exactly once. Recomputing fresh is idempotent and safe to call on
        every assembly, the same shape as
        TrainingBlockService.resolve_active_block.

        Deliberately does NOT touch the TrainingBlock's own persisted
        phase/session-count progression (Phase 4) -- the tactical brake is
        a pure assembly-time override, so "recovery" is just "the override
        stops applying next time", not something that needs to remember
        whether a deload was forced vs organically reached.
        """
        recent_counts = await self._overload.list_recent_session_feedback_counts(
            user.id, limit=max(TACTICAL_BRAKE_WINDOW, STRUCTURAL_REPLAY_LOOKBACK)
        )
        signals_newest_first = [
            signal
            for signal in (classify_session(hard_count=h, max_count=m, total_with_feedback=t) for h, m, t in recent_counts)
            if signal is not None
        ]

        user.difficulty_throttle_steps = compute_difficulty_throttle_steps(list(reversed(signals_newest_first)))

        if tactical_brake_engaged(signals_newest_first):
            return BlockPhase.DELOAD
        return block_phase
