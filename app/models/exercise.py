import enum
import uuid

from sqlalchemy import Boolean, CheckConstraint, Float, Integer, String, Text, false
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


class EquipmentType(enum.StrEnum):
    GYM = "gym"
    HOME = "home"
    BODYWEIGHT = "bodyweight"


class Exercise(Base):
    __tablename__ = "exercises"
    __table_args__ = (
        CheckConstraint(
            "difficulty_level >= 1 AND difficulty_level <= 5", name="ck_exercises_difficulty_level"
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
    target_stat: Mapped[TargetStat] = mapped_column(
        enum_column(TargetStat, "target_stat"), nullable=False
    )
    difficulty_level: Mapped[int] = mapped_column(Integer, nullable=False)
    equipment_type: Mapped[EquipmentType] = mapped_column(
        enum_column(EquipmentType, "equipment_type"), nullable=False
    )

    video_source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    video_source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    target_sets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

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
