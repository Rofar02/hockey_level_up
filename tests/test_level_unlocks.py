"""app.core.level_unlocks -- pure functions, no DB needed. Boundary values
matter more than exhaustive coverage here, same style as
test_stat_difficulty_gate.py's band checks.
"""
from app.core.level_unlocks import (
    LEVEL_AVATAR_RING_CHOICE,
    LEVEL_JERSEY_COLOR_CHOICE,
    SKILL_SLOT_CAP,
    has_avatar_ring_choice,
    has_jersey_color_choice,
    max_skill_slots_for_level,
)


def test_skill_slot_tiers_at_their_boundaries() -> None:
    assert max_skill_slots_for_level(1) == 3
    assert max_skill_slots_for_level(4) == 3
    assert max_skill_slots_for_level(5) == 4
    assert max_skill_slots_for_level(9) == 4
    assert max_skill_slots_for_level(10) == 5
    assert max_skill_slots_for_level(14) == 5
    assert max_skill_slots_for_level(15) == 6


def test_skill_slot_cap_never_grows_past_level_15() -> None:
    assert max_skill_slots_for_level(15) == SKILL_SLOT_CAP
    assert max_skill_slots_for_level(999) == SKILL_SLOT_CAP


def test_avatar_ring_choice_unlocks_at_its_level() -> None:
    assert has_avatar_ring_choice(LEVEL_AVATAR_RING_CHOICE - 1) is False
    assert has_avatar_ring_choice(LEVEL_AVATAR_RING_CHOICE) is True
    assert has_avatar_ring_choice(LEVEL_AVATAR_RING_CHOICE + 1) is True


def test_jersey_color_choice_unlocks_at_its_level() -> None:
    assert has_jersey_color_choice(LEVEL_JERSEY_COLOR_CHOICE - 1) is False
    assert has_jersey_color_choice(LEVEL_JERSEY_COLOR_CHOICE) is True
