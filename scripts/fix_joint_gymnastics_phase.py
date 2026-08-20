"""One-row data fix: "Комплекс суставной гимнастики" was tagged
phase='main' (and consequently warmup_stage=NULL, since that field is only
ever set on WARMUP rows) -- a real, user-reported bug, not a hypothetical:
it kept showing up as MAIN accessory content in real assembled sessions.

Confirmed via the real DB against its two near-identical siblings, both
correctly phase='warmup'/warmup_stage='joint_mobility' with the same
movement_patterns, exercise_type='duration', target_duration_seconds=180,
and target_stats=agility -- this row is unmistakably the same kind of
content, just mistagged. Checked the rest of the catalog for the same
mistake (phase='main' + a warmup/mobility-sounding name) -- nothing else
turned up; this is an isolated row, not a systemic tagging problem.

_pick_main's role 4 (accessories) has no filter against warmup-only
movement_patterns (HIP_MOBILITY/SHOULDER_MOBILITY/ANKLE_MOBILITY/
WRIST_MOBILITY) beyond phase itself -- see ScheduleService.list_for_assembly,
which filters candidates to phase=MAIN. A correctly-tagged phase='warmup'
row is invisible to that query regardless of its movement_pattern, which is
why the two correctly-tagged siblings never showed up as MAIN content and
this one did.

Not a migration -- run manually:

    poetry run python scripts/fix_joint_gymnastics_phase.py

Idempotent: no-ops if the row is already phase='warmup'.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import Exercise, TrainingPhase, WarmupStage  # noqa: E402

TARGET_NAME = "Комплекс суставной гимнастики"


async def fix() -> None:
    async with AsyncSessionLocal() as session:
        exercise = (
            await session.execute(select(Exercise).where(Exercise.name == TARGET_NAME))
        ).scalar_one_or_none()
        if exercise is None:
            print(f"WARNING: {TARGET_NAME!r} not found in DB, nothing to do.")
            return
        if exercise.phase == TrainingPhase.WARMUP:
            print(f"{TARGET_NAME!r} already phase=warmup, no-op.")
            return
        exercise.phase = TrainingPhase.WARMUP
        exercise.warmup_stage = WarmupStage.JOINT_MOBILITY
        await session.commit()
        print(f"Fixed {TARGET_NAME!r}: phase -> warmup, warmup_stage -> joint_mobility.")


if __name__ == "__main__":
    asyncio.run(fix())
