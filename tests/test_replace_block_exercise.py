"""Stage 1.5 (2026-08-20 planning session, "тренажёр занят"): manual,
single-slot exercise replacement -- ScheduleService.replace_block_exercise.
Not a session regenerate: exactly one SessionBlock's exercise_id changes,
everything else in the session (including its own order/completed_at)
stays untouched. Post-Stage-2 behavior per the plan: MAIN blocks
substitute within the outgoing exercise's own role (_role_patterns_for),
aware of muscle groups already loaded by the rest of today's session;
WARMUP/COOLDOWN blocks substitute by movement_pattern via the existing
_pick_single (roles/archetypes are a MAIN-only concept).

Real ExerciseMovementPattern/ExerciseMuscleGroup rows throughout, same
"lives in the real table" style as test_pick_main_day_archetype.py --
only list_for_assembly is faked, to keep the real seeded catalog from
leaking into these pools.
"""
import uuid
from datetime import date

import pytest

from app.core.training_block import BlockPhase
from app.models.exercise import (
    Exercise,
    ExerciseCategory,
    ExerciseMovementPattern,
    ExerciseMuscleGroup,
    MovementPattern,
    MuscleGroup,
    TrainingPhase,
    WarmupStage,
)
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan
from app.models.user import User
from app.services.schedule_service import ScheduleService

TODAY = date(2026, 8, 20)


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"replace_{unique}",
        email=f"replace_{unique}@example.com",
        password_hash="irrelevant",
        level=15,
    )


def _make_exercise(
    *, name: str, phase: TrainingPhase = TrainingPhase.MAIN, warmup_stage: WarmupStage | None = None
) -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=name,
        category=ExerciseCategory.OFF_ICE,
        phase=phase,
        difficulty_level=1,
        warmup_stage=warmup_stage,
    )


def _isolate_candidates(service: ScheduleService, exercises: dict[str, Exercise]) -> None:
    async def fake_list_for_assembly(*, phase, user, category=None, suitable_for_game_day=None):
        pool = [e for e in exercises.values() if e.phase == phase]
        if category is not None:
            pool = [e for e in pool if e.category == category]
        return pool

    service._exercises.list_for_assembly = fake_list_for_assembly


async def _make_session(db_session, user: User, blocks: list[SessionBlock]) -> TrainingSession:
    weekly_plan = WeeklyPlan(id=uuid.uuid4(), user_id=user.id, week_start_date=TODAY)
    db_session.add(weekly_plan)
    await db_session.flush()
    day_plan = DayPlan(
        id=uuid.uuid4(), weekly_plan_id=weekly_plan.id, date=TODAY, session_type=DaySessionType.OFF_ICE
    )
    db_session.add(day_plan)
    training_session = TrainingSession(id=uuid.uuid4(), day_plan_id=day_plan.id, blocks=blocks)
    db_session.add(training_session)
    await db_session.flush()
    return training_session


@pytest.mark.asyncio
async def test_main_replacement_stays_within_the_same_role(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    outgoing = _make_exercise(name="AAA squat outgoing")
    same_role = _make_exercise(name="BBB hip hinge same role")
    other_role = _make_exercise(name="CCC rotation other role")
    sibling = _make_exercise(name="DDD push sibling")
    exercises = {"outgoing": outgoing, "same_role": same_role, "other_role": other_role, "sibling": sibling}
    db_session.add_all(exercises.values())
    db_session.add_all([
        ExerciseMovementPattern(exercise_id=outgoing.id, movement_pattern=MovementPattern.SQUAT),
        ExerciseMovementPattern(exercise_id=same_role.id, movement_pattern=MovementPattern.HIP_HINGE),
        ExerciseMovementPattern(exercise_id=other_role.id, movement_pattern=MovementPattern.ROTATION),
        ExerciseMovementPattern(exercise_id=sibling.id, movement_pattern=MovementPattern.PUSH),
    ])
    await db_session.flush()

    outgoing_block = SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=outgoing.id, order=0)
    sibling_block = SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=sibling.id, order=1)
    await _make_session(db_session, user, [outgoing_block, sibling_block])

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    result = await service.replace_block_exercise(outgoing_block.id, user)

    assert result.exercise.id == same_role.id
    assert result.id == outgoing_block.id
    assert result.phase == TrainingPhase.MAIN


@pytest.mark.asyncio
async def test_main_replacement_avoids_a_muscle_group_already_loaded_today(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    outgoing = _make_exercise(name="AAA squat outgoing")
    overlaps = _make_exercise(name="BBB hip hinge overlaps quads")
    varied = _make_exercise(name="CCC hip hinge varied")
    sibling = _make_exercise(name="DDD sibling loads quads")
    exercises = {"outgoing": outgoing, "overlaps": overlaps, "varied": varied, "sibling": sibling}
    db_session.add_all(exercises.values())
    db_session.add_all([
        ExerciseMovementPattern(exercise_id=outgoing.id, movement_pattern=MovementPattern.SQUAT),
        ExerciseMovementPattern(exercise_id=overlaps.id, movement_pattern=MovementPattern.HIP_HINGE),
        ExerciseMovementPattern(exercise_id=varied.id, movement_pattern=MovementPattern.HIP_HINGE),
        ExerciseMovementPattern(exercise_id=sibling.id, movement_pattern=MovementPattern.PUSH),
        ExerciseMuscleGroup(exercise_id=overlaps.id, muscle_group=MuscleGroup.QUADS, weight=1.0),
        ExerciseMuscleGroup(exercise_id=varied.id, muscle_group=MuscleGroup.HAMSTRINGS, weight=1.0),
        ExerciseMuscleGroup(exercise_id=sibling.id, muscle_group=MuscleGroup.QUADS, weight=1.0),
    ])
    await db_session.flush()

    outgoing_block = SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=outgoing.id, order=0)
    sibling_block = SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=sibling.id, order=1)
    await _make_session(db_session, user, [outgoing_block, sibling_block])

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    result = await service.replace_block_exercise(outgoing_block.id, user)

    # Both candidates match the role (hip_hinge), but "overlaps" shares
    # QUADS with the sibling block already in today's session -- "varied"
    # must win.
    assert result.exercise.id == varied.id


@pytest.mark.asyncio
async def test_main_replacement_falls_back_when_no_role_match_exists(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    outgoing = _make_exercise(name="AAA squat outgoing")
    only_candidate = _make_exercise(name="BBB rotation only candidate")
    exercises = {"outgoing": outgoing, "only_candidate": only_candidate}
    db_session.add_all(exercises.values())
    db_session.add_all([
        ExerciseMovementPattern(exercise_id=outgoing.id, movement_pattern=MovementPattern.SQUAT),
        ExerciseMovementPattern(exercise_id=only_candidate.id, movement_pattern=MovementPattern.ROTATION),
    ])
    await db_session.flush()

    outgoing_block = SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=outgoing.id, order=0)
    await _make_session(db_session, user, [outgoing_block])

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    result = await service.replace_block_exercise(outgoing_block.id, user)

    # No SQUAT/HIP_HINGE candidate exists -- falls back to the only other
    # exercise in the pool rather than leaving the slot unfilled.
    assert result.exercise.id == only_candidate.id


@pytest.mark.asyncio
async def test_warmup_replacement_matches_movement_pattern(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    outgoing = _make_exercise(name="AAA squat warmup", phase=TrainingPhase.WARMUP, warmup_stage=WarmupStage.DYNAMIC)
    matching = _make_exercise(name="BBB squat warmup match", phase=TrainingPhase.WARMUP, warmup_stage=WarmupStage.DYNAMIC)
    unrelated = _make_exercise(name="CCC pull warmup unrelated", phase=TrainingPhase.WARMUP, warmup_stage=WarmupStage.DYNAMIC)
    exercises = {"outgoing": outgoing, "matching": matching, "unrelated": unrelated}
    db_session.add_all(exercises.values())
    db_session.add_all([
        ExerciseMovementPattern(exercise_id=outgoing.id, movement_pattern=MovementPattern.SQUAT),
        ExerciseMovementPattern(exercise_id=matching.id, movement_pattern=MovementPattern.SQUAT),
        ExerciseMovementPattern(exercise_id=unrelated.id, movement_pattern=MovementPattern.PULL),
    ])
    await db_session.flush()

    outgoing_block = SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.WARMUP, exercise_id=outgoing.id, order=0)
    await _make_session(db_session, user, [outgoing_block])

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    result = await service.replace_block_exercise(outgoing_block.id, user)

    assert result.exercise.id == matching.id
    assert result.phase == TrainingPhase.WARMUP


@pytest.mark.asyncio
async def test_returns_404_for_another_users_block(db_session) -> None:
    owner = _make_user()
    intruder = _make_user()
    db_session.add_all([owner, intruder])
    await db_session.flush()

    exercise = _make_exercise(name="AAA someones exercise")
    db_session.add(exercise)
    db_session.add(ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=MovementPattern.SQUAT))
    await db_session.flush()

    block = SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=0)
    await _make_session(db_session, owner, [block])

    service = ScheduleService(db_session)
    with pytest.raises(Exception) as exc_info:
        await service.replace_block_exercise(block.id, intruder)
    assert getattr(exc_info.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_returns_409_for_an_already_completed_block(db_session) -> None:
    from datetime import datetime, timezone

    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    exercise = _make_exercise(name="AAA completed exercise")
    db_session.add(exercise)
    db_session.add(ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=MovementPattern.SQUAT))
    await db_session.flush()

    block = SessionBlock(
        id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=0,
        completed_at=datetime.now(timezone.utc),
    )
    await _make_session(db_session, user, [block])

    service = ScheduleService(db_session)
    with pytest.raises(Exception) as exc_info:
        await service.replace_block_exercise(block.id, user)
    assert getattr(exc_info.value, "status_code", None) == 409


@pytest.mark.asyncio
async def test_returns_409_when_no_substitute_is_available(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    only_exercise = _make_exercise(name="AAA lonely exercise")
    exercises = {"only": only_exercise}
    db_session.add(only_exercise)
    db_session.add(ExerciseMovementPattern(exercise_id=only_exercise.id, movement_pattern=MovementPattern.SQUAT))
    await db_session.flush()

    block = SessionBlock(id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=only_exercise.id, order=0)
    await _make_session(db_session, user, [block])

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    with pytest.raises(Exception) as exc_info:
        await service.replace_block_exercise(block.id, user)
    assert getattr(exc_info.value, "status_code", None) == 409
