import enum
import uuid

from sqlalchemy import CheckConstraint, Enum, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


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


def _enum_column(enum_cls: type[enum.StrEnum], name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        values_callable=lambda cls: [member.value for member in cls],
    )


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

    category: Mapped[ExerciseCategory] = mapped_column(
        _enum_column(ExerciseCategory, "exercise_category"), nullable=False
    )
    phase: Mapped[TrainingPhase] = mapped_column(
        _enum_column(TrainingPhase, "training_phase"), nullable=False
    )
    target_stat: Mapped[TargetStat] = mapped_column(
        _enum_column(TargetStat, "target_stat"), nullable=False
    )
    difficulty_level: Mapped[int] = mapped_column(Integer, nullable=False)
    equipment_type: Mapped[EquipmentType] = mapped_column(
        _enum_column(EquipmentType, "equipment_type"), nullable=False
    )

    video_source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    video_source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
