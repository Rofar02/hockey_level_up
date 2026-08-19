"""Off-ice exercise difficulty gated by measured physical characteristics
(UserStat), not by User.level/XP (2026-08-18 planning session).

Why the split exists: User.level/xp tracks engagement -- it grows from
completing *any* SessionBlock regardless of how physically capable the
person actually is (see app.events.handlers.block_completed.xp_consumer,
gain = difficulty_level * 10 flat, no relation to real fitness). UserStat
tracks measured capability -- seeded by AssessmentService from an actual
strength/agility/endurance test, and grown by
app.events.handlers.block_completed.stat_consumer's own, separate formula.
Gating exercise difficulty on level let a highly-leveled-but-weak account
into heavy barbell work, and left a strong-but-freshly-registered account
stuck on push-ups until it ground out XP unrelated to strength. Gating on
the exercise's own primary characteristic instead ties eligibility to the
one thing that actually predicts injury risk.

On-ice exercises are NOT covered by this module -- ScheduleService still
gates them with app.core.training_block.max_difficulty_for_level, on
purpose, pending a separate pass at the on-ice assessment/stat pipeline
(2026-08-18: "про лёд забудь пока что").
"""
from app.core.training_block import MAX_DIFFICULTY_LEVEL

# (stat_value_upper_bound, cap) pairs, ascending -- the first row whose
# upper bound is > the user's effective value for that exercise's primary
# characteristic wins. Five bands for five difficulty levels: a 0-100
# characteristic splits evenly into exactly as many tiers as
# Exercise.difficulty_level has values, so raising a stat one band
# unlocks exactly the next difficulty rung, no smoothing/rounding needed.
_STAT_DIFFICULTY_BANDS: list[tuple[float, int]] = [
    (20.0, 1),
    (40.0, 2),
    (60.0, 3),
    (80.0, 4),
]  # stat >= 80 -> MAX_DIFFICULTY_LEVEL (5), no cap


def max_difficulty_for_stat(stat_value: float) -> int:
    for upper_bound, cap in _STAT_DIFFICULTY_BANDS:
        if stat_value < upper_bound:
            return cap
    return MAX_DIFFICULTY_LEVEL


# An off-ice exercise with no primary (order=0) ExerciseTargetStat row yet
# can't be matched to any characteristic at all -- treated as the most
# conservative band rather than let unclassified catalog gaps quietly
# bypass the gate. Same "NULL means not yet classified, never a free
# pass" contract as stimulus_type/exercise_type/warmup_stage.
UNCLASSIFIED_EXERCISE_CAP = 1
