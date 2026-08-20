"""Stage 1 groundwork (2026-08-20 planning session): measure the ACTUAL median
off-ice MAIN block duration against the real catalog and real ScheduleService
assembly, instead of guessing. estimate_block_duration_seconds already
accounts for stimulus_type-based rest between sets (see app/core/session_duration.py)
so this is a real number, not a rough one.

Calls ScheduleService._pick_main directly for a fresh GYM-equipped level-1
user, many times per BlockPhase (patterns are shuffled inside _pick_main, so
repeated calls sample the real distribution), and reports the duration
distribution against the 60-90 minute whole-session target.

Run against a TEST environment only:

    docker compose exec backend poetry run python scripts/measure_main_block_duration.py
"""
import asyncio
import statistics
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.session_duration import estimate_block_duration_seconds  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import EquipmentType, ExerciseCategory  # noqa: E402
from app.models.schedule import BlockPhase  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.schedule_service import ScheduleService  # noqa: E402

SAMPLES_PER_PHASE = 40


async def make_probe_user(session) -> User:
    unique = uuid.uuid4().hex[:8]
    user = User(
        id=uuid.uuid4(),
        username=f"probe_{unique}",
        email=f"probe_{unique}@example.com",
        password_hash="irrelevant",
        last_name="Probe",
        first_name="Duration",
        equipment_access=EquipmentType.GYM,
        weight=75.0,
        height=180.0,
        age=20,
        level=1,
        xp=0,
    )
    session.add(user)
    await session.flush()
    return user


async def main() -> None:
    async with AsyncSessionLocal() as session:
        user = await make_probe_user(session)
        schedule_service = ScheduleService(session)

        print(f"{'phase':<16} {'n':>3} {'min':>6} {'median':>7} {'mean':>6} {'max':>6}  (seconds, MAIN block only)")
        for phase in BlockPhase:
            durations = []
            for _ in range(SAMPLES_PER_PHASE):
                exercises = await schedule_service._pick_main(
                    ExerciseCategory.OFF_ICE, user, phase
                )
                total = sum(estimate_block_duration_seconds(ex) for ex in exercises)
                durations.append(total)

            durations.sort()
            print(
                f"{phase.value:<16} {len(durations):>3} "
                f"{min(durations):>6} {round(statistics.median(durations)):>7} "
                f"{round(statistics.mean(durations)):>6} {max(durations):>6}"
            )
            print(f"{'':<16}  -> {min(durations)/60:.1f}-{max(durations)/60:.1f} min, median {statistics.median(durations)/60:.1f} min")

        await session.rollback()  # probe user is throwaway, never commit


if __name__ == "__main__":
    asyncio.run(main())
