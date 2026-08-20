"""Stage 2.4 (2026-08-20 planning session): day-archetype rotation for
squat/hip_hinge/push/pull -- three parallel progression lines per pattern
(strength/power/skill, reusing StimulusType rather than inventing a new
enum -- see UserMovementPatternVariant's docstring) instead of the single
pinned variant every other movement_pattern still gets. Pure decision
rules only, no DB access -- the DB-querying/mutating side lives in
ScheduleService._pick_main.
"""
from datetime import date

from app.core.training_block import MAIN_EXERCISE_COUNT_RANGE, main_exercise_count_range
from app.models.exercise import ExerciseCategory, MovementPattern, StimulusType
from app.models.schedule import BlockPhase
from app.models.user import SeasonPeriod

# Which movement patterns support the three-archetype split at all --
# squat/hip_hinge/push/pull have a genuine strength/power/skill spread in
# real S&C programming (barbell squat vs jump squat vs pistol squat);
# *_mobility patterns physiologically don't (see the planning doc). Every
# other pattern (rotation/core/locomotion/stick_handling/coordination)
# keeps the pre-2.4 single-pin behavior untouched.
ARCHETYPE_ELIGIBLE_PATTERNS: frozenset[MovementPattern] = frozenset(
    {
        MovementPattern.SQUAT,
        MovementPattern.HIP_HINGE,
        MovementPattern.PUSH,
        MovementPattern.PULL,
    }
)

DAY_ARCHETYPES: tuple[StimulusType, ...] = (
    StimulusType.STRENGTH,
    StimulusType.POWER,
    StimulusType.SKILL,
)

# First-ever pick for a pattern (no rotation history at all yet) starts
# here -- resolved decision, 2026-08-20: accumulation is the base-building
# phase, strength is the matching character; "hasn't happened in a while"
# takes over from the second session on for that pattern.
DEFAULT_FIRST_ARCHETYPE = StimulusType.STRENGTH


def choose_archetype(last_chosen_at: dict[StimulusType, date | None]) -> StimulusType:
    """"Hasn't happened in the longest time" wins. An archetype with no
    entry at all in `last_chosen_at` (never genuinely trained -- see
    UserMovementPatternVariant.last_chosen_at's docstring on what "genuine"
    means here) outranks any archetype that has a real date, and among
    dated archetypes the oldest date wins.

    The one exception, resolved decision 2026-08-20: if literally none of
    the three has ever been chosen (this pattern's very first-ever pick),
    skip the "untried beats tried" comparison -- there's nothing to prefer
    between three equally-untried options -- and start at
    DEFAULT_FIRST_ARCHETYPE outright instead of an arbitrary/enum-order
    tie-break.
    """
    if all(last_chosen_at.get(archetype) is None for archetype in DAY_ARCHETYPES):
        return DEFAULT_FIRST_ARCHETYPE
    return min(
        DAY_ARCHETYPES,
        key=lambda archetype: (
            last_chosen_at.get(archetype) is not None,
            last_chosen_at.get(archetype) or date.min,
        ),
    )


def forces_technical_archetype(
    block_phase: BlockPhase,
    *,
    category: ExerciseCategory,
    season_period: SeasonPeriod,
    is_tapering: bool = False,
    is_final_taper_week: bool = False,
) -> bool:
    """Resolved decision, 2026-08-20: whenever this session's MAIN volume
    has already collapsed to deload's own count range -- a real deload
    phase, a tactical-brake-forced one (OverloadService.apply_brakes
    already forces block_phase itself to DELOAD before _pick_main ever
    sees it, so that case falls out of this check for free), the final
    taper week, or playoffs -- the archetype rotation for
    ARCHETYPE_ELIGIBLE_PATTERNS is overridden outright to SKILL
    (technical/light), without consulting choose_archetype at all.

    Reuses main_exercise_count_range's own resolution cascade (taper ->
    playoffs -> season -> base phase) instead of duplicating it, so the
    two can never drift out of sync -- "embedded in the existing
    volume-priority table", per the planning doc, not a parallel
    mechanism. Rotation state itself is untouched by an override taking
    effect: last_chosen_at is only ever bumped by a genuine (non-override)
    pick, so the interrupted archetype resumes exactly where it left off
    once the override stops applying.
    """
    resolved_range = main_exercise_count_range(
        block_phase,
        category=category,
        season_period=season_period,
        is_tapering=is_tapering,
        is_final_taper_week=is_final_taper_week,
    )
    return resolved_range == MAIN_EXERCISE_COUNT_RANGE[BlockPhase.DELOAD]
