import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.exercise import EquipmentType
from app.models.user import Position


class UserBase(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    height: float | None = Field(default=None, gt=0)
    weight: float | None = Field(default=None, gt=0)
    age: int | None = Field(default=None, gt=0)
    position: Position | None = None
    years_of_experience: int | None = Field(default=None, ge=0)


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    equipment_access: EquipmentType
    is_admin: bool
    created_at: datetime


class UserUpdate(BaseModel):
    equipment_access: EquipmentType
