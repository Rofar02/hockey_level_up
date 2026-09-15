"""Catalog health check: for every archetype-eligible movement pattern
(squat/hip_hinge/push/pull) x stimulus_type (strength/power/skill) x a set
of representative equipment profiles, reports whether at least one
off-ice MAIN exercise is actually reachable.

A "0 reachable" cell is exactly the shape of bug fixed 2026-09-16 in
ScheduleService.pick_for_pattern: the archetype rotation can never find a
genuine match there, so it either freezes on a fallback for a whole
training block (pre-fix) or keeps re-rolling a fallback every session
(post-fix) -- neither is as good as having a real match. This script is
meant to be run whenever the catalog changes, to catch a new gap before a
real user does.

Usage:
    docker compose exec backend python scripts/audit_archetype_coverage.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import (  # noqa: E402
    Exercise,
    ExerciseCategory,
    ExerciseEquipmentItem,
    ExerciseMovementPattern,
    GYM_COVERED_ITEMS,
    MovementPattern,
    StimulusType,
    TrainingPhase,
)

ARCHETYPE_PATTERNS = [
    MovementPattern.SQUAT,
    MovementPattern.HIP_HINGE,
    MovementPattern.PUSH,
    MovementPattern.PULL,
]
ARCHETYPES = [StimulusType.STRENGTH, StimulusType.POWER, StimulusType.SKILL]

# Representative equipment profiles to check against -- not exhaustive of
# every real user, but the common shapes: a fully-equipped gym, a
# home-gym with the most common items, and pure bodyweight.
PROFILES: dict[str, tuple[bool, frozenset]] = {
    "full_gym": (True, frozenset()),
    "home_band_dumbbells": (False, frozenset({"resistance_band", "dumbbells", "jump_rope"})),
    "home_kettlebell_only": (False, frozenset({"kettlebell"})),
    "bodyweight_only": (False, frozenset()),
}


async def main() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Exercise).where(
                Exercise.phase == TrainingPhase.MAIN,
                Exercise.category == ExerciseCategory.OFF_ICE,
            )
        )
        exercises = result.scalars().all()
        ex_ids = [e.id for e in exercises]

        patterns_by_ex: dict = {}
        result = await session.execute(
            select(ExerciseMovementPattern).where(ExerciseMovementPattern.exercise_id.in_(ex_ids))
        )
        for row in result.scalars().all():
            patterns_by_ex.setdefault(row.exercise_id, set()).add(row.movement_pattern)

        equip_by_ex: dict = {}
        result = await session.execute(
            select(ExerciseEquipmentItem).where(ExerciseEquipmentItem.exercise_id.in_(ex_ids))
        )
        for row in result.scalars().all():
            equip_by_ex.setdefault(row.exercise_id, set()).add(row.equipment_item.value)

        gaps_found = False
        for profile_name, (has_gym_access, owned) in PROFILES.items():
            print(f"\n===== profile: {profile_name} =====")
            for pattern in ARCHETYPE_PATTERNS:
                for archetype in ARCHETYPES:
                    candidates = []
                    for e in exercises:
                        if pattern not in patterns_by_ex.get(e.id, set()):
                            continue
                        if e.stimulus_type != archetype.value:
                            continue
                        required = equip_by_ex.get(e.id, set())
                        reachable = all(
                            (has_gym_access and item in GYM_COVERED_ITEMS) or item in owned
                            for item in required
                        )
                        if reachable:
                            candidates.append(e.name)
                    marker = "OK" if candidates else "!! GAP !!"
                    if not candidates:
                        gaps_found = True
                    print(f"  {pattern.value:12s} {archetype.value:9s} {marker:10s} ({len(candidates)} reachable)")

        print("\n" + ("SOME GAPS FOUND -- see !! GAP !! rows above" if gaps_found else "No gaps found across all profiles."))


if __name__ == "__main__":
    asyncio.run(main())
