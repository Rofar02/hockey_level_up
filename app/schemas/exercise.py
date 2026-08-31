import uuid

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.core.rest import rest_seconds_for
from app.models.exercise import (
    EquipmentItem,
    Exercise,
    ExerciseCategory,
    ExerciseType,
    MovementPattern,
    MuscleGroup,
    StimulusType,
    TargetStat,
    TrainingPhase,
    WarmupStage,
)


class ExerciseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    category: ExerciseCategory
    phase: TrainingPhase
    # Not a passthrough model attribute (Exercise has no target_stat column
    # or relationship() -- see ExerciseTargetStat) -- always supplied
    # explicitly by the service layer from a bulk ExerciseTargetStat query,
    # never auto-populated by from_attributes. Order matches ExerciseTargetStat.order;
    # index 0 is the "primary" stat ScheduleService buckets on for diversity.
    target_stats: list[TargetStat]
    difficulty_level: int = Field(ge=1, le=5)
    video_source_type: str | None
    video_source_id: str | None
    target_sets: int | None
    rep_range_min: int | None
    rep_range_max: int | None
    target_duration_seconds: int | None
    tracks_weight: bool
    bodyweight_ratio: float | None
    suitable_for_game_day: bool
    # Stage 2.4: bilateral vs unilateral load, meaningful only for squat/
    # hip_hinge exercises -- NULL means not yet classified, same contract
    # as stimulus_type. See ScheduleService._pick_main's role 2.
    is_unilateral: bool | None
    stimulus_type: StimulusType | None
    exercise_type: ExerciseType | None
    # Which of the 5 warmup stages this belongs to (see WarmupStage) --
    # meaningless outside phase=WARMUP, but not enforced null elsewhere at
    # the schema level, same "NULL means not yet classified" contract as
    # stimulus_type/exercise_type above. ScheduleService._pick_warmup_complex
    # never selects a WARMUP exercise with this unset -- see the admin form's
    # own warning copy.
    warmup_stage: WarmupStage | None
    # Admin-only checklist flag (see Exercise.admin_reviewed) -- no gameplay
    # meaning, just lets the admin panel filter out exercises already gone
    # over while working through the catalog.
    admin_reviewed: bool

    # Computed, not stored -- see app.core.rest. Derived from stimulus_type
    # and difficulty_level (None only when stimulus_type is unclassified),
    # exposed here so every client reads the same rest suggestion without
    # reimplementing the stimulus_type/difficulty formula.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def rest_seconds(self) -> int | None:
        return rest_seconds_for(self.stimulus_type, self.difficulty_level)


# Every ExerciseRead must be built through here (or exercises_to_read for a
# batch), not ExerciseRead.model_validate(exercise) -- target_stats isn't a
# passthrough model attribute (see the field's docstring above), so
# from_attributes alone can't populate it. Callers fetch target_stats
# themselves (single via ExerciseRepository.list_target_stats, batch via
# list_target_stats_by_exercise) so this stays a pure function with no
# repository/session dependency of its own.
def exercise_to_read(exercise: Exercise, target_stats: list[TargetStat]) -> ExerciseRead:
    return ExerciseRead(
        id=exercise.id,
        name=exercise.name,
        description=exercise.description,
        category=exercise.category,
        phase=exercise.phase,
        target_stats=target_stats,
        difficulty_level=exercise.difficulty_level,
        video_source_type=exercise.video_source_type,
        video_source_id=exercise.video_source_id,
        target_sets=exercise.target_sets,
        rep_range_min=exercise.rep_range_min,
        rep_range_max=exercise.rep_range_max,
        target_duration_seconds=exercise.target_duration_seconds,
        tracks_weight=exercise.tracks_weight,
        bodyweight_ratio=exercise.bodyweight_ratio,
        suitable_for_game_day=exercise.suitable_for_game_day,
        is_unilateral=exercise.is_unilateral,
        stimulus_type=exercise.stimulus_type,
        exercise_type=exercise.exercise_type,
        warmup_stage=exercise.warmup_stage,
        admin_reviewed=exercise.admin_reviewed,
    )


def exercises_to_read(
    exercises: list[Exercise], target_stats_by_id: dict[uuid.UUID, list[TargetStat]]
) -> list[ExerciseRead]:
    return [exercise_to_read(e, target_stats_by_id.get(e.id, [])) for e in exercises]


class ExerciseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    category: ExerciseCategory
    phase: TrainingPhase
    difficulty_level: int = Field(ge=1, le=5)
    video_source_type: str | None = None
    video_source_id: str | None = None
    target_sets: int | None = None
    rep_range_min: int | None = None
    rep_range_max: int | None = None
    target_duration_seconds: int | None = None
    tracks_weight: bool = False
    bodyweight_ratio: float | None = Field(default=None, gt=0)
    suitable_for_game_day: bool = False
    is_unilateral: bool | None = None
    stimulus_type: StimulusType | None = None
    exercise_type: ExerciseType | None = None
    warmup_stage: WarmupStage | None = None


class ExerciseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    category: ExerciseCategory | None = None
    phase: TrainingPhase | None = None
    difficulty_level: int | None = Field(default=None, ge=1, le=5)
    video_source_type: str | None = None
    video_source_id: str | None = None
    target_sets: int | None = None
    rep_range_min: int | None = None
    rep_range_max: int | None = None
    target_duration_seconds: int | None = None
    tracks_weight: bool | None = None
    bodyweight_ratio: float | None = Field(default=None, gt=0)
    suitable_for_game_day: bool | None = None
    is_unilateral: bool | None = None
    stimulus_type: StimulusType | None = None
    exercise_type: ExerciseType | None = None
    warmup_stage: WarmupStage | None = None
    # Not exposed in the main admin form's save payload -- toggled through
    # its own dedicated button/request instead (see AdminExercisesPage's
    # setExerciseReviewed), so a routine content edit never accidentally
    # resets it.
    admin_reviewed: bool | None = None


class MovementPatternsReplace(BaseModel):
    movement_patterns: list[MovementPattern]


class EquipmentItemsReplace(BaseModel):
    equipment_items: list[EquipmentItem]


class ExerciseEquipmentRequirement(BaseModel):
    """One row per off_ice exercise -- Stage 2.3 (2026-08-20 planning
    session): bulk, non-admin-gated (see GET /exercises/equipment-
    requirements) so the onboarding/profile inventory screen can compute
    its live "unlocked N exercises" counter client-side, on every checkbox
    tap, with no per-tap network round trip. Deliberately off_ice-only
    (on_ice is never equipment-gated, see
    ExerciseRepository.list_for_assembly) so the counter's denominator
    only counts exercises that could actually change as the grid is
    edited."""

    exercise_id: uuid.UUID
    equipment_items: list[EquipmentItem]


class CatalogHealthIssue(BaseModel):
    """One row per exercise with at least one classification gap that
    causes it to silently drop out of (or wrongly stay eligible for)
    selection -- Stage 3 (2026-08-20 planning session), admin-gated (see
    GET /exercises/catalog-health), replacing manual SQL auditing as new
    classification axes (muscle groups, equipment) landed in Stage 2 and
    multiplied the ways an exercise can go quietly under-classified.

    `missing` values and exactly what each one means:
      - "primary_target_stat": no order=0 ExerciseTargetStat row. Off_ice
        only -- ScheduleService._apply_difficulty_gate treats this as
        app.core.stat_difficulty.UNCLASSIFIED_EXERCISE_CAP (1), so any
        exercise above difficulty_level 1 becomes near-invisible to
        selection for effectively every user.
      - "movement_pattern": no ExerciseMovementPattern row at all --
        ScheduleService._pick_main/_pick_sequence bucket candidates by
        pattern, so an untagged exercise never appears in any bucket,
        on_ice or off_ice.
      - "warmup_stage": phase=warmup with warmup_stage still NULL --
        _pick_warmup_complex fills one slot per WarmupStage in
        WARMUP_STAGE_ORDER, so an untagged warmup exercise can never be
        selected for any stage.
      - "equipment_for_tracked_weight": off_ice, tracks_weight=true, zero
        ExerciseEquipmentItem rows. Deliberately narrower than "any
        off_ice exercise with zero equipment tags" -- most real off_ice
        exercises are legitimately bodyweight-only (245/368 checked
        2026-08-20), so that blanket check would be almost pure noise.
        A tracked-weight exercise with nothing to hold/load is the actual
        content gap worth flagging.
    """

    exercise_id: uuid.UUID
    name: str
    category: ExerciseCategory
    phase: TrainingPhase
    missing: list[str]


class MuscleGroupWeight(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    muscle_group: MuscleGroup
    weight: float = Field(ge=0.0, le=1.0)


class MuscleGroupsReplace(BaseModel):
    # Weights should sum to ~1.0 across the list (see ExerciseService's
    # validation, same precedent as skill_service._validate_weight_sum) --
    # not enforced here since that's a cross-item constraint, not a
    # per-field one.
    muscle_groups: list[MuscleGroupWeight]


class TargetStatsReplace(BaseModel):
    # List order becomes ExerciseTargetStat.order on write -- index 0 is the
    # "primary" stat (see ExerciseRead.target_stats).
    target_stats: list[TargetStat]


class SuggestedWeightRead(BaseModel):
    # None whenever a suggestion can't be computed: the exercise doesn't
    # track weight, the user hasn't set a body weight, or bodyweight_ratio
    # isn't configured for this exercise yet -- see WeightSuggestionService.
    suggested_weight_kg: float | None


class SuggestedRepsRead(BaseModel):
    # None whenever a suggestion can't be computed: the exercise isn't
    # exercise_type=sets_reps, or its rep_range_min/max aren't both set yet
    # (not backfilled) -- see RepsSuggestionService.
    suggested_reps: int | None
