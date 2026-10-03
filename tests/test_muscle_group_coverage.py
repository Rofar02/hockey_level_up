"""Guards for adding a MuscleGroup (2026-10-03: adductors, hip_flexors).

Two hand-written maps list the groups one by one, and the muscle_group
columns are fixed-width VARCHARs. Neither fails loudly on a new group by
itself (the analytics lookup is a .get(), the coach labels fall back to the
raw code, and a too-long value only fails on the first INSERT), so these tests
make forgetting one a red build instead of a silent gap on prod.
"""
import uuid

import pytest
from sqlalchemy import inspect, select

from app.models.exercise import (
    Exercise,
    ExerciseCategory,
    ExerciseMuscleGroup,
    MuscleGroup,
    TrainingPhase,
)
from app.services.analytics_overview_service import (
    DISPLAY_GROUP_ORDER,
    MUSCLE_DISPLAY_GROUP,
)
from app.services.coach_chat_service import MUSCLE_GROUP_LABELS


def test_every_muscle_group_has_an_analytics_display_group() -> None:
    missing = [g for g in MuscleGroup if g not in MUSCLE_DISPLAY_GROUP]
    assert missing == [], f"load of these groups would silently vanish from analytics: {missing}"
    assert set(MUSCLE_DISPLAY_GROUP.values()) <= set(DISPLAY_GROUP_ORDER)


def test_every_muscle_group_has_a_coach_label() -> None:
    missing = [g for g in MuscleGroup if g not in MUSCLE_GROUP_LABELS]
    assert missing == [], f"the coach would name these groups by their raw code: {missing}"


@pytest.mark.asyncio
async def test_muscle_group_columns_fit_every_group_value(db_session) -> None:
    connection = await db_session.connection()

    def _lengths(sync_connection) -> dict[str, int | None]:
        insp = inspect(sync_connection)
        out = {}
        for table in ("exercise_muscle_groups", "user_muscle_loads", "user_temporary_restrictions"):
            col = next(c for c in insp.get_columns(table) if c["name"] == "muscle_group")
            out[table] = col["type"].length
        return out

    lengths = await connection.run_sync(_lengths)
    longest = max(len(g.value) for g in MuscleGroup)
    for table, length in lengths.items():
        assert length is not None and length >= longest, f"{table}.muscle_group is VARCHAR({length}), needs {longest}+"


@pytest.mark.asyncio
async def test_new_groups_can_be_stored(db_session) -> None:
    exercise = Exercise(
        id=uuid.uuid4(),
        name=f"Exercise {uuid.uuid4().hex[:8]}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
    )
    db_session.add(exercise)
    await db_session.flush()
    db_session.add(ExerciseMuscleGroup(exercise_id=exercise.id, muscle_group=MuscleGroup.ADDUCTORS, weight=0.5))
    db_session.add(ExerciseMuscleGroup(exercise_id=exercise.id, muscle_group=MuscleGroup.HIP_FLEXORS, weight=0.5))
    await db_session.flush()

    rows = await db_session.execute(
        select(ExerciseMuscleGroup.muscle_group).where(ExerciseMuscleGroup.exercise_id == exercise.id)
    )
    assert {r[0] for r in rows.all()} == {MuscleGroup.ADDUCTORS, MuscleGroup.HIP_FLEXORS}
