import uuid
from datetime import datetime
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.exercise import EquipmentType
from app.models.user import Position, ReminderPreference


class UserBase(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    # No min_length here -- UserRead inherits this too, and legacy users
    # created before these fields existed have "" (the DB server_default),
    # which would otherwise fail response validation. UserCreate re-declares
    # both as required below for actual registration input.
    last_name: str = Field(max_length=100)
    first_name: str = Field(max_length=100)
    patronymic: str | None = Field(default=None, max_length=100)
    height: float | None = Field(default=None, gt=0)
    weight: float | None = Field(default=None, gt=0)
    age: int | None = Field(default=None, gt=0)
    position: Position | None = None
    years_of_experience: float | None = Field(default=None, ge=0)


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)
    last_name: str = Field(min_length=1, max_length=100)
    first_name: str = Field(min_length=1, max_length=100)


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    jersey_number: int | None = Field(default=None, ge=0, le=99)
    avatar_url: str | None = None
    equipment_access: EquipmentType
    is_admin: bool
    xp: int
    level: int
    timezone: str
    reminder_preference: ReminderPreference
    created_at: datetime


class UserUpdate(BaseModel):
    equipment_access: EquipmentType | None = None
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    patronymic: str | None = Field(default=None, max_length=100)
    jersey_number: int | None = Field(default=None, ge=0, le=99)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    reminder_preference: ReminderPreference | None = None

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str | None) -> str | None:
        if value is not None and value not in available_timezones():
            raise ValueError("Unknown IANA timezone")
        return value
