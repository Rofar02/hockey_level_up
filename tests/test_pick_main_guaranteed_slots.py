"""2026-09-18 audit round 2 item #4 ("выносливость и катание почти не
попадают в основной блок"): _pick_main's guarantee_endurance/
guarantee_locomotion params, resolved once per week by
_choose_guaranteed_slot_dates. Same isolation/determinism conventions as
test_pick_main_coherence_validator.py -- random.randint/shuffle
monkeypatched, single-candidate-per-pattern fixtures so random.choice never
needs mocking (every pool it's asked to choose from has exactly one
element).

_enforce_muscle_group_cap's own protected_exercise_ids behavior (the other
half of this audit item) is covered separately in
test_pick_main_coherence_validator.py, which already owns that function's
test conventions.
"""
import uuid
from datetime import date, timedelta

import pytest

from app.core.training_block import BlockPhase
from app.models.exercise import (
    Exercise,
    ExerciseCategory,
    ExerciseMovementPattern,
    ExerciseMuscleGroup,
    ExerciseTargetStat,
    MovementPattern,
    MuscleGroup,
    StimulusType,
    TargetStat,
    TrainingPhase,
)
from app.models.schedule import DaySessionType
from app.models.user import User
from app.schemas.schedule import DayPlanIn
from app.services.schedule_service import ScheduleService

_EXPLOSIVE_PATTERN_SET = frozenset(
    {MovementPattern.LOCOMOTION, MovementPattern.STICK_HANDLING, MovementPattern.COORDINATION}
)


@pytest.fixture(autouse=True)
def deterministic_shuffle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Leaves every shuffle as a no-op (declared MovementPattern enum
    order survives) EXCEPT role 1's own 3-element explosive-pattern list,
    which is reordered so COORDINATION is tried first -- these tests need
    role 1 to claim a *different* explosive pattern than LOCOMOTION so
    LOCOMOTION genuinely reaches role 4, without touching role 4's own
    accessory-pattern order (which several tests rely on being the plain
    enum declaration order for their "no guarantee" baseline)."""
    import random

    def fake_shuffle(seq: list) -> None:
        if set(seq) == _EXPLOSIVE_PATTERN_SET:
            seq.sort(key=lambda p: 0 if p == MovementPattern.COORDINATION else 1)

    monkeypatch.setattr(random, "shuffle", fake_shuffle)


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"guaranteed_{unique}",
        email=f"guaranteed_{unique}@example.com",
        password_hash="irrelevant",
    )


def _make_exercise(
    name: str,
    pattern: MovementPattern,
    *,
    stimulus_type: StimulusType | None = None,
    muscle_group: MuscleGroup | None = None,
) -> tuple[Exercise, ExerciseTargetStat, ExerciseMovementPattern, ExerciseMuscleGroup | None]:
    exercise = Exercise(
        id=uuid.uuid4(),
        name=name,
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=1,
        stimulus_type=stimulus_type,
    )
    muscle_row = (
        ExerciseMuscleGroup(exercise_id=exercise.id, muscle_group=muscle_group, weight=1.0)
        if muscle_group is not None
        else None
    )
    return (
        exercise,
        ExerciseTargetStat(exercise_id=exercise.id, target_stat=TargetStat.STRENGTH, order=0),
        ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=pattern),
        muscle_row,
    )


def _add_all(db_session, rows) -> list[Exercise]:
    db_session.add_all([e for e, _, _, _ in rows])
    db_session.add_all([s for _, s, _, _ in rows])
    db_session.add_all([p for _, _, p, _ in rows])
    db_session.add_all([m for _, _, _, m in rows if m is not None])
    return [e for e, _, _, _ in rows]


def _isolate_candidates(service: ScheduleService, exercises: list[Exercise]) -> None:
    async def fake_list_for_assembly(*, phase, user, category, suitable_for_game_day=None):
        return [e for e in exercises if e.phase == phase and e.category == category]

    service._exercises.list_for_assembly = fake_list_for_assembly


@pytest.mark.asyncio
async def test_guarantee_endurance_wins_a_scarce_slot_over_the_ordinary_pick(
    db_session, monkeypatch
) -> None:
    """ROTATION sorts before CORE in MovementPattern's own declaration
    order, so with count=1 (a single accessory slot, nothing else
    competing) the ordinary pick lands on ROTATION -- CORE's
    ENDURANCE-stimulus exercise never gets a look-in without the
    guarantee."""
    import random

    monkeypatch.setattr(random, "randint", lambda a, b: 1)

    user = _make_user()
    db_session.add(user)
    exercises = _add_all(
        db_session,
        [
            _make_exercise("A-rotation", MovementPattern.ROTATION, stimulus_type=StimulusType.STRENGTH),
            _make_exercise("Z-core-endurance", MovementPattern.CORE, stimulus_type=StimulusType.ENDURANCE),
        ],
    )
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)

    without_guarantee = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, guarantee_endurance=False
    )
    assert [e.name for e in without_guarantee] == ["A-rotation"]

    with_guarantee = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, guarantee_endurance=True
    )
    assert [e.name for e in with_guarantee] == ["Z-core-endurance"]


@pytest.mark.asyncio
async def test_guarantee_locomotion_wins_a_scarce_slot_when_role1_took_something_else(
    db_session, monkeypatch
) -> None:
    """Role 1 claims COORDINATION (forced by the deterministic_shuffle
    fixture), leaving LOCOMOTION free for role 4. ROTATION sorts before
    LOCOMOTION in MovementPattern's own declaration order, so with a
    single remaining accessory slot the ordinary pick lands on ROTATION
    without the guarantee."""
    import random

    monkeypatch.setattr(random, "randint", lambda a, b: 2)  # role 1 (1) + role 4 (1)

    user = _make_user()
    db_session.add(user)
    exercises = _add_all(
        db_session,
        [
            _make_exercise("A-coordination", MovementPattern.COORDINATION, stimulus_type=StimulusType.POWER),
            _make_exercise("B-rotation", MovementPattern.ROTATION),
            _make_exercise("Z-locomotion", MovementPattern.LOCOMOTION),
        ],
    )
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)

    without_guarantee = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, guarantee_locomotion=False
    )
    assert [e.name for e in without_guarantee] == ["A-coordination", "B-rotation"]

    with_guarantee = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, guarantee_locomotion=True
    )
    assert [e.name for e in with_guarantee] == ["A-coordination", "Z-locomotion"]


@pytest.mark.asyncio
async def test_guarantee_locomotion_is_a_no_op_when_role1_already_claimed_it(
    db_session, monkeypatch
) -> None:
    """LOCOMOTION is the only explosive-role candidate at all (no
    COORDINATION/STICK_HANDLING), so role 1 claims it regardless of
    shuffle order -- the "at most one per movement_pattern" invariant then
    means role 4 can never also pick a LOCOMOTION exercise. The guarantee
    must not crash or otherwise misbehave when its target pattern is
    already gone before role 4 even starts."""
    import random

    monkeypatch.setattr(random, "randint", lambda a, b: 4)

    user = _make_user()
    db_session.add(user)
    exercises = _add_all(
        db_session,
        [_make_exercise("Only-locomotion", MovementPattern.LOCOMOTION, stimulus_type=StimulusType.POWER)],
    )
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION, guarantee_locomotion=True
    )

    assert [e.name for e in picked] == ["Only-locomotion"]


@pytest.mark.asyncio
async def test_both_guarantees_fold_onto_one_slot_when_locomotion_is_the_only_endurance_carrier(
    db_session, monkeypatch
) -> None:
    """Round 2 audit item #4's merge case: LOCOMOTION is simultaneously the
    skating guarantee's target pattern AND the only accessory-eligible
    pattern carrying an ENDURANCE-stimulus exercise. Both guarantees must
    land on that single slot -- not reserve two, and not crash trying to
    remove the same pattern from accessory_patterns twice."""
    import random

    monkeypatch.setattr(random, "randint", lambda a, b: 4)  # plenty of room; nothing else has candidates

    user = _make_user()
    db_session.add(user)
    exercises = _add_all(
        db_session,
        [
            _make_exercise("A-coordination", MovementPattern.COORDINATION, stimulus_type=StimulusType.POWER),
            _make_exercise(
                "Z-locomotion-endurance", MovementPattern.LOCOMOTION, stimulus_type=StimulusType.ENDURANCE
            ),
        ],
    )
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE,
        user,
        BlockPhase.ACCUMULATION,
        guarantee_endurance=True,
        guarantee_locomotion=True,
    )

    # Exactly one exercise per guaranteed pattern -- role 1's own pick plus
    # a single (not doubled) role-4 slot for the merged guarantee.
    assert [e.name for e in picked] == ["A-coordination", "Z-locomotion-endurance"]


@pytest.mark.asyncio
async def test_guaranteed_exercise_survives_cap_enforcement_as_the_sole_overload_cause(
    db_session, monkeypatch
) -> None:
    """Integration proof of the round 2 audit's original complaint: the
    guaranteed LOCOMOTION+ENDURANCE pick ("Z") shares MuscleGroup.CORE
    with three other role-4 picks, pushing CORE to 4 (over
    MAX_EXERCISES_PER_MUSCLE_GROUP=3). Z's own pattern has a real
    substitute ("ALT-locomotion-plain") that avoids CORE entirely -- the
    kind of candidate _enforce_muscle_group_cap would normally prefer and
    silently swap to, which would drop Z's ENDURANCE stimulus and quietly
    break the guarantee. protected_exercise_ids must stop that: CORE stays
    honestly over cap (no substitute exists for the three *other*
    single-candidate CORE patterns), and Z itself survives untouched.
    """
    import random

    monkeypatch.setattr(random, "randint", lambda a, b: 5)  # role 1 (1) + role 4 (4)

    user = _make_user()
    db_session.add(user)
    exercises = _add_all(
        db_session,
        [
            _make_exercise(
                "A-coordination", MovementPattern.COORDINATION,
                stimulus_type=StimulusType.POWER, muscle_group=MuscleGroup.QUADS,
            ),
            _make_exercise(
                "Z-locomotion-endurance", MovementPattern.LOCOMOTION,
                stimulus_type=StimulusType.ENDURANCE, muscle_group=MuscleGroup.CORE,
            ),
            # A real substitute for Z's own pattern that avoids CORE --
            # exactly what _enforce_muscle_group_cap prefers when nothing
            # protects the offender.
            _make_exercise(
                "ALT-locomotion-plain", MovementPattern.LOCOMOTION,
                stimulus_type=StimulusType.STRENGTH, muscle_group=MuscleGroup.CALVES,
            ),
            _make_exercise("B-rotation-core", MovementPattern.ROTATION, muscle_group=MuscleGroup.CORE),
            _make_exercise("C-ankle-core", MovementPattern.ANKLE_MOBILITY, muscle_group=MuscleGroup.CORE),
            _make_exercise("D-hip-core", MovementPattern.HIP_MOBILITY, muscle_group=MuscleGroup.CORE),
        ],
    )
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, exercises)
    picked = await service._pick_main(
        ExerciseCategory.OFF_ICE,
        user,
        BlockPhase.ACCUMULATION,
        guarantee_endurance=True,
        guarantee_locomotion=True,
    )

    names = [e.name for e in picked]
    assert "Z-locomotion-endurance" in names
    assert "ALT-locomotion-plain" not in names
    core_count = sum(1 for e in picked if e.name in {"Z-locomotion-endurance", "B-rotation-core", "C-ankle-core", "D-hip-core"})
    assert core_count == 4  # honestly over MAX_EXERCISES_PER_MUSCLE_GROUP -- not silently fixed


def test_choose_guaranteed_slot_dates_is_a_no_op_for_a_week_with_no_off_ice_day() -> None:
    """A week declared entirely ON_ICE/REST (or GAME) has no day _pick_main
    could ever touch -- MAIN only exists on OFF_ICE. Must return (None,
    None) rather than raising or picking a date that doesn't qualify."""
    today = date(2026, 9, 21)
    days = [
        DayPlanIn(date=today, session_type=DaySessionType.ON_ICE),
        DayPlanIn(date=today + timedelta(days=1), session_type=DaySessionType.REST),
        DayPlanIn(date=today + timedelta(days=2), session_type=DaySessionType.GAME),
    ]

    endurance_date, locomotion_date = ScheduleService._choose_guaranteed_slot_dates(days)

    assert endurance_date is None
    assert locomotion_date is None


def test_choose_guaranteed_slot_dates_only_picks_among_off_ice_days() -> None:
    today = date(2026, 9, 21)
    off_ice_date = today + timedelta(days=2)
    days = [
        DayPlanIn(date=today, session_type=DaySessionType.ON_ICE),
        DayPlanIn(date=today + timedelta(days=1), session_type=DaySessionType.REST),
        DayPlanIn(date=off_ice_date, session_type=DaySessionType.OFF_ICE),
    ]

    endurance_date, locomotion_date = ScheduleService._choose_guaranteed_slot_dates(days)

    assert endurance_date == off_ice_date
    assert locomotion_date == off_ice_date
