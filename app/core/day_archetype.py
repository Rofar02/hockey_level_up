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
# squat/hip_hinge/push/pull have a genuine strength/power spread in real
# S&C programming; *_mobility patterns physiologically don't (see the
# planning doc). Every other pattern (rotation/core/locomotion/
# stick_handling/coordination) keeps the pre-2.4 single-pin behavior,
# except for ROTATING_PATTERNS below (2026-09-17 fix), which gets a
# simpler same-variant session cap instead of the archetype split.
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

# 2026-09-17 fix (audit item #1): SKILL as a squat/hip_hinge "day
# archetype" reflects a real different hockey-relevant skill (e.g. pistol
# squat vs barbell squat). A gym push/pull has no equivalent -- the real
# technical skill for a shot/contact is on the ice, not in the weight
# room -- and the catalog has zero push/skill and pull/skill candidates
# for exactly that reason (checked against the real catalog, see the
# audit doc). Per-pattern archetype set so push/pull only ever rotate
# strength/power, never fall back into an empty skill pool.
PATTERN_ARCHETYPES: dict[MovementPattern, tuple[StimulusType, ...]] = {
    MovementPattern.SQUAT: DAY_ARCHETYPES,
    MovementPattern.HIP_HINGE: DAY_ARCHETYPES,
    MovementPattern.PUSH: (StimulusType.STRENGTH, StimulusType.POWER),
    MovementPattern.PULL: (StimulusType.STRENGTH, StimulusType.POWER),
}

# First-ever pick for a pattern (no rotation history at all yet) starts
# here -- resolved decision, 2026-08-20: accumulation is the base-building
# phase, strength is the matching character; "hasn't happened in a while"
# takes over from the second session on for that pattern.
DEFAULT_FIRST_ARCHETYPE = StimulusType.STRENGTH

# 2026-09-17 fix (audit item #1): the 7 non-archetype-eligible patterns
# were pinned to one variant for the whole training block (up to
# PHASE_CALENDAR_CEILING_WEEKS) -- the direct cause of "same exercise for
# weeks" complaints. Catalog audit confirmed these 4 patterns have enough
# distinct candidates across every equipment tier to support real
# rotation; *_mobility and stick_handling are WARMUP content and are
# deliberately left untouched (not in scope for MAIN-block repetition).
# A full 3-archetype split doesn't fit these patterns semantically (no
# strength/power/skill distinction the way squat does), so instead of
# reusing that machinery they get a simpler cap: the same pinned variant
# is allowed for at most ROTATION_SESSION_LIMIT genuine picks in a row,
# then _pick_main forces a fresh candidate even within the same block.
ROTATING_PATTERNS: frozenset[MovementPattern] = frozenset(
    {
        MovementPattern.LOCOMOTION,
        MovementPattern.CORE,
        MovementPattern.COORDINATION,
        MovementPattern.ROTATION,
    }
)

ROTATION_SESSION_LIMIT = 3


def choose_archetype(
    last_chosen_at: dict[StimulusType, date | None],
    candidates: tuple[StimulusType, ...] = DAY_ARCHETYPES,
) -> StimulusType:
    """"Hasn't happened in the longest time" wins. An archetype with no
    entry at all in `last_chosen_at` (never genuinely trained -- see
    UserMovementPatternVariant.last_chosen_at's docstring on what "genuine"
    means here) outranks any archetype that has a real date, and among
    dated archetypes the oldest date wins.

    The one exception, resolved decision 2026-08-20: if literally none of
    `candidates` has ever been chosen (this pattern's very first-ever
    pick), skip the "untried beats tried" comparison -- there's nothing to
    prefer between equally-untried options -- and start at
    DEFAULT_FIRST_ARCHETYPE outright instead of an arbitrary/enum-order
    tie-break (falling back to candidates[0] if DEFAULT_FIRST_ARCHETYPE
    itself isn't one of this pattern's candidates, e.g. push/pull).

    `candidates` defaults to the full three-way split (DAY_ARCHETYPES) for
    the SQUAT/HIP_HINGE call sites and direct callers; PUSH/PULL pass
    PATTERN_ARCHETYPES[pattern] explicitly instead (see that dict's
    docstring for why they're excluded from SKILL).
    """
    if all(last_chosen_at.get(archetype) is None for archetype in candidates):
        return DEFAULT_FIRST_ARCHETYPE if DEFAULT_FIRST_ARCHETYPE in candidates else candidates[0]
    return min(
        candidates,
        key=lambda archetype: (
            last_chosen_at.get(archetype) is not None,
            last_chosen_at.get(archetype) or date.min,
        ),
    )


def initial_rotation_order(
    last_chosen_at: dict[StimulusType, date | None],
    candidates: tuple[StimulusType, ...] = DAY_ARCHETYPES,
) -> list[StimulusType]:
    """Same "hasn't happened in the longest time wins" comparison as
    choose_archetype, but returns the full stale-to-fresh order instead of
    just the winner. Meant to be computed ONCE per pattern before building
    a whole batch of days (a real week, always built in one request -- see
    ScheduleService.create_weekly_plan/_patch_weekly_plan), then consumed
    round-robin across that batch's days -- rather than calling
    choose_archetype fresh against live state after each day.

    Re-deriving live within the same batch creates a real monopoly: the
    archetype that wins day 1 gets its own last_chosen_at bumped to day
    1's date, while the untouched runners-up still sit at whatever older
    date they already had. Day 2 compares day-1's winner (now dated day 1)
    against the runners-up (still older) -- day-1's winner is *still* the
    "most stale" and wins again, advancing one calendar day at a time
    while the runners-up stand still, so it can take several days to
    finally close the gap. A fixed order decided once, then cycled,
    can't run away like that.

    See choose_archetype for what `candidates` is and why PUSH/PULL pass a
    narrower set than SQUAT/HIP_HINGE.
    """
    if all(last_chosen_at.get(archetype) is None for archetype in candidates):
        default = DEFAULT_FIRST_ARCHETYPE if DEFAULT_FIRST_ARCHETYPE in candidates else candidates[0]
        rest = [a for a in candidates if a != default]
        return [default, *rest]
    return sorted(
        candidates,
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
