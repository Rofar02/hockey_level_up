import uuid
from datetime import datetime
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.exercise import EquipmentType
from app.models.user import Position, ReminderPreference


class UserBase(BaseModel):
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
    # No username input at registration -- AuthService.register generates
    # one internally (still needed as a stable, unique DB identifier for
    # login-by-username on pre-existing accounts). Jersey number, on the
    # other hand, is now a required part of who a player is, not an
    # optional profile detail edited later.
    jersey_number: int = Field(ge=0, le=99)
    # Defaults to False (not a required field) rather than `bool` with no
    # default -- an omitted field should fail the same explicit 400 check in
    # AuthService.register as an explicit `false`, instead of a generic 422
    # from pydantic that wouldn't distinguish "forgot to send it" from any
    # other malformed request.
    privacy_consent: bool = False


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    # Still a real, unique column (see AuthService._generate_username) --
    # kept on UserRead since login-by-username still works for accounts
    # created before this field left the registration form, but it's no
    # longer treated as a display name anywhere in the frontend.
    username: str
    jersey_number: int | None = Field(default=None, ge=0, le=99)
    avatar_url: str | None = None
    equipment_access: EquipmentType
    is_admin: bool
    has_premium: bool
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


class UserDeleteRequest(BaseModel):
    # Defaults to "" rather than a required field, same reasoning as
    # UserCreate.privacy_consent above -- an omitted password should fail
    # UserService.delete_account's explicit 400 check, not a generic 422.
    password: str = ""


class UserAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    first_name: str
    last_name: str
    level: int
    is_admin: bool
    has_premium: bool
    created_at: datetime


class UserAdminUpdate(BaseModel):
    is_admin: bool | None = None
    has_premium: bool | None = None
