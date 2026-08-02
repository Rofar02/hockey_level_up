import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, Integer, String, false, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enum_column import enum_column
from app.models.exercise import EquipmentType


class Position(enum.StrEnum):
    GOALIE = "goalie"
    DEFENSE = "defense"
    FORWARD = "forward"


class FitnessTier(enum.StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "jersey_number IS NULL OR (jersey_number >= 0 AND jersey_number <= 99)",
            name="ck_users_jersey_number",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    last_name: Mapped[str] = mapped_column(String(100), nullable=False, server_default="")
    first_name: Mapped[str] = mapped_column(String(100), nullable=False, server_default="")
    patronymic: Mapped[str | None] = mapped_column(String(100), nullable=True)
    jersey_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avatar_path: Mapped[str | None] = mapped_column(String(255), nullable=True)

    height: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position: Mapped[Position | None] = mapped_column(
        enum_column(Position, "position"), nullable=True
    )
    # Float, not Integer -- someone 6 months into the sport still deserves a
    # partial experience_bonus/intellect_baseline credit (see
    # app/config/expected_baseline.py) instead of rounding down to 0.
    years_of_experience: Mapped[float | None] = mapped_column(Float, nullable=True)

    equipment_access: Mapped[EquipmentType] = mapped_column(
        enum_column(EquipmentType, "equipment_type"),
        nullable=False,
        server_default=EquipmentType.BODYWEIGHT.value,
    )

    is_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    fitness_tier: Mapped[FitnessTier | None] = mapped_column(
        enum_column(FitnessTier, "fitness_tier"), nullable=True
    )
    has_assessment: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    suggested_reassessment: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    xp: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    @property
    def avatar_url(self) -> str | None:
        if self.avatar_path is None:
            return None
        return f"/static/avatars/{self.avatar_path}"
