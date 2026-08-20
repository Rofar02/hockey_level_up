import uuid
from datetime import date, datetime
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import Position, ReminderPreference, SeasonPeriod


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
    # Only ever populated on the caller's own UserRead (this schema is never
    # returned for anyone else -- see UserPublicRead for what's shown about
    # other users) -- shared out-of-band so a friend can send a request to
    # it (FriendService.send_request_by_code).
    friend_code: str | None = None
    # Stage 2.2: bypasses the equipment filter entirely when true. Owned
    # items themselves (UserEquipmentItem) aren't a passthrough field here,
    # same "not part of the main Read schema" treatment ExerciseRead gives
    # movement_patterns/muscle_groups -- see GET /users/me/equipment-items.
    has_gym_access: bool
    email_verified: bool
    is_admin: bool
    has_premium: bool
    xp: int
    level: int
    timezone: str
    reminder_preference: ReminderPreference
    season_period: SeasonPeriod
    tournament_date: date | None = None
    has_seen_onboarding_tour: bool
    has_seen_weight_hint: bool
    created_at: datetime


class UserPublicRead(BaseModel):
    """What a friend or teammate can see about another user -- see
    UserService.get_public_profile for the friend-or-teammate 403 gate.
    Deliberately excludes weight/height (never included here regardless of
    relationship, per spec) and everything private on UserRead: email,
    is_admin, has_premium, has_gym_access, timezone, reminder_preference,
    season_period, tournament_date, has_seen_onboarding_tour,
    has_seen_weight_hint, friend_code.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    first_name: str
    last_name: str
    patronymic: str | None = None
    avatar_url: str | None = None
    position: Position | None = None
    jersey_number: int | None = None
    years_of_experience: float | None = None
    level: int
    xp: int
    created_at: datetime


class UserUpdate(BaseModel):
    has_gym_access: bool | None = None
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    patronymic: str | None = Field(default=None, max_length=100)
    jersey_number: int | None = Field(default=None, ge=0, le=99)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    reminder_preference: ReminderPreference | None = None
    season_period: SeasonPeriod | None = None
    tournament_date: date | None = None
    has_seen_weight_hint: bool | None = None

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
