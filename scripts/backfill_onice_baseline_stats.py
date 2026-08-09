"""One-off backfill: give every user who's completed onboarding
(User.has_assessment=True, set by either the real off-ice test or "start
from scratch" -- both go through AssessmentService._apply_assessment) a
baseline UserStat row for the two on-ice stats (on_ice_skating,
puck_handling) if they don't already have one.

Fixes users created before _apply_assessment started seeding these two
stats itself: without a UserStat row at all (not even zero), the
frontend's per-stat tiles for on_ice_skating/puck_handling silently have
nothing to render for them.

Idempotent and safe to re-run: uses the same insert-only-if-missing path
as _apply_assessment (ProgressRepository.ensure_stat_exists), so a user
who's already taken the real on-ice test keeps their actual result --
this never overwrites an existing row, and running it twice never
produces duplicates.

    poetry run python scripts/backfill_onice_baseline_stats.py
"""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import TargetStat  # noqa: E402
from app.models.user import User  # noqa: E402
from app.repositories.progress_repository import ProgressRepository  # noqa: E402
from app.services.assessment_service import (  # noqa: E402
    REASON_ONICE_BASELINE_DEFAULT,
    SCRATCH_STARTING_VALUE,
)

ONICE_STAT_TYPES = (TargetStat.ON_ICE_SKATING, TargetStat.PUCK_HANDLING)


async def backfill_onice_baseline_stats(session: AsyncSession) -> int:
    """Returns the number of UserStat rows actually inserted (0 on a
    already-fixed dataset, or on a repeat run)."""
    progress = ProgressRepository(session)
    now = datetime.now(timezone.utc)

    user_ids = (
        (await session.execute(select(User.id).where(User.has_assessment.is_(True))))
        .scalars()
        .all()
    )

    inserted_count = 0
    for user_id in user_ids:
        for stat_type in ONICE_STAT_TYPES:
            inserted = await progress.ensure_stat_exists(
                user_id, stat_type, SCRATCH_STARTING_VALUE, now, REASON_ONICE_BASELINE_DEFAULT
            )
            if inserted:
                inserted_count += 1

    return inserted_count


async def main() -> None:
    async with AsyncSessionLocal() as session:
        inserted_count = await backfill_onice_baseline_stats(session)
        await session.commit()
        print(f"Inserted {inserted_count} baseline on-ice UserStat row(s).")


if __name__ == "__main__":
    asyncio.run(main())
