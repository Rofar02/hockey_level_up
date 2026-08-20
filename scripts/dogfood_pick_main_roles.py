"""Stage 2.4 dogfooding sanity check (2026-08-20 planning session, run
before moving on to Stage 2.5 per the plan's own instruction): assembles
several real MAIN sessions against the real seeded catalog for a level-15
GYM-equipped probe user, across all three BlockPhase values, and prints
the actual picks with their movement_pattern/stimulus_type/is_unilateral
so the role order and archetype behavior can be eyeballed against a real
catalog, not just isolated unit-test fixtures.

Run against a TEST environment only:

    docker compose exec backend poetry run python scripts/dogfood_pick_main_roles.py
"""
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import EquipmentItem, ExerciseCategory  # noqa: E402
from app.models.schedule import BlockPhase, TrainingBlock  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.schedule_service import ScheduleService  # noqa: E402


async def make_probe_user(session) -> User:
    unique = uuid.uuid4().hex[:8]
    user = User(
        id=uuid.uuid4(),
        username=f"dogfood_{unique}",
        email=f"dogfood_{unique}@example.com",
        password_hash="irrelevant",
        last_name="Dogfood",
        first_name="Roles",
        has_gym_access=True,
        weight=80.0,
        height=185.0,
        age=25,
        level=15,
        xp=0,
    )
    session.add(user)
    await session.flush()
    return user


async def main() -> None:
    async with AsyncSessionLocal() as session:
        user = await make_probe_user(session)
        schedule_service = ScheduleService(session)

        # One continuous journey (accumulation -> intensification -> deload,
        # increasing block_number) rather than isolated snapshots --
        # UserMovementPatternVariant rotation state is per-user, not
        # per-block, so this is the realistic way to see it evolve, same
        # as a real user progressing through one mesocycle would.
        for block_number, phase in enumerate(BlockPhase, start=1):
            print(f"\n=== block {block_number}: {phase.value} ===")
            block = TrainingBlock(user_id=user.id, block_number=block_number, phase=phase)
            session.add(block)
            await session.flush()

            for session_num in range(1, 4):
                exercises = await schedule_service._pick_main(
                    ExerciseCategory.OFF_ICE, user, phase, training_block=block
                )
                print(f"-- session {session_num} ({len(exercises)} exercises) --")
                for exercise in exercises:
                    patterns = await schedule_service._exercises.list_movement_patterns(exercise.id)
                    print(
                        f"  {exercise.name!r:50} patterns={[p.value for p in patterns]} "
                        f"stimulus={exercise.stimulus_type} unilateral={exercise.is_unilateral}"
                    )

        await session.rollback()  # probe user + everything it touched is throwaway


if __name__ == "__main__":
    asyncio.run(main())
