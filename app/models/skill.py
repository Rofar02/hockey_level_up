import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enum_column import enum_column
from app.models.exercise import TargetStat


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)


class SkillStatWeight(Base):
    __tablename__ = "skill_stat_weights"
    __table_args__ = (
        UniqueConstraint("skill_id", "stat_type", name="uq_skill_stat_weights_skill_stat"),
        CheckConstraint(
            "weight >= 0.0 AND weight <= 1.0", name="ck_skill_stat_weights_weight_range"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stat_type: Mapped[TargetStat] = mapped_column(
        enum_column(TargetStat, "target_stat"), nullable=False
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False)


class SkillTag(Base):
    __tablename__ = "skill_tags"
    __table_args__ = (
        UniqueConstraint("exercise_id", "skill_id", name="uq_skill_tags_exercise_skill"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exercises.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transfer_note: Mapped[str] = mapped_column(Text, nullable=False)


class SkillMilestone(Base):
    __tablename__ = "skill_milestones"
    __table_args__ = (
        CheckConstraint(
            "threshold >= 0 AND threshold <= 100", name="ck_skill_milestones_threshold_range"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class UserSkillPreference(Base):
    __tablename__ = "user_skill_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "skill_id", name="uq_user_skill_preferences_user_skill"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
