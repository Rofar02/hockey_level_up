"""Readiness-based off-ice difficulty gate in
ScheduleService._apply_difficulty_gate (2026-08-18 planning session,
replacing the old User.level-based off-ice gate this file used to test --
see git history for the superseded tests).

Why the change: User.level/xp tracks engagement, growing from completing
*any* SessionBlock regardless of physical capability (see
app.events.handlers.block_completed.xp_consumer). UserStat tracks measured
capability instead, seeded by the real fitness assessment and grown by
app.events.handlers.block_completed.stat_consumer. Gating off-ice exercise
difficulty on level let a highly-leveled-but-weak account into heavy
barbell work, and left a strong-but-freshly-registered account stuck on
push-ups. This file verifies the replacement:

  1. max_difficulty_for_stat's five bands and their exact boundaries.
  2. Off-ice: an exercise's own primary target_stat, not a single blended
     number, decides its cap -- a user strong in one stat and weak in
     another gets a different cap per exercise in the *same* pick.
  3. On-ice is untouched -- still gated by max_difficulty_for_level, not
     by any UserStat (explicit regression test, since this file's whole
     point last time was almost silently letting on-ice ride along).
  4. Unclassified exercises (no primary ExerciseTargetStat row) get
     UNCLASSIFIED_EXERCISE_CAP, not a free pass.
  5. Last-resort fallback (nothing survives the cap) still relaxes back to
     the full pool with a warning, same contract as before.
  6. The gate reads effective (decay-adjusted) stat value, not the raw
     stored one -- a stale UserStat doesn't hold a cap open forever.
  7. Hard gate, not a preference -- SkillTag priority still can't
     reintroduce an over-cap exercise.

Same `_isolate_candidates` pattern as test_pick_main_periodization.py --
stubs list_for_assembly so the real dev-DB catalog can't leak into these
pools and make picks non-deterministic.
"""
import logging
import random
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.stat_difficulty import UNCLASSIFIED_EXERCISE_CAP, max_difficulty_for_stat
from app.core.training_block import BlockPhase, max_difficulty_for_level
from app.models.exercise import (
    Exercise,
    ExerciseCategory,
    ExerciseMovementPattern,
    ExerciseTargetStat,
    MovementPattern,
    TargetStat,
    TrainingPhase,
)
from app.models.progress import UserStat
from app.models.user import User
from app.services.schedule_service import ScheduleService

_STAT_TO_PATTERN: dict[TargetStat, MovementPattern] = {
    TargetStat.STRENGTH: MovementPattern.HIP_HINGE,
    TargetStat.AGILITY: MovementPattern.SQUAT,
    TargetStat.INTELLECT: MovementPattern.PUSH,
    TargetStat.ENDURANCE: MovementPattern.PULL,
}


def _make_user(*, level: int = 1, category: ExerciseCategory = ExerciseCategory.OFF_ICE) -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"statgate_{unique}",
        email=f"statgate_{unique}@example.com",
        password_hash="irrelevant",
        level=level,
    )


def _make_exercise(
    name: str, difficulty_level: int, *, category: ExerciseCategory = ExerciseCategory.OFF_ICE
) -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=name,
        category=category,
        phase=TrainingPhase.MAIN,
        difficulty_level=difficulty_level,
    )


def _stat_row(exercise: Exercise, target_stat: TargetStat) -> ExerciseTargetStat:
    return ExerciseTargetStat(exercise_id=exercise.id, target_stat=target_stat, order=0)


def _pattern_row(exercise: Exercise, target_stat: TargetStat) -> ExerciseMovementPattern:
    return ExerciseMovementPattern(
        exercise_id=exercise.id, movement_pattern=_STAT_TO_PATTERN[target_stat]
    )


def _user_stat(user: User, target_stat: TargetStat, value: float, *, stale_days: float = 0) -> UserStat:
    return UserStat(
        id=uuid.uuid4(),
        user_id=user.id,
        stat_type=target_stat,
        current_value=value,
        last_updated_at=datetime.now(timezone.utc) - timedelta(days=stale_days),
    )


def _isolate_candidates(service: ScheduleService, exercises: dict[str, Exercise]) -> None:
    async def fake_list_for_assembly(*, phase, user, category, suitable_for_game_day=None):
        return [e for e in exercises.values() if e.category == category]

    service._exercises.list_for_assembly = fake_list_for_assembly


class TestMaxDifficultyForStat:
    """Pure-function boundary checks, no DB needed."""

    @pytest.mark.parametrize(
        ("value", "expected_cap"),
        [
            (0.0, 1),
            (19.9, 1),
            (20.0, 2),  # boundary: exactly 20 lands in the *upper* band
            (39.9, 2),
            (40.0, 3),
            (59.9, 3),
            (60.0, 4),
            (79.9, 4),
            (80.0, 5),  # boundary: >= 80 uncapped
            (100.0, 5),
        ],
    )
    def test_bands_and_boundaries(self, value: float, expected_cap: int) -> None:
        assert max_difficulty_for_stat(value) == expected_cap


@pytest.mark.asyncio
async def test_low_stat_user_never_gets_difficulty_above_the_band(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    db_session.add(_user_stat(user, TargetStat.STRENGTH, 15.0))  # band 1: cap <= 1
    await db_session.flush()

    easy = _make_exercise("Easy", 1)
    hard = _make_exercise("Hard", 4)
    db_session.add_all([easy, hard])
    db_session.add_all([_stat_row(easy, TargetStat.STRENGTH), _stat_row(hard, TargetStat.STRENGTH)])
    db_session.add_all([_pattern_row(easy, TargetStat.STRENGTH), _pattern_row(hard, TargetStat.STRENGTH)])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, {"easy": easy, "hard": hard})
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == ["Easy"]


@pytest.mark.asyncio
async def test_per_exercise_gate_not_a_single_blended_number(db_session) -> None:
    """The whole point of switching off level/fitness_tier: a user strong in
    one characteristic and weak in another gets a *different* cap per
    exercise in the same MAIN pick, not one blended ceiling."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    db_session.add(_user_stat(user, TargetStat.STRENGTH, 90.0))  # band 5: uncapped
    db_session.add(_user_stat(user, TargetStat.AGILITY, 10.0))  # band 1: cap <= 1
    await db_session.flush()

    heavy_squat = _make_exercise("Heavy squat", 5)
    plyo_jump = _make_exercise("Plyo jump", 4)
    easy_hop = _make_exercise("Easy hop", 1)
    db_session.add_all([heavy_squat, plyo_jump, easy_hop])
    db_session.add_all(
        [
            _stat_row(heavy_squat, TargetStat.STRENGTH),
            _stat_row(plyo_jump, TargetStat.AGILITY),
            _stat_row(easy_hop, TargetStat.AGILITY),
        ]
    )
    db_session.add_all(
        [
            _pattern_row(heavy_squat, TargetStat.STRENGTH),
            _pattern_row(plyo_jump, TargetStat.AGILITY),
            _pattern_row(easy_hop, TargetStat.AGILITY),
        ]
    )
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(
        service, {"heavy_squat": heavy_squat, "plyo_jump": plyo_jump, "easy_hop": easy_hop}
    )
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)
    picked_names = {e.name for e in picked}

    # Strong-strength exercise survives despite difficulty 5 -- agility-band
    # exercise "Plyo jump" (difficulty 4) does NOT, because it shares the
    # agility pattern's pool with "Easy hop" and loses to the cap there.
    assert "Heavy squat" in picked_names
    assert "Plyo jump" not in picked_names
    assert "Easy hop" in picked_names


@pytest.mark.asyncio
async def test_on_ice_still_gated_by_level_not_by_any_stat(db_session) -> None:
    """Explicit regression: on-ice is deliberately NOT part of this
    redesign yet (2026-08-18: "про лёд забудь пока что") -- it must keep
    using max_difficulty_for_level, completely unaffected by whatever
    UserStat rows exist."""
    user = _make_user(level=3)  # max_difficulty_for_level(3) == 2
    db_session.add(user)
    await db_session.flush()
    # A sky-high ON_ICE_SKATING stat must NOT unlock difficulty 5 on ice --
    # if it did, this test would prove on-ice quietly got swept into the
    # stat-based gate too.
    db_session.add(_user_stat(user, TargetStat.ON_ICE_SKATING, 95.0))
    await db_session.flush()

    easy = _make_exercise("Ice easy", 1, category=ExerciseCategory.ON_ICE)
    hard = _make_exercise("Ice hard", 5, category=ExerciseCategory.ON_ICE)
    db_session.add_all([easy, hard])
    db_session.add_all(
        [_stat_row(easy, TargetStat.ON_ICE_SKATING), _stat_row(hard, TargetStat.ON_ICE_SKATING)]
    )
    db_session.add_all(
        [
            ExerciseMovementPattern(exercise_id=easy.id, movement_pattern=MovementPattern.LOCOMOTION),
            ExerciseMovementPattern(exercise_id=hard.id, movement_pattern=MovementPattern.LOCOMOTION),
        ]
    )
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, {"easy": easy, "hard": hard})
    picked = await service._pick_main(ExerciseCategory.ON_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == ["Ice easy"]
    assert max_difficulty_for_level(3) == 2


@pytest.mark.asyncio
async def test_unclassified_exercise_gets_the_conservative_cap(db_session) -> None:
    """No primary ExerciseTargetStat row at all -- can't be matched to any
    characteristic, so it's treated as UNCLASSIFIED_EXERCISE_CAP rather
    than slipping through ungated."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    db_session.add(_user_stat(user, TargetStat.STRENGTH, 95.0))  # would be uncapped if classified
    await db_session.flush()

    unclassified = _make_exercise("Unclassified", UNCLASSIFIED_EXERCISE_CAP + 1)
    db_session.add(unclassified)
    db_session.add(_pattern_row(unclassified, TargetStat.STRENGTH))
    # Deliberately no ExerciseTargetStat row.
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, {"unclassified": unclassified})

    with pytest.raises(AssertionError):
        # Sanity: the fixture itself really is above the conservative cap,
        # otherwise this test wouldn't distinguish "gated" from "not".
        assert unclassified.difficulty_level <= UNCLASSIFIED_EXERCISE_CAP

    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)
    # Only candidate is over the conservative cap -> last-resort fallback
    # relaxes back to it rather than returning nothing.
    assert [e.name for e in picked] == ["Unclassified"]


@pytest.mark.asyncio
async def test_stale_stat_uses_decayed_effective_value_not_raw(db_session) -> None:
    """A UserStat well past its grace period must gate on its decayed
    value, not the raw stored current_value -- proves the gate actually
    calls get_effective_value instead of reading current_value directly."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    # Raw value 90 (band 5, uncapped) but 200 days stale -- way past the
    # 10-day grace period, decays hard toward the 10% floor (9.0).
    db_session.add(_user_stat(user, TargetStat.STRENGTH, 90.0, stale_days=200))
    await db_session.flush()

    easy = _make_exercise("Easy", 1)
    hard = _make_exercise("Hard", 5)
    db_session.add_all([easy, hard])
    db_session.add_all([_stat_row(easy, TargetStat.STRENGTH), _stat_row(hard, TargetStat.STRENGTH)])
    db_session.add_all([_pattern_row(easy, TargetStat.STRENGTH), _pattern_row(hard, TargetStat.STRENGTH)])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, {"easy": easy, "hard": hard})
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == ["Easy"]


@pytest.mark.asyncio
async def test_fallback_when_nothing_survives_the_cap(
    db_session, caplog: pytest.LogCaptureFixture
) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    db_session.add(_user_stat(user, TargetStat.ENDURANCE, 5.0))  # band 1
    await db_session.flush()

    only_hard = _make_exercise("Only-hard", 5)
    db_session.add(only_hard)
    db_session.add(_stat_row(only_hard, TargetStat.ENDURANCE))
    db_session.add(_pattern_row(only_hard, TargetStat.ENDURANCE))
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, {"only_hard": only_hard})

    with caplog.at_level(logging.WARNING):
        picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == ["Only-hard"]
    assert any(
        "falling back to the full difficulty range" in record.message for record in caplog.records
    )


@pytest.mark.asyncio
async def test_gate_is_not_overridden_by_skilltag_priority(db_session) -> None:
    """The readiness cap must win even when a SkillTag-preferred exercise
    is over it -- a hard capability gate, not a soft preference."""
    from app.models.skill import Skill, SkillTag, UserSkillPreference

    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    db_session.add(_user_stat(user, TargetStat.STRENGTH, 15.0))  # band 1: cap <= 1
    await db_session.flush()

    easy_untagged = _make_exercise("Easy-untagged", 1)
    hard_tagged = _make_exercise("Hard-tagged", 5)
    db_session.add_all([easy_untagged, hard_tagged])
    db_session.add_all(
        [_stat_row(easy_untagged, TargetStat.STRENGTH), _stat_row(hard_tagged, TargetStat.STRENGTH)]
    )
    db_session.add_all(
        [
            _pattern_row(easy_untagged, TargetStat.STRENGTH),
            _pattern_row(hard_tagged, TargetStat.STRENGTH),
        ]
    )
    await db_session.flush()

    skill = Skill(id=uuid.uuid4(), name=f"Test skill {uuid.uuid4().hex[:8]}")
    db_session.add(skill)
    await db_session.flush()
    db_session.add(
        SkillTag(exercise_id=hard_tagged.id, skill_id=skill.id, transfer_note="test transfer note")
    )
    db_session.add(UserSkillPreference(user_id=user.id, skill_id=skill.id))
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, {"easy_untagged": easy_untagged, "hard_tagged": hard_tagged})
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == ["Easy-untagged"]


@pytest.mark.asyncio
async def test_pick_single_respects_the_stat_gate_off_ice(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    db_session.add(_user_stat(user, TargetStat.STRENGTH, 15.0))  # band 1
    await db_session.flush()

    easy = _make_exercise("Easy-warmup", 1)
    easy.phase = TrainingPhase.WARMUP
    hard = _make_exercise("Hard-warmup", 5)
    hard.phase = TrainingPhase.WARMUP
    db_session.add_all([easy, hard])
    db_session.add_all([_stat_row(easy, TargetStat.STRENGTH), _stat_row(hard, TargetStat.STRENGTH)])
    await db_session.flush()

    service = ScheduleService(db_session)

    async def fake_list_for_assembly(*, phase, user, category, suitable_for_game_day=None):
        return [easy, hard]

    service._exercises.list_for_assembly = fake_list_for_assembly
    monkeypatch.setattr(random, "choice", lambda pool: max(pool, key=lambda e: e.difficulty_level))

    picked = await service._pick_single(
        TrainingPhase.WARMUP, ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION
    )

    assert picked is not None
    assert picked.name == "Easy-warmup"
