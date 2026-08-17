import enum
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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


class EquipmentType(enum.StrEnum):
    GYM = "gym"
    HOME = "home"
    BODYWEIGHT = "bodyweight"


class MuscleGroup(enum.StrEnum):
    PUSH = "push"
    PULL = "pull"
    LEGS = "legs"
    CORE = "core"


class StimulusType(enum.StrEnum):
    STRENGTH = "strength"
    POWER = "power"
    ENDURANCE = "endurance"
    SKILL = "skill"
    MOBILITY = "mobility"


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
    equipment_type: Mapped[EquipmentType] = mapped_column(
        enum_column(EquipmentType, "equipment_type"), nullable=False
    )

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

    # Anatomical push/pull/legs/core grouping, used only to softly balance
    # ScheduleService._pick_main's off_ice picks (see MAIN_EXERCISE_COUNT_RANGE
    # for the count side of that same picker). Nullable and left unset for
    # on_ice exercises (technique/shooting/tactics drills aren't isolated-
    # muscle-group work) and for off_ice exercises that don't fit any of the
    # four groups (cardio, mental) -- None always means "not applicable",
    # never a random/default group.
    muscle_group: Mapped[MuscleGroup | None] = mapped_column(
        enum_column(MuscleGroup, "muscle_group"), nullable=True
    )

    # Both nullable and unset on nearly every existing exercise -- NULL means
    # "not yet classified", not a default value. Real classification is a
    # manual product-owner pass (like muscle_group/suitable_for_game_day),
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
