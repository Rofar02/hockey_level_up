"""Stage 2.4 (2026-08-20 planning session): day-archetype rotation as
exercised end-to-end through ScheduleService._pick_main, not just the pure
app.core.day_archetype functions (see test_day_archetype.py for those in
isolation). Covers the parts test_pick_main_variant_stability.py's SQUAT
fixtures never touch, because none of them set stimulus_type -- every call
there degenerately resolves to the STRENGTH default and stays there.

Verifies:
  1. An archetype with no rotation history at all outranks any archetype
     with a real (even very recent) last_chosen_at date.
  2. day_archetype.forces_technical_archetype overrides rotation outright
     during a deload-equivalent session.
  3. A fallback pick (the resolved archetype's own stimulus_type pool was
     empty) must NOT be recorded as having satisfied that archetype --
     last_chosen_at stays untouched, even though a pin row still gets
     created/updated for that archetype slot.
  4. PUSH/PULL now get the same three-way split as SQUAT/HIP_HINGE
     (2026-09-20 fix, round-4 audit).
  5. A thin, single-candidate pool logs a warning when it silently
     collapses every archetype onto the same fallback exercise
     (2026-09-20 fix, round-4 audit).
"""
import logging
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.exercise import (
    Exercise,
    ExerciseCategory,
    ExerciseMovementPattern,
    MovementPattern,
    StimulusType,
    TrainingPhase,
    UserMovementPatternVariant,
)
from app.models.schedule import BlockPhase, TrainingBlock
from app.models.user import User
from app.services.schedule_service import ScheduleService

TODAY = date(2026, 8, 20)


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"archetype_{unique}",
        email=f"archetype_{unique}@example.com",
        password_hash="irrelevant",
        level=15,
    )
    defaults.update(overrides)
    return User(**defaults)


def _make_block(user: User, *, block_number: int = 1) -> TrainingBlock:
    return TrainingBlock(user_id=user.id, block_number=block_number, phase=BlockPhase.ACCUMULATION)


def _make_squat_exercise(name: str, stimulus_type: StimulusType) -> tuple[Exercise, ExerciseMovementPattern]:
    exercise = Exercise(
        id=uuid.uuid4(),
        name=name,
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
        stimulus_type=stimulus_type,
    )
    return exercise, ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=MovementPattern.SQUAT)


def _make_push_exercise(name: str, stimulus_type: StimulusType) -> tuple[Exercise, ExerciseMovementPattern]:
    exercise = Exercise(
        id=uuid.uuid4(),
        name=name,
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
        stimulus_type=stimulus_type,
    )
    return exercise, ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=MovementPattern.PUSH)


def _isolate_candidates(service: ScheduleService, exercises: list[Exercise]) -> None:
    async def fake_list_for_assembly(*, phase, user, category, suitable_for_game_day=None):
        return [e for e in exercises if e.phase == phase and e.category == category]

    service._exercises.list_for_assembly = fake_list_for_assembly


async def _get_pin(db_session, user: User, archetype: StimulusType) -> UserMovementPatternVariant:
    result = await db_session.execute(
        select(UserMovementPatternVariant).where(
            UserMovementPatternVariant.user_id == user.id,
            UserMovementPatternVariant.category == ExerciseCategory.OFF_ICE,
            UserMovementPatternVariant.movement_pattern == MovementPattern.SQUAT,
            UserMovementPatternVariant.archetype == archetype,
        )
    )
    return result.scalar_one()


@pytest.mark.asyncio
async def test_never_tried_archetype_wins_over_a_recently_dated_one(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    strength_ex, strength_pattern = _make_squat_exercise("Strength-squat", StimulusType.STRENGTH)
    power_ex, power_pattern = _make_squat_exercise("Power-squat", StimulusType.POWER)
    skill_ex, skill_pattern = _make_squat_exercise("Skill-squat", StimulusType.SKILL)
    db_session.add_all([strength_ex, power_ex, skill_ex, strength_pattern, power_pattern, skill_pattern])
    block = _make_block(user)
    db_session.add(block)
    await db_session.flush()

    # STRENGTH and POWER both have real (recent) history; SKILL has none at
    # all -- SKILL must win regardless of how recent the dated ones are.
    db_session.add_all([
        UserMovementPatternVariant(
            user_id=user.id, category=ExerciseCategory.OFF_ICE, movement_pattern=MovementPattern.SQUAT,
            archetype=StimulusType.STRENGTH, exercise_id=strength_ex.id, block_number=1,
            last_chosen_at=TODAY - timedelta(days=1),
        ),
        UserMovementPatternVariant(
            user_id=user.id, category=ExerciseCategory.OFF_ICE, movement_pattern=MovementPattern.SQUAT,
            archetype=StimulusType.POWER, exercise_id=power_ex.id, block_number=1,
            last_chosen_at=TODAY - timedelta(days=2),
        ),
    ])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [strength_ex, power_ex, skill_ex])
    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block, today=TODAY
    )

    assert [e.name for e in picked] == ["Skill-squat"]
    pin = await _get_pin(db_session, user, StimulusType.SKILL)
    assert pin.exercise_id == skill_ex.id
    assert pin.last_chosen_at == TODAY  # genuine match -> stamped


@pytest.mark.asyncio
async def test_override_forces_skill_during_a_deload_equivalent_session(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    strength_ex, strength_pattern = _make_squat_exercise("Strength-squat", StimulusType.STRENGTH)
    skill_ex, skill_pattern = _make_squat_exercise("Skill-squat", StimulusType.SKILL)
    db_session.add_all([strength_ex, skill_ex, strength_pattern, skill_pattern])
    block = _make_block(user)
    db_session.add(block)
    await db_session.flush()

    # STRENGTH has no history (would normally win outright as the never-
    # tried default) -- the deload override must still force SKILL.
    service = ScheduleService(db_session)
    _isolate_candidates(service, [strength_ex, skill_ex])
    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.DELOAD, training_block=block, today=TODAY
    )

    assert [e.name for e in picked] == ["Skill-squat"]


@pytest.mark.asyncio
async def test_fallback_pick_does_not_falsely_mark_the_archetype_done(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    # Only a STRENGTH-tagged candidate exists -- no POWER exercise at all.
    strength_ex, strength_pattern = _make_squat_exercise("Strength-squat", StimulusType.STRENGTH)
    db_session.add_all([strength_ex, strength_pattern])
    block = _make_block(user)
    db_session.add(block)
    await db_session.flush()

    # POWER is the oldest (30 days) vs STRENGTH's 1 day -- rotation resolves
    # to POWER, but there's nothing POWER-tagged to actually pick.
    db_session.add_all([
        UserMovementPatternVariant(
            user_id=user.id, category=ExerciseCategory.OFF_ICE, movement_pattern=MovementPattern.SQUAT,
            archetype=StimulusType.STRENGTH, exercise_id=strength_ex.id, block_number=1,
            last_chosen_at=TODAY - timedelta(days=1),
        ),
        UserMovementPatternVariant(
            user_id=user.id, category=ExerciseCategory.OFF_ICE, movement_pattern=MovementPattern.SQUAT,
            archetype=StimulusType.POWER, exercise_id=strength_ex.id, block_number=1,
            last_chosen_at=TODAY - timedelta(days=30),
        ),
    ])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [strength_ex])
    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block, today=TODAY
    )

    # Fell back to the only real candidate -- still fills the slot.
    assert [e.name for e in picked] == ["Strength-squat"]
    # But POWER's pin/last_chosen_at must be untouched -- the pick was a
    # fallback (Strength-squat's own stimulus_type is STRENGTH, not POWER),
    # not a genuine POWER instance, so it must not be marked done.
    power_pin = await _get_pin(db_session, user, StimulusType.POWER)
    assert power_pin.last_chosen_at == TODAY - timedelta(days=30)


@pytest.mark.asyncio
async def test_override_forces_skill_during_a_deload_equivalent_session_for_push(
    db_session,
) -> None:
    """2026-09-20 fix (round-4 audit): PUSH/PULL used to be excluded from
    SKILL entirely (PATTERN_ARCHETYPES), so forces_technical's SKILL
    override silently fell through to an unfiltered pick for these two
    patterns -- the "lighter, technical" deload/taper/playoffs intent
    quietly never applied to them. Mirrors
    test_override_forces_skill_during_a_deload_equivalent_session above,
    but for PUSH, now that it has real SKILL content."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    strength_ex, strength_pattern = _make_push_exercise("Strength-push", StimulusType.STRENGTH)
    skill_ex, skill_pattern = _make_push_exercise("Skill-push", StimulusType.SKILL)
    db_session.add_all([strength_ex, skill_ex, strength_pattern, skill_pattern])
    block = _make_block(user)
    db_session.add(block)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [strength_ex, skill_ex])
    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.DELOAD, training_block=block, today=TODAY
    )

    assert [e.name for e in picked] == ["Skill-push"]


@pytest.mark.asyncio
async def test_forces_technical_does_not_force_an_archetype_the_pattern_lacks(
    db_session, monkeypatch
) -> None:
    """Defensive branch for the fix above: if a pattern's own
    PATTERN_ARCHETYPES entry ever lacks SKILL again (e.g. a future
    catalog regression), forces_technical must not force an archetype
    that pattern doesn't support -- it should fall through to the normal,
    read-only archetype resolution instead of forcing an empty
    stimulus_preference search."""
    from app.services import schedule_service as schedule_service_module

    monkeypatch.setitem(
        schedule_service_module.PATTERN_ARCHETYPES,
        MovementPattern.PUSH,
        (StimulusType.STRENGTH, StimulusType.POWER),
    )

    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    strength_ex, strength_pattern = _make_push_exercise("Strength-push", StimulusType.STRENGTH)
    db_session.add_all([strength_ex, strength_pattern])
    block = _make_block(user)
    db_session.add(block)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [strength_ex])
    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.DELOAD, training_block=block, today=TODAY
    )

    # No SKILL candidate exists and PATTERN_ARCHETYPES[PUSH] no longer
    # offers it -- falls through to the only real (STRENGTH) content
    # instead of an empty, forced SKILL search.
    assert [e.name for e in picked] == ["Strength-push"]


@pytest.mark.asyncio
async def test_thin_pool_collapse_to_a_single_exercise_logs_a_warning(
    db_session, caplog
) -> None:
    """2026-09-20 fix (round-4 audit): when a pattern's post-filter pool
    has only one real candidate, all three day archetypes silently
    collapse onto it -- the slot still gets filled (same best-effort
    softness as every other layer), but it's now logged so a thin catalog
    spot is visible instead of invisibly masquerading as real variety."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    only_ex, only_pattern = _make_squat_exercise("Only squat available", StimulusType.STRENGTH)
    db_session.add_all([only_ex, only_pattern])
    block = _make_block(user)
    db_session.add(block)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [only_ex])

    with caplog.at_level(logging.WARNING, logger="app.services.schedule_service"):
        picked = await service._pick_main(
            ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block, today=TODAY
        )

    assert [e.name for e in picked] == ["Only squat available"]
    # First-ever pick resolves to STRENGTH (DEFAULT_FIRST_ARCHETYPE) --
    # genuine, no warning for that one. Nothing else fired this call
    # (POWER/SKILL are only tried once STRENGTH's own pin is reused/
    # rotated on a later call), so no fallback warning is expected here
    # either -- this call alone just establishes the pin.
    assert not any("Day-archetype fallback" in record.message for record in caplog.records)

    # A second call, forcing rotation past STRENGTH (bump times_chosen to
    # the rotation limit) -- resolves to POWER or SKILL next, neither of
    # which this thin pool can genuinely satisfy.
    pin = await _get_pin(db_session, user, StimulusType.STRENGTH)
    pin.times_chosen = 999
    await db_session.flush()

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="app.services.schedule_service"):
        picked_again = await service._pick_main(
            ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, training_block=block, today=TODAY
        )

    assert [e.name for e in picked_again] == ["Only squat available"]
    assert any("Day-archetype fallback" in record.message for record in caplog.records)
