"""Cap on how many UserSkillPreference rows a user can have selected at
once, scaled by User.level -- same tiered-threshold pattern as
max_difficulty_for_level (app/core/training_block.py), kept in its own
module since this is a different piece of game balance (skill-picker cap,
not exercise difficulty selection).
"""

# (level_threshold, cap) pairs, ascending on the threshold; the first row
# whose threshold is > level wins. Edit this list to retune the cap --
# nothing else needs to change.
_SKILL_PREFERENCE_CAPS: list[tuple[int, int]] = [
    (8, 3),  # level < 8        -> max 3
    (15, 6),  # 8 <= level < 15  -> max 6
    (25, 9),  # 15 <= level < 25 -> max 9
]  # level >= 25 -> unlimited (None)


def max_skill_preferences_for_level(level: int) -> int | None:
    """None means unlimited -- unlike max_difficulty_for_level (which has a
    hard ceiling at MAX_DIFFICULTY_LEVEL), there's genuinely no cap past
    the last tier here."""
    for threshold, cap in _SKILL_PREFERENCE_CAPS:
        if level < threshold:
            return cap
    return None
