"""User.level difficulty gate in ScheduleService._pick_main/_pick_single.

Verifies:
  1. max_difficulty_for_level's three tiers and their exact boundaries
     (level=8 and level=15 land in the *upper* tier each crosses into).
  2. _pick_main never returns an exercise above the caller's level cap.
  3. The level cap is a hard filter, not a preference -- unlike the
     block-phase difficulty predicate, it doesn't get overridden by
     SkillTag priority.
  4. Last-resort fallback: when literally nothing in the catalog for a
     stat clears the cap, _pick_main still returns something (never an
     empty/broken plan) and logs a warning about it.

Same `_isolate_candidates` pattern as test_pick_main_periodization.py --
stubs list_for_assembly so the real dev-DB catalog can't leak into these
pools and make picks non-deterministic.
"""
import logging
import random
import uuid

import pytest

from app.core.training_block import BlockPhase, max_difficulty_for_level
from app.models.exercise import EquipmentType, Exercise, ExerciseCategory, TargetStat, TrainingPhase
from app.models.user import User
from app.services.schedule_service import ScheduleService


def _make_user(level: int) -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"levelgate_{unique}",
        email=f"levelgate_{unique}@example.com",
        password_hash="irrelevant",
        equipment_access=EquipmentType.BODYWEIGHT,
        level=level,
    )


def _make_exercise(name: str, target_stat: TargetStat, difficulty_level: int) -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        name=name,
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        target_stat=target_stat,
        difficulty_level=difficulty_level,
        equipment_type=EquipmentType.BODYWEIGHT,
    )


def _isolate_candidates(service: ScheduleService, exercises: dict[str, Exercise]) -> None:
    async def fake_list_for_assembly(*, phase, equipment_access, category):
        return list(exercises.values())

    service._exercises.list_for_assembly = fake_list_for_assembly


class TestMaxDifficultyForLevel:
    """Pure-function boundary checks, no DB needed."""

    @pytest.mark.parametrize(
        ("level", "expected_cap"),
        [
            (1, 2),
            (7, 2),
            (8, 3),  # boundary: level 8-14 -> <=3, not still <=2
            (10, 3),
            (14, 3),
            (15, 5),  # boundary: level >= 15 -> uncapped
            (30, 5),
        ],
    )
    def test_tiers_and_boundaries(self, level: int, expected_cap: int) -> None:
        assert max_difficulty_for_level(level) == expected_cap


@pytest.mark.asyncio
async def test_low_level_user_never_gets_difficulty_above_2(db_session) -> None:
    user = _make_user(level=3)
    db_session.add(user)

    easy = _make_exercise("Easy", TargetStat.STRENGTH, 1)
    mid_easy = _make_exercise("Mid-easy", TargetStat.STRENGTH, 2)
    hard = _make_exercise("Hard", TargetStat.STRENGTH, 4)
    very_hard = _make_exercise("Very-hard", TargetStat.STRENGTH, 5)
    db_session.add_all([easy, mid_easy, hard, very_hard])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(
        service, {"easy": easy, "mid_easy": mid_easy, "hard": hard, "very_hard": very_hard}
    )
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert len(picked) == 1
    assert picked[0].difficulty_level <= 2
    assert picked[0].name in {"Easy", "Mid-easy"}


@pytest.mark.asyncio
async def test_mid_level_user_gets_up_to_3_not_4_or_5(db_session) -> None:
    user = _make_user(level=10)
    db_session.add(user)

    easy = _make_exercise("Easy", TargetStat.STRENGTH, 1)
    mid = _make_exercise("Mid", TargetStat.STRENGTH, 3)
    hard = _make_exercise("Hard", TargetStat.STRENGTH, 4)
    very_hard = _make_exercise("Very-hard", TargetStat.STRENGTH, 5)
    db_session.add_all([easy, mid, hard, very_hard])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, {"easy": easy, "mid": mid, "hard": hard, "very_hard": very_hard})
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert len(picked) == 1
    assert picked[0].difficulty_level <= 3
    assert picked[0].name in {"Easy", "Mid"}


@pytest.mark.asyncio
async def test_high_level_user_can_get_any_difficulty(db_session) -> None:
    user = _make_user(level=20)
    db_session.add(user)

    # Only a difficulty-5 candidate exists -- a capped user would fall back
    # to the full pool anyway, which wouldn't distinguish "capped" from
    # "uncapped". Here the pool is a single easy exercise *and* a single
    # very-hard one on different stats, so both must survive independently
    # for an uncapped user.
    very_hard = _make_exercise("Very-hard", TargetStat.STRENGTH, 5)
    easy = _make_exercise("Easy", TargetStat.AGILITY, 1)
    db_session.add_all([very_hard, easy])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, {"very_hard": very_hard, "easy": easy})
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert {e.name for e in picked} == {"Very-hard", "Easy"}


@pytest.mark.asyncio
async def test_boundary_level_8_allows_difficulty_3_but_not_4(db_session) -> None:
    user = _make_user(level=8)
    db_session.add(user)

    mid = _make_exercise("Mid", TargetStat.STRENGTH, 3)
    hard = _make_exercise("Hard", TargetStat.STRENGTH, 4)
    db_session.add_all([mid, hard])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, {"mid": mid, "hard": hard})
    picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == ["Mid"]


@pytest.mark.asyncio
async def test_boundary_level_15_is_uncapped_level_14_still_capped(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same two-candidate pool (difficulty 3 and 5) for both users -- picking
    the hardest survivor deterministically isolates exactly what the cap
    let through, with no fallback ambiguity (both pools are non-empty after
    filtering either way)."""
    monkeypatch.setattr(random, "choice", lambda pool: max(pool, key=lambda e: e.difficulty_level))

    mid = _make_exercise("Mid", TargetStat.STRENGTH, 3)
    hard = _make_exercise("Hard", TargetStat.STRENGTH, 5)
    db_session.add_all([mid, hard])
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, {"mid": mid, "hard": hard})

    uncapped_user = _make_user(level=15)
    db_session.add(uncapped_user)
    picked_uncapped = await service._pick_main(
        ExerciseCategory.OFF_ICE, uncapped_user, BlockPhase.ACCUMULATION
    )
    assert [e.name for e in picked_uncapped] == ["Hard"]

    capped_user = _make_user(level=14)
    db_session.add(capped_user)
    picked_capped = await service._pick_main(
        ExerciseCategory.OFF_ICE, capped_user, BlockPhase.ACCUMULATION
    )
    assert [e.name for e in picked_capped] == ["Mid"]


@pytest.mark.asyncio
async def test_level_cap_is_not_overridden_by_skilltag_priority(db_session) -> None:
    """The level cap must win even when a SkillTag-preferred exercise is
    over the cap -- it's a hard capability gate, not a soft preference."""
    from app.models.skill import Skill, SkillTag, UserSkillPreference

    user = _make_user(level=3)
    db_session.add(user)

    easy_untagged = _make_exercise("Easy-untagged", TargetStat.STRENGTH, 2)
    hard_tagged = _make_exercise("Hard-tagged", TargetStat.STRENGTH, 5)
    db_session.add_all([easy_untagged, hard_tagged])
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

    # Tagged exercise is over the level cap -- must lose to the untagged
    # in-cap one, not win on skill priority.
    assert [e.name for e in picked] == ["Easy-untagged"]


@pytest.mark.asyncio
async def test_fallback_when_stat_has_nothing_under_the_cap(
    db_session, caplog: pytest.LogCaptureFixture
) -> None:
    """No difficulty<=2 candidate exists for this stat at all -- rather than
    silently dropping the stat (empty/thin plan), the cap relaxes for just
    that stat and a warning is logged. Mirrors a real gap found in the
    current catalog (off_ice/main/endurance has zero difficulty<=2 rows)."""
    user = _make_user(level=1)
    db_session.add(user)

    only_hard = _make_exercise("Only-hard", TargetStat.ENDURANCE, 5)
    db_session.add(only_hard)
    await db_session.flush()

    service = ScheduleService(db_session)
    _isolate_candidates(service, {"only_hard": only_hard})

    with caplog.at_level(logging.WARNING):
        picked = await service._pick_main(ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION)

    assert [e.name for e in picked] == ["Only-hard"]
    assert any(
        "No exercises with difficulty<=" in record.message for record in caplog.records
    )


@pytest.mark.asyncio
async def test_pick_single_respects_level_cap(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    user = _make_user(level=3)
    db_session.add(user)

    easy = _make_exercise("Easy-warmup", TargetStat.STRENGTH, 1)
    easy.phase = TrainingPhase.WARMUP
    hard = _make_exercise("Hard-warmup", TargetStat.STRENGTH, 5)
    hard.phase = TrainingPhase.WARMUP
    db_session.add_all([easy, hard])
    await db_session.flush()

    service = ScheduleService(db_session)

    async def fake_list_for_assembly(*, phase, equipment_access, category):
        return [easy, hard]

    service._exercises.list_for_assembly = fake_list_for_assembly
    # Deliberately biased toward the *harder* candidate -- if the level cap
    # weren't actually filtering the pool before this pick, "Hard-warmup"
    # would win every time.
    monkeypatch.setattr(random, "choice", lambda pool: max(pool, key=lambda e: e.difficulty_level))

    picked = await service._pick_single(
        TrainingPhase.WARMUP, ExerciseCategory.OFF_ICE, user, BlockPhase.ACCUMULATION
    )

    assert picked is not None
    assert picked.name == "Easy-warmup"
