import uuid
from datetime import date, datetime
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.exercise import TargetStat
from app.models.user import (
    AvatarRingAccent,
    CoachPersonality,
    JerseyColor,
    Position,
    ReminderPreference,
    SeasonPeriod,
)


MIN_AGE, MAX_AGE = 6, 90
FIRST_HOCKEY_YEAR = 1930


def check_birth_date(value: date | None) -> date | None:
    """Review 2026-10-11, 3.3: not in the future, an age of 6..90."""
    if value is None:
        return value
    today = date.today()
    if value > today:
        raise ValueError("Дата рождения не может быть в будущем")
    years = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
    if not MIN_AGE <= years <= MAX_AGE:
        raise ValueError(f"Возраст должен быть от {MIN_AGE} до {MAX_AGE} лет")
    return value


def check_hockey_since(value: int | None) -> int | None:
    if value is None:
        return value
    if value > date.today().year:
        raise ValueError("Год не может быть в будущем")
    if value < FIRST_HOCKEY_YEAR:
        raise ValueError("Проверьте год")
    return value


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
    # Review 2026-10-11, 3.1-3.2: given instead of the age / the years.
    birth_date: date | None = None
    hockey_since_year: int | None = None


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

    _birth = field_validator("birth_date")(classmethod(lambda cls, v: check_birth_date(v)))
    _since = field_validator("hockey_since_year")(classmethod(lambda cls, v: check_hockey_since(v)))

    @model_validator(mode="after")
    def _since_after_birth(self) -> "UserCreate":
        if self.birth_date and self.hockey_since_year and self.hockey_since_year < self.birth_date.year:
            raise ValueError("Год начала игры раньше года рождения")
        return self


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
    avatar_ring_accent: AvatarRingAccent | None = None
    jersey_color: JerseyColor | None = None
    # Only ever populated on the caller's own UserRead (this schema is never
    # returned for anyone else -- see UserPublicRead for what's shown about
    # other users) -- shared out-of-band so a friend can send a request to
    # it (FriendService.send_request_by_code).
    friend_code: str | None = None
    # Whether the name search finds this player now (the explicit choice or
    # the age default, see User.findable_by_name).
    findable_by_name: bool = False
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
    coach_personality: CoachPersonality
    tournament_date: date | None = None
    has_seen_onboarding_tour: bool
    has_seen_weight_hint: bool
    has_seen_coach_personality_intro: bool
    created_at: datetime
    # Review 12.10, 5: «🎂 день рождения у …» with the team, both ways.
    team_birthdays: bool = True
    # The festive player card, a week from the birthday.
    birthday_festive: bool = False


class PublicStatRead(BaseModel):
    """One stat on someone else's player card -- just the value, none of the
    decay bookkeeping UserStatRead carries for the owner."""

    stat_type: TargetStat
    effective_value: float


class UserPublicRead(BaseModel):
    """What a friend or teammate can see about another user -- see
    UserService.get_public_profile for the friend-or-teammate 403 gate.
    Deliberately excludes weight/height (never included here regardless of
    relationship, per spec) and everything private on UserRead: email,
    is_admin, has_gym_access, timezone, reminder_preference,
    season_period, coach_personality, tournament_date,
    has_seen_onboarding_tour, has_seen_weight_hint,
    has_seen_coach_personality_intro, friend_code.
    has_premium IS included (2026-10-04, owner's decision): the player card
    shows a PREMIUM plate to friends and teammates too.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    first_name: str
    last_name: str
    patronymic: str | None = None
    avatar_url: str | None = None
    avatar_ring_accent: AvatarRingAccent | None = None
    position: Position | None = None
    jersey_number: int | None = None
    jersey_color: JerseyColor | None = None
    has_premium: bool = False
    years_of_experience: float | None = None
    # Review 2026-10-11, 3.3: «Играю с 2021». Never the age or the birth
    # date -- this card is also shown to strangers on the invite-link page.
    hockey_since_year: int | None = None
    level: int
    xp: int
    created_at: datetime
    # Review 12.10, 5: the festive card for the birthday week -- set by the
    # router for a teammate only, when the player shares the birthday with
    # the team (User.team_birthdays); never behind the invite link.
    birthday_festive: bool = False
    # The six stats' current values, so a friend or teammate sees the same
    # player card the owner does. Filled in by the router (not a column).
    stats: list[PublicStatRead] = []
    # The player's team for the card (2026-10-09), filled in by the router.
    team: "PlayerTeamBadgeRead | None" = None


class UserUpdate(BaseModel):
    has_gym_access: bool | None = None
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    patronymic: str | None = Field(default=None, max_length=100)
    jersey_number: int | None = Field(default=None, ge=0, le=99)
    # PhysicalStep's own registration copy promises "можно... заполнить
    # позже в настройках" for exactly these four fields (they're skippable
    # there) -- until this, Settings had no way to actually do that, so
    # anyone who registered without an age was permanently locked out of
    # the fitness test/leaderboard/analytics rating (all hard-require it,
    # see assessment_service.py/leaderboard_service.py/progress_service.py).
    height: float | None = Field(default=None, gt=0)
    weight: float | None = Field(default=None, gt=0)
    age: int | None = Field(default=None, gt=0)
    position: Position | None = None
    years_of_experience: float | None = Field(default=None, ge=0)
    birth_date: date | None = None
    hockey_since_year: int | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    reminder_preference: ReminderPreference | None = None
    season_period: SeasonPeriod | None = None
    coach_personality: CoachPersonality | None = None
    tournament_date: date | None = None
    has_seen_weight_hint: bool | None = None
    avatar_ring_accent: AvatarRingAccent | None = None
    jersey_color: JerseyColor | None = None
    name_search: bool | None = None
    team_birthdays: bool | None = None

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str | None) -> str | None:
        if value is not None and value not in available_timezones():
            raise ValueError("Unknown IANA timezone")
        return value

    _birth = field_validator("birth_date")(classmethod(lambda cls, v: check_birth_date(v)))
    _since = field_validator("hockey_since_year")(classmethod(lambda cls, v: check_hockey_since(v)))


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


class TeamAttentionRead(BaseModel):
    """What's waiting on the "Команда" tab -- see TeamAttentionService."""

    friend_requests: int
    party_invites: int
    team_join_requests: int
    # Captains' invitations to the player, still unanswered (2026-10-08).
    team_invitations: int = 0


from app.schemas.team import PlayerTeamBadgeRead  # noqa: E402  (team.py imports user.py)

UserPublicRead.model_rebuild()
