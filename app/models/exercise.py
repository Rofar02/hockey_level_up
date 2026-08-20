import enum
import uuid
from datetime import date

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enum_column import enum_column


class ExerciseCategory(enum.StrEnum):
    ON_ICE = "on_ice"
    OFF_ICE = "off_ice"


class TrainingPhase(enum.StrEnum):
    WARMUP = "warmup"
    MAIN = "main"
    COOLDOWN = "cooldown"


class TargetStat(enum.StrEnum):
    STRENGTH = "strength"
    AGILITY = "agility"
    INTELLECT = "intellect"
    ENDURANCE = "endurance"
    # On-ice-only stats, calibrated from a separate on-ice test rather than
    # the off-ice fitness assessment (see AssessmentService) -- longer decay
    # grace period in stat_service.GRACE_PERIOD_DAYS_BY_STAT since on-ice
    # sessions happen less often than off-ice training.
    ON_ICE_SKATING = "on_ice_skating"
    PUCK_HANDLING = "puck_handling"


class EquipmentItem(enum.StrEnum):
    """Stage 2.2 (2026-08-20 planning session) -- replaced the old
    gym/home/bodyweight tier on both Exercise and User. An exercise now
    requires a *set* of specific items (see ExerciseEquipmentItem, e.g.
    step platform + dumbbells for a step-up) instead of one coarse tier,
    and a user owns a set of specific items (see UserEquipmentItem)
    instead of picking a tier. Deliberately no equivalence grouping --
    kettlebell/dumbbells/barbell are NOT interchangeable for matching,
    they're different exercises technique-wise; tagging is always to the
    concrete item actually required. Closed list, extend as the catalog
    needs new items -- not meant to be exhaustive of every possible piece
    of equipment on day one.
    """

    KETTLEBELL = "kettlebell"
    DUMBBELLS = "dumbbells"
    BARBELL = "barbell"
    RESISTANCE_BAND = "resistance_band"
    PULL_UP_BAR = "pull_up_bar"
    JUMP_ROPE = "jump_rope"
    FOAM_ROLLER = "foam_roller"
    STEP_PLATFORM = "step_platform"
    SLIDE_BOARD = "slide_board"
    MEDICINE_BALL = "medicine_ball"
    # Stage 2.6 (2026-08-20 planning session): the "add external load"
    # lever for a tracks_weight=false bodyweight exercise -- tag an
    # exercise as requiring this item, flip tracks_weight to true and set
    # bodyweight_ratio, and the existing double-progression machinery
    # (WeightSuggestionService/RepsSuggestionService) just works unmodified.
    # No DB migration needed to add this value: EquipmentItem is a
    # VARCHAR-backed enum (see app/db/enum_column.py), not a native
    # Postgres enum type, and nothing CHECK-constrains it to a fixed list.
    WEIGHTED_VEST = "weighted_vest"


class MuscleGroup(enum.StrEnum):
    """Anatomical taxonomy (Stage 2.1, 2026-08-20 planning session) --
    replaced the old push/pull/legs/core grouping, which couldn't tell a
    squat from a lunge apart (both "legs") even though they load different
    muscles. See ExerciseMuscleGroup for how an exercise attaches to these
    (a weighted list, not one value)."""

    QUADS = "quads"
    HAMSTRINGS = "hamstrings"
    GLUTES = "glutes"
    CHEST = "chest"
    BACK = "back"
    SHOULDERS = "shoulders"
    CORE = "core"
    CALVES = "calves"


class StimulusType(enum.StrEnum):
    STRENGTH = "strength"
    POWER = "power"
    ENDURANCE = "endurance"
    SKILL = "skill"
    MOBILITY = "mobility"


class WarmupStage(enum.StrEnum):
    """Which stage of a proper warmup a WARMUP-phase exercise belongs to
    (RAMP protocol: Raise-Activate-Mobilize-Potentiate, reordered to match
    how the product actually sequences it -- soft tissue prep first, then
    raise, joints, activation, sport-specific dynamic movement last).
    NULL for every non-WARMUP exercise, and for WARMUP rows not yet
    classified -- see scripts/backfill_warmup_stages.py.

    SOFT_TISSUE is the only stage with zero bodyweight-tier exercises in
    the catalog (foam roller/ball work inherently needs a tool) -- that's
    accepted as the one stage that's simply absent for a bodyweight-only
    user's warmup complex, not something patched around, since raise/
    joint_mobility/activation/dynamic all have bodyweight coverage.
    """

    SOFT_TISSUE = "soft_tissue"
    RAISE = "raise"
    JOINT_MOBILITY = "joint_mobility"
    ACTIVATION = "activation"
    DYNAMIC = "dynamic"


WARMUP_STAGE_ORDER: tuple[WarmupStage, ...] = (
    WarmupStage.SOFT_TISSUE,
    WarmupStage.RAISE,
    WarmupStage.JOINT_MOBILITY,
    WarmupStage.ACTIVATION,
    WarmupStage.DYNAMIC,
)


class ExerciseType(enum.StrEnum):
    SETS_REPS = "sets_reps"
    DURATION = "duration"


class MovementPattern(enum.StrEnum):
    HIP_HINGE = "hip_hinge"
    SQUAT = "squat"
    PUSH = "push"
    PULL = "pull"
    ROTATION = "rotation"
    ANKLE_MOBILITY = "ankle_mobility"
    HIP_MOBILITY = "hip_mobility"
    SHOULDER_MOBILITY = "shoulder_mobility"
    WRIST_MOBILITY = "wrist_mobility"
    CORE = "core"
    LOCOMOTION = "locomotion"
    # 2026-08-19: added for the handful of catalog exercises that are
    # neither a strength/mobility movement nor without a slot at all --
    # stick-skill drills (mirrors the "Обводка" skill) and general
    # coordination/reaction/balance work (mirrors "Координация и реакция" --
    # balance is folded in here rather than getting its own pattern, since
    # this axis only needs to be as coarse as MAIN diversity/warmup-cooldown
    # matching require, not as fine-grained as skill_tags, which still track
    # balance as its own separate skill).
    STICK_HANDLING = "stick_handling"
    COORDINATION = "coordination"


class Exercise(Base):
    __tablename__ = "exercises"
    __table_args__ = (
        CheckConstraint(
            "difficulty_level >= 1 AND difficulty_level <= 5", name="ck_exercises_difficulty_level"
        ),
        # enum_column() builds a VARCHAR-backed Enum with native_enum=False
        # and no create_constraint=True, so nothing at the DB level stops an
        # invalid string landing in exercise_type outside the app layer
        # (raw SQL, a bad migration, a bulk import). NULL still passes --
        # Postgres CHECK only fails on FALSE, never on NULL -- so this
        # doesn't need its own "OR exercise_type IS NULL" clause.
        CheckConstraint(
            "exercise_type IN ('sets_reps', 'duration')", name="ck_exercises_exercise_type"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    category: Mapped[ExerciseCategory] = mapped_column(
        enum_column(ExerciseCategory, "exercise_category"), nullable=False
    )
    phase: Mapped[TrainingPhase] = mapped_column(
        enum_column(TrainingPhase, "training_phase"), nullable=False
    )
    difficulty_level: Mapped[int] = mapped_column(Integer, nullable=False)

    video_source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    video_source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    target_sets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # A range, not a single number (Phase: double progression) -- reps
    # personalize within [min, max] per session based on performance (see
    # RepsSuggestionService); target_sets above stays a static catalog value,
    # sets-count personalization is a separate, harder topic, not this one.
    rep_range_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rep_range_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Both nullable and unset on nearly every existing exercise -- NULL means
    # "not yet classified", not a default value. Real classification is a
    # manual product-owner pass (like suitable_for_game_day),
    # not inferred here. stimulus_type feeds a future rest-time formula;
    # exercise_type will eventually replace the implicit sets/reps-vs-
    # duration discriminator below, but no CHECK constraint ties them
    # together yet -- most rows have neither target_sets/rep_range_min/
    # rep_range_max nor target_duration_seconds set, so such a constraint
    # isn't satisfiable until real volume data is backfilled.
    stimulus_type: Mapped[StimulusType | None] = mapped_column(
        enum_column(StimulusType, "stimulus_type"), nullable=True
    )
    exercise_type: Mapped[ExerciseType | None] = mapped_column(
        enum_column(ExerciseType, "exercise_type"), nullable=True
    )

    # Which stage of a proper warmup this belongs to -- see WarmupStage.
    # NULL for every non-WARMUP exercise (meaningless there) and for WARMUP
    # rows not yet classified, same "NULL means not yet classified" contract
    # as stimulus_type/exercise_type above.
    warmup_stage: Mapped[WarmupStage | None] = mapped_column(
        enum_column(WarmupStage, "warmup_stage"), nullable=True
    )

    # Whether this exercise has a working weight at all (barbell/dumbbell/
    # machine work) -- gates both the weight-suggestion service and whether
    # SetCompletion rows for it are expected to carry weight_kg.
    tracks_weight: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    # Working weight as a multiple of bodyweight (e.g. 0.5 for a goblet squat
    # around half bodyweight) -- only meaningful, and only ever populated,
    # when tracks_weight is true. Used by WeightSuggestionService for the
    # first-ever suggestion before any SetCompletion history exists.
    bodyweight_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Whether this exercise is light enough to be pre-game activation, not a
    # full warmup (e.g. not loaded barbell work) -- gates
    # ScheduleService._build_game_day_session's physical-activation pick,
    # on top of phase=WARMUP. Defaults false for every existing exercise on
    # purpose: this isn't inferred from name/category, someone has to
    # actually mark exercises suitable one at a time via the admin panel.
    suitable_for_game_day: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    # Stage 2.4 (2026-08-20 planning session): bilateral (both legs at
    # once, e.g. a barbell squat) vs unilateral (one leg, e.g. a Bulgarian
    # split squat) load -- only meaningful for squat/hip_hinge exercises,
    # NULL ("not yet classified") everywhere else, same contract as
    # stimulus_type/warmup_stage above. Skating is an inherently
    # unilateral push, so ScheduleService's lower-body strength role
    # prefers unilateral candidates when both are available in the
    # surviving pool -- a soft tie-break, not a hard filter, since most of
    # the catalog isn't classified yet.
    is_unilateral: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


# Bare m2m tag, unlike SkillTag -- no per-pair metadata is needed, so this is
# a plain association table (no relationship() on Exercise, consistent with
# how SkillTag is accessed: explicit select()s via the repository, not ORM
# collection traversal) managed as a full-replace set, not one-row CRUD.
class ExerciseMovementPattern(Base):
    __tablename__ = "exercise_movement_patterns"
    __table_args__ = (
        UniqueConstraint(
            "exercise_id", "movement_pattern", name="uq_exercise_movement_patterns_exercise_pattern"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False, index=True
    )
    movement_pattern: Mapped[MovementPattern] = mapped_column(
        enum_column(MovementPattern, "movement_pattern"), nullable=False
    )


# Bare m2m tag, unlike ExerciseMuscleGroup -- no weight, just "this specific
# item is required". Membership semantics for eligibility are AND across the
# whole set, not OR: ExerciseRepository.list_for_assembly only shows an
# exercise to a non-gym user if *every* row here is also in that user's own
# UserEquipmentItem rows (subset check), matching a step-up genuinely
# needing both a step platform AND dumbbells at once, not either one. Zero
# rows means bodyweight-only -- always eligible regardless of inventory,
# the natural floor case, not a category of its own (Stage 2.2, 2026-08-20
# planning session).
class ExerciseEquipmentItem(Base):
    __tablename__ = "exercise_equipment_items"
    __table_args__ = (
        UniqueConstraint(
            "exercise_id", "equipment_item", name="uq_exercise_equipment_items_exercise_item"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False, index=True
    )
    equipment_item: Mapped[EquipmentItem] = mapped_column(
        enum_column(EquipmentItem, "equipment_item"), nullable=False
    )


# Weighted list, not one value (Stage 2.1) -- same shape as SkillStatWeight:
# a per-exercise set of (muscle_group, weight) rows whose weights sum to
# ~1.0, validated in ExerciseService (see skill_service._validate_weight_sum
# for the precedent), not by a DB CHECK, since "sum across sibling rows"
# isn't expressible as one. An exercise with zero rows here means "not yet
# classified" (on_ice drills, off_ice cardio/mental work, or simply not
# retagged yet under the new taxonomy) -- same "absent means not applicable"
# contract as ExerciseMovementPattern. ScheduleService._apply_muscle_balance
# reads presence (is this muscle_group anywhere in the exercise's rows),
# never the weight value itself -- an explicit simplification, not an
# oversight; weight exists for future finer-grained use (see the planning
# doc's muscle-load-heatmap backlog item), not for this validator.
class ExerciseMuscleGroup(Base):
    __tablename__ = "exercise_muscle_groups"
    __table_args__ = (
        UniqueConstraint(
            "exercise_id", "muscle_group", name="uq_exercise_muscle_groups_exercise_group"
        ),
        CheckConstraint(
            "weight >= 0.0 AND weight <= 1.0", name="ck_exercise_muscle_groups_weight_range"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False, index=True
    )
    muscle_group: Mapped[MuscleGroup] = mapped_column(
        enum_column(MuscleGroup, "muscle_group"), nullable=False
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False)


# Also a plain association table (no relationship() on Exercise), but unlike
# ExerciseMovementPattern this one needs an explicit order: order=0 is the
# exercise's "primary" stat, which ScheduleService._pick_main/
# suggest_party_exercises bucket on for diversity -- relying on whatever row
# order Postgres happens to return would repeat the SessionBlock.order=0
# collision bug found across training phases. Reward-splitting (stat_consumer)
# reads every row for an exercise, not just order=0.
class ExerciseTargetStat(Base):
    __tablename__ = "exercise_target_stats"
    __table_args__ = (
        UniqueConstraint(
            "exercise_id", "target_stat", name="uq_exercise_target_stats_exercise_stat"
        ),
        UniqueConstraint("exercise_id", "order", name="uq_exercise_target_stats_exercise_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_stat: Mapped[TargetStat] = mapped_column(
        enum_column(TargetStat, "target_stat"), nullable=False
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False)


class UserMovementPatternVariant(Base):
    """Phase: П.3 variant rotation, extended by Stage 2.4's day-archetype
    system. One row per (user, category, pattern, archetype) -- the
    exercise ScheduleService._pick_main currently holds stable for this
    combination, the block_number it was last confirmed/rotated at, and
    (Stage 2.4) the date it was last actually assembled into a session.
    Held constant across sessions within the same TrainingBlock; rotated to
    a fresh candidate at the boundary of a new (non-macrocycle-deload)
    block; held through a macrocycle-deload block's boundary instead of
    rotating (see is_macrocycle_deload_block) -- only block_number bumps in
    that case, exercise_id stays. No relationship()s, same convention as
    ExerciseMovementPattern/UserSkillPreference -- accessed only through
    UserMovementPatternVariantRepository.

    category is part of the key, not just movement_pattern, because
    movement_pattern=locomotion is tagged on both on_ice and off_ice
    exercises -- one pin per pattern alone would collide between an
    on-ice and an off-ice session.

    archetype is NULL for every pattern outside
    app.core.day_archetype.ARCHETYPE_ELIGIBLE_PATTERNS (squat/hip_hinge/
    push/pull) -- exactly one row per pattern there, identical to the
    pre-2.4 shape. For an eligible pattern there can be up to three rows
    (one per StimulusType.STRENGTH/POWER/SKILL "day archetype"), each its
    own independent rotation line -- see app.core.day_archetype for the
    "hasn't happened in the longest time" selection rule that reads
    last_chosen_at across a pattern's rows before this table's own
    per-archetype pin stability even applies.
    """

    __tablename__ = "user_movement_pattern_variants"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "category", "movement_pattern", "archetype",
            name="uq_ump_variants_user_category_pattern_archetype",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[ExerciseCategory] = mapped_column(
        enum_column(ExerciseCategory, "exercise_category"), nullable=False
    )
    movement_pattern: Mapped[MovementPattern] = mapped_column(
        enum_column(MovementPattern, "movement_pattern"), nullable=False
    )
    # StimulusType reused rather than a parallel enum -- "day archetype"
    # for squat/hip_hinge/push/pull is exactly strength/power/skill, the
    # same axis exercises are already classified on (see
    # app.core.day_archetype.DAY_ARCHETYPES). NULL for every pattern
    # outside ARCHETYPE_ELIGIBLE_PATTERNS.
    archetype: Mapped[StimulusType | None] = mapped_column(
        enum_column(StimulusType, "stimulus_type"), nullable=True
    )
    # No ondelete restriction unlike SetCompletion.exercise_id -- this is
    # ephemeral pointer state with no history value, deleting the pinned
    # exercise should just clear the pin (next pick creates a fresh one),
    # not fail loudly.
    exercise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Which TrainingBlock.block_number this pin was last set/confirmed at --
    # the versioning mechanism for "has a block boundary passed since this
    # was pinned", not a real training_blocks FK (a block_number is only
    # unique per-user, and blocks are frequently created/retired).
    block_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Stage 2.4: last calendar date this (pattern, archetype) was actually
    # assembled into a session -- NULL means never. Drives the "hasn't
    # happened in the longest time" rotation rule; only bumped when the
    # exercise actually picked genuinely matched this archetype's
    # stimulus_type (a fallback to the full pattern pool, e.g. because the
    # catalog has no SKILL-classified squat yet, leaves this untouched, so
    # an unsatisfied archetype honestly keeps looking rather than being
    # marked done by a pick that wasn't really it).
    last_chosen_at: Mapped[date | None] = mapped_column(Date, nullable=True)


# Stage 2.2: replaces User.equipment_access's old gym/home/bodyweight tier.
# The user's own concrete item inventory -- "Свой инвентарь" in the profile/
# onboarding grid (Stage 2.3), checked against ExerciseEquipmentItem's
# per-exercise requirement set. No rows at all is the natural "bodyweight
# only" floor, not a separate category. Meaningless (never queried) for a
# user with has_gym_access=True, who bypasses the equipment filter entirely
# -- see ExerciseRepository.list_for_assembly.
class UserEquipmentItem(Base):
    __tablename__ = "user_equipment_items"
    __table_args__ = (
        UniqueConstraint("user_id", "equipment_item", name="uq_user_equipment_items_user_item"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    equipment_item: Mapped[EquipmentItem] = mapped_column(
        enum_column(EquipmentItem, "equipment_item"), nullable=False
    )
