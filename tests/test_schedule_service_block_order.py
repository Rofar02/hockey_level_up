"""Regression: TrainingSession.blocks' `order` column must be unique
(and warmup < main < cooldown) within a single session.

_build_training_session used to reset `order` back to 0 for each phase
(warmup=0, main=0..n-1, cooldown=0) -- fine as long as every consumer
re-groups blocks by phase before using them (which they all happen to,
see TrainingSessionPage's `orderedBlocks` comment), but wrong on its own
terms: TrainingSession.blocks' relationship is `order_by="SessionBlock.order"`,
a single global sort with no phase tiebreak, so warmup/main[0]/cooldown
tying at order=0 left its actual sequence up to whatever the DB happened
to return for equal keys -- not guaranteed to be warmup-then-main-then-
cooldown. Fixed by making `order` run across the whole session instead of
resetting per phase.
"""
import random
import uuid

import pytest

from app.core.training_block import BlockPhase
from app.models.exercise import (
    EquipmentType,
    Exercise,
    ExerciseCategory,
    ExerciseTargetStat,
    TargetStat,
    TrainingPhase,
)
from app.models.schedule import DaySessionType
from app.models.user import User
from app.services.schedule_service import ScheduleService


@pytest.fixture(autouse=True)
def deterministic_random(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(random, "randint", lambda a, b: 2)
    monkeypatch.setattr(random, "choice", lambda pool: sorted(pool, key=lambda e: e.name)[0])


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"block_order_{unique}",
        email=f"block_order_{unique}@example.com",
        password_hash="irrelevant",
        equipment_access=EquipmentType.BODYWEIGHT,
        level=15,
    )


def _make_exercise(*, name: str, phase: TrainingPhase) -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=name,
        category=ExerciseCategory.OFF_ICE,
        phase=phase,
        difficulty_level=1,
        equipment_type=EquipmentType.BODYWEIGHT,
    )


@pytest.mark.asyncio
async def test_block_order_is_unique_and_matches_warmup_main_cooldown_sequence(db_session) -> None:
    user = _make_user()
    db_session.add(user)

    warmup = _make_exercise(name="warmup", phase=TrainingPhase.WARMUP)
    main_strength = _make_exercise(name="main strength", phase=TrainingPhase.MAIN)
    main_agility = _make_exercise(name="main agility", phase=TrainingPhase.MAIN)
    cooldown = _make_exercise(name="cooldown", phase=TrainingPhase.COOLDOWN)

    exercises = {
        "warmup": warmup,
        "main_strength": main_strength,
        "main_agility": main_agility,
        "cooldown": cooldown,
    }
    db_session.add_all(exercises.values())
    db_session.add_all(
        [
            ExerciseTargetStat(exercise_id=main_strength.id, target_stat=TargetStat.STRENGTH, order=0),
            ExerciseTargetStat(exercise_id=main_agility.id, target_stat=TargetStat.AGILITY, order=0),
        ]
    )
    await db_session.flush()

    async def fake_list_for_assembly(
        *, phase, equipment_access, category=None, suitable_for_game_day=None
    ):
        pool = [e for e in exercises.values() if e.phase == phase]
        if category is not None:
            pool = [e for e in pool if e.category == category]
        return pool

    service = ScheduleService(db_session)
    service._exercises.list_for_assembly = fake_list_for_assembly

    session = await service._build_training_session(
        session_type=DaySessionType.OFF_ICE, user=user, block_phase=BlockPhase.ACCUMULATION
    )

    orders = [block.order for block in session.blocks]
    assert len(orders) == len(set(orders)), f"duplicate order values: {orders}"

    by_order = sorted(session.blocks, key=lambda b: b.order)
    assert [b.phase for b in by_order] == [
        TrainingPhase.WARMUP,
        TrainingPhase.MAIN,
        TrainingPhase.MAIN,
        TrainingPhase.COOLDOWN,
    ]
