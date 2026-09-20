"""2026-09-19 audit round 3 item #2 --
ScheduleService.patch_week_for_eligibility_change, the shared patcher
UserTemporaryRestrictionService.report/lift and
UserService.replace_owned_equipment now both call. Before this, a
restriction reported (or lifted) or equipment added/removed mid-week only
ever affected *future* day/week assembly -- an already-generated,
not-yet-started day in the current week kept showing exercises that no
longer belong there for the rest of the week. Same
"untouched-future-day-only" scoping as
test_ceiling_escalation_week_patch.py, deliberately isolated from the
service-level wiring (covered instead by
test_user_temporary_restriction_service.py's own commit-boundary tests)
-- this file is about the patch mechanics themselves.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.exercise import (
    EquipmentItem,
    Exercise,
    ExerciseCategory,
    ExerciseMovementPattern,
    MovementPattern,
    TrainingPhase,
    UserEquipmentItem,
    UserMovementPatternVariant,
)
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.user import User
from app.services.schedule_service import ScheduleService

TODAY = date(2026, 9, 19)


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"weekpatch_{unique}",
        email=f"weekpatch_{unique}@example.com",
        password_hash="irrelevant",
        level=15,
    )


def _make_exercise(
    name: str, *, phase: TrainingPhase = TrainingPhase.MAIN, category: ExerciseCategory = ExerciseCategory.OFF_ICE
) -> Exercise:
    return Exercise(id=uuid.uuid4(), name=name, category=category, phase=phase, difficulty_level=1)


def _isolate_candidates(service: ScheduleService, exercises: list[Exercise]) -> None:
    async def fake_list_for_assembly(*, phase, user, category=None, suitable_for_game_day=None):
        pool = [e for e in exercises if e.phase == phase]
        if category is not None:
            pool = [e for e in pool if e.category == category]
        return pool

    service._exercises.list_for_assembly = fake_list_for_assembly


def _untouched_off_ice_day(offset_days: int, block: SessionBlock) -> DayPlan:
    return DayPlan(
        id=uuid.uuid4(),
        date=TODAY + timedelta(days=offset_days),
        session_type=DaySessionType.OFF_ICE,
        training_session=TrainingSession(id=uuid.uuid4(), blocks=[block]),
    )


@pytest.mark.asyncio
async def test_patches_ineligible_blocks_in_untouched_future_days_and_moves_the_pin(db_session) -> None:
    now_ineligible = _make_exercise("Bench press")
    eligible_substitute = _make_exercise("Cable press")
    warmup_now_ineligible = _make_exercise("Shoulder stretch", phase=TrainingPhase.WARMUP)
    warmup_substitute = _make_exercise("Arm circles", phase=TrainingPhase.WARMUP)
    exercises = [now_ineligible, eligible_substitute, warmup_now_ineligible, warmup_substitute]

    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    pattern_rows = [
        ExerciseMovementPattern(exercise_id=now_ineligible.id, movement_pattern=MovementPattern.PUSH),
        ExerciseMovementPattern(exercise_id=eligible_substitute.id, movement_pattern=MovementPattern.PUSH),
    ]
    pin = UserMovementPatternVariant(
        user_id=user.id,
        category=ExerciseCategory.OFF_ICE,
        movement_pattern=MovementPattern.PUSH,
        archetype=None,
        exercise_id=now_ineligible.id,
        block_number=1,
    )
    db_session.add_all([*exercises, *pattern_rows, pin])
    await db_session.flush()

    main_block = SessionBlock(
        id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=now_ineligible.id, order=0
    )
    warmup_block = SessionBlock(
        id=uuid.uuid4(), phase=TrainingPhase.WARMUP, exercise_id=warmup_now_ineligible.id, order=1
    )
    tomorrow_plan = _untouched_off_ice_day(1, main_block)
    tomorrow_plan.training_session.blocks.append(warmup_block)

    weekly_plan = WeeklyPlan(
        id=uuid.uuid4(), user_id=user.id, week_start_date=TODAY, day_plans=[tomorrow_plan]
    )
    db_session.add(weekly_plan)
    await db_session.flush()

    service = ScheduleService(db_session)
    # This test's own fixtures only ever include the *currently* eligible
    # pool -- the outgoing exercises are deliberately absent from it,
    # standing in for "a restriction/missing-equipment change just made
    # this exercise ineligible", same isolation shape as
    # test_ceiling_escalation_week_patch.py's own fake.
    _isolate_candidates(service, [eligible_substitute, warmup_substitute])

    changed = await service.patch_week_for_eligibility_change(user, today=TODAY)

    assert changed == 2
    await db_session.refresh(main_block)
    await db_session.refresh(warmup_block)
    assert main_block.exercise_id == eligible_substitute.id
    assert warmup_block.exercise_id == warmup_substitute.id
    await db_session.refresh(pin)
    assert pin.exercise_id == eligible_substitute.id


@pytest.mark.asyncio
async def test_returns_zero_when_every_remaining_day_has_already_started(db_session) -> None:
    user = _make_user()
    now_ineligible = _make_exercise("Bench press")
    db_session.add_all([user, now_ineligible])
    await db_session.flush()

    started_block = SessionBlock(
        id=uuid.uuid4(),
        phase=TrainingPhase.MAIN,
        exercise_id=now_ineligible.id,
        order=0,
        completed_at=None,
        skipped_at=None,
    )
    tomorrow_plan = _untouched_off_ice_day(1, started_block)
    # A sibling block in the same session already completed -- the whole
    # day counts as begun, same "all-or-nothing" rule
    # _untouched_future_day_plans documents.
    tomorrow_plan.training_session.blocks.append(
        SessionBlock(
            id=uuid.uuid4(),
            phase=TrainingPhase.WARMUP,
            exercise_id=now_ineligible.id,
            order=1,
            completed_at=datetime.now(timezone.utc),
        )
    )
    weekly_plan = WeeklyPlan(
        id=uuid.uuid4(), user_id=user.id, week_start_date=TODAY, day_plans=[tomorrow_plan]
    )
    db_session.add(weekly_plan)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [])  # nothing eligible at all -- would patch if it looked

    changed = await service.patch_week_for_eligibility_change(user, today=TODAY)

    assert changed == 0
    await db_session.refresh(started_block)
    assert started_block.exercise_id == now_ineligible.id


@pytest.mark.asyncio
async def test_no_current_week_returns_zero(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    service = ScheduleService(db_session)
    changed = await service.patch_week_for_eligibility_change(user, today=TODAY)

    assert changed == 0


@pytest.mark.asyncio
async def test_adds_puck_module_to_untouched_off_ice_day_when_stick_now_owned(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    puck_exercise = _make_exercise("Puck drill", phase=TrainingPhase.PUCK)
    main_exercise = _make_exercise("Off-ice main")
    db_session.add_all([
        puck_exercise,
        main_exercise,
        UserEquipmentItem(user_id=user.id, equipment_item=EquipmentItem.HOCKEY_STICK),
    ])
    await db_session.flush()

    main_block = SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=main_exercise.id, order=0)
    tomorrow_plan = _untouched_off_ice_day(1, main_block)
    weekly_plan = WeeklyPlan(
        id=uuid.uuid4(), user_id=user.id, week_start_date=TODAY, day_plans=[tomorrow_plan]
    )
    db_session.add(weekly_plan)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [puck_exercise, main_exercise])

    changed = await service.patch_week_for_eligibility_change(user, today=TODAY)

    assert changed == 1
    puck_blocks = [b for b in tomorrow_plan.training_session.blocks if b.phase == TrainingPhase.PUCK]
    assert [b.exercise_id for b in puck_blocks] == [puck_exercise.id]


@pytest.mark.asyncio
async def test_removes_puck_block_when_stick_no_longer_owned(db_session) -> None:
    user = _make_user()
    puck_exercise = _make_exercise("Puck drill", phase=TrainingPhase.PUCK)
    db_session.add_all([user, puck_exercise])
    await db_session.flush()
    # No UserEquipmentItem -- stick was just removed from inventory.

    puck_block = SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.PUCK, exercise_id=puck_exercise.id, order=1)
    tomorrow_plan = _untouched_off_ice_day(1, puck_block)
    weekly_plan = WeeklyPlan(
        id=uuid.uuid4(), user_id=user.id, week_start_date=TODAY, day_plans=[tomorrow_plan]
    )
    db_session.add(weekly_plan)
    await db_session.flush()

    service = ScheduleService(db_session)
    # The PUCK phase itself now has no eligible candidates for this user
    # at all (equipment filter fails every ExerciseEquipmentItem(HOCKEY_
    # STICK) row) -- represented here the same way this test file
    # represents every other "now ineligible" case, an empty pool for
    # that phase.
    _isolate_candidates(service, [])

    changed = await service.patch_week_for_eligibility_change(user, today=TODAY)

    assert changed == 1
    assert tomorrow_plan.training_session.blocks == []


@pytest.mark.asyncio
async def test_falls_back_to_any_eligible_exercise_when_no_pattern_matches(db_session) -> None:
    now_ineligible = _make_exercise("Bench press")
    unrelated_eligible = _make_exercise("Leg press")

    user = _make_user()
    pattern_rows = [
        ExerciseMovementPattern(exercise_id=now_ineligible.id, movement_pattern=MovementPattern.PUSH),
        ExerciseMovementPattern(exercise_id=unrelated_eligible.id, movement_pattern=MovementPattern.SQUAT),
    ]
    db_session.add_all([user, now_ineligible, unrelated_eligible, *pattern_rows])
    await db_session.flush()

    main_block = SessionBlock(
        id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=now_ineligible.id, order=0
    )
    tomorrow_plan = _untouched_off_ice_day(1, main_block)
    weekly_plan = WeeklyPlan(
        id=uuid.uuid4(), user_id=user.id, week_start_date=TODAY, day_plans=[tomorrow_plan]
    )
    db_session.add(weekly_plan)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [unrelated_eligible])

    changed = await service.patch_week_for_eligibility_change(user, today=TODAY)

    assert changed == 1
    await db_session.refresh(main_block)
    assert main_block.exercise_id == unrelated_eligible.id


@pytest.mark.asyncio
async def test_leaves_block_alone_when_no_eligible_substitute_exists_at_all(db_session) -> None:
    user = _make_user()
    now_ineligible = _make_exercise("Bench press")
    db_session.add_all([user, now_ineligible])
    await db_session.flush()

    main_block = SessionBlock(
        id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=now_ineligible.id, order=0
    )
    tomorrow_plan = _untouched_off_ice_day(1, main_block)
    weekly_plan = WeeklyPlan(
        id=uuid.uuid4(), user_id=user.id, week_start_date=TODAY, day_plans=[tomorrow_plan]
    )
    db_session.add(weekly_plan)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, [])  # nothing legal at all for MAIN/OFF_ICE right now

    changed = await service.patch_week_for_eligibility_change(user, today=TODAY)

    assert changed == 0
    await db_session.refresh(main_block)
    assert main_block.exercise_id == now_ineligible.id
