import calendar
import enum
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    SmallInteger,
    String,
    false,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy import case, cast
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enum_column import enum_column

# Below this age a player is hidden from the name search by default.
ADULT_AGE = 18


def full_years(birth: date, today: date) -> int:
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


# Review 12.10, 5: the player card looks festive for a week from the birthday.
BIRTHDAY_FESTIVE_DAYS = 7


def birthday_in(birth: date, year: int) -> date:
    """The birthday in `year` -- 29 February on the 28th in a common year."""
    if birth.month == 2 and birth.day == 29 and not calendar.isleap(year):
        return date(year, 2, 28)
    return date(year, birth.month, birth.day)


class Position(enum.StrEnum):
    GOALIE = "goalie"
    DEFENSE = "defense"
    FORWARD = "forward"


class FitnessTier(enum.StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


# Level-gated cosmetics (item 6, 2026-08-30 gamification pass) -- see
# app.core.level_unlocks for the level thresholds. NULL means "no choice
# made yet, use the automatic default" for both: avatar_ring_accent falls
# back to the tier-based ring app.utils avatarTier.ts already draws
# automatically (this only lets a level>=10 player override *which* accent
# that ring uses below the level-15 tier, which always shows the automatic
# gradient regardless); jersey_color falls back to the jersey number
# badge's existing default (white).
class AvatarRingAccent(enum.StrEnum):
    ICE = "ice"
    PERSIMMON = "persimmon"
    MIX = "mix"
    # 2026-10-04: premium-only, any level (ring + gold player card).
    GOLD = "gold"


class JerseyColor(enum.StrEnum):
    WHITE = "white"
    ICE = "ice"
    PERSIMMON = "persimmon"
    GOLD = "gold"


class ReminderPreference(enum.StrEnum):
    NONE = "none"
    MORNING = "morning"
    EVENING = "evening"


class SeasonPeriod(enum.StrEnum):
    OFFSEASON = "offseason"
    PRESEASON = "preseason"
    SEASON = "season"
    PLAYOFFS = "playoffs"


# P3 #9: purely templated text tone for push reminders (and future
# templated coach-voice copy) -- NOT the same feature as the real LLM
# coach_chat_service ("AI-тренер" in the UI). Deliberately named
# CoachPersonality rather than anything AiCoach*-flavored so the two never
# get confused later when the real model integration lands.
class CoachPersonality(enum.StrEnum):
    CALM = "calm"
    STRICT = "strict"
    HUMOR = "humor"
    VIBE = "vibe"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "jersey_number IS NULL OR (jersey_number >= 0 AND jersey_number <= 99)",
            name="ck_users_jersey_number",
        ),
        # Prefix lookups for the friend search by name (2026-10-08).
        Index("ix_users_lower_last_name", func.lower(text("last_name"))),
        Index("ix_users_lower_first_name", func.lower(text("first_name"))),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Set True by AuthService.confirm_email_verification once the user
    # redeems an AuthToken(purpose=EMAIL_VERIFY) -- deliberately does NOT
    # gate login/authenticate anywhere (see the design discussion: this is
    # the first email integration in the project, so a delivery outage must
    # never lock anyone out of an already-working account). Every row that
    # existed before this column shipped was backfilled to True by this
    # column's migration -- verification is only ever asked of accounts
    # created after email sending existed at all.
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    last_name: Mapped[str] = mapped_column(String(100), nullable=False, server_default="")
    first_name: Mapped[str] = mapped_column(String(100), nullable=False, server_default="")
    patronymic: Mapped[str | None] = mapped_column(String(100), nullable=True)
    jersey_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # "Путь новичка" checklist (app/services/onboarding_service.py): which
    # tasks were paid, whether the first sync happened, dismissed, finished.
    onboarding_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    avatar_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_ring_accent: Mapped[AvatarRingAccent | None] = mapped_column(
        enum_column(AvatarRingAccent, "avatar_ring_accent"), nullable=True
    )
    jersey_color: Mapped[JerseyColor | None] = mapped_column(
        enum_column(JerseyColor, "jersey_color"), nullable=True
    )

    height: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Review 2026-10-11, 3.1: a typed-in age goes stale, so the player gives
    # a birth date and `age` is computed from it (`age_stored`, the old
    # column, is the fallback for those who haven't given one yet).
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    age_stored: Mapped[int | None] = mapped_column("age", Integer, nullable=True)
    # MMDD of the birth date (1231 for 31 Dec), kept by Postgres and indexed:
    # the greeting loop finds today's birthdays without scanning everyone.
    birth_mmdd: Mapped[int | None] = mapped_column(
        SmallInteger,
        Computed("(EXTRACT(month FROM birth_date) * 100 + EXTRACT(day FROM birth_date))::smallint", persisted=True),
        nullable=True,
        index=True,
    )
    # Review 2026-10-11, 3.4 (greetings, later): the year last congratulated.
    last_birthday_greeted_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The local date the «день закрыт» praise was last sent (greeting_scheduler).
    day_done_pushed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Review 12.10, 5: the year the birthday gift (+XP, the coach's word, the
    # team's push) was given -- once a year, whatever happens to the push.
    birthday_gift_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # «🎂 Сегодня день рождения у …» both ways: the player hears about the
    # teammates' birthdays and the team hears about theirs. On by default.
    team_birthdays: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    position: Mapped[Position | None] = mapped_column(
        enum_column(Position, "position"), nullable=True
    )
    # Float, not Integer -- someone 6 months into the sport still deserves a
    # partial experience_bonus/intellect_baseline credit (see
    # app/config/expected_baseline.py) instead of rounding down to 0.
    experience_stored: Mapped[float | None] = mapped_column("years_of_experience", Float, nullable=True)
    # Review 2026-10-11, 3.2: «С какого года играете?» -- the experience
    # grows by itself; years_of_experience is computed from it.
    hockey_since_year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Stage 2.2: replaces the old gym/home/bodyweight equipment_access tier.
    # True bypasses the equipment filter entirely (sees every exercise,
    # including future new items, with no changes needed on this side) --
    # see ExerciseRepository.list_for_assembly. False means matching goes
    # through UserEquipmentItem's owned-item set instead; an empty set there
    # is the natural "bodyweight only" floor, not a separate flag.
    has_gym_access: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    is_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    # Step 8 (security, 2): every access/refresh token carries the version
    # it was issued under ("ver"); bumping it (password change or reset,
    # "Выйти на всех устройствах") kills all of them at once.
    token_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    has_premium: Mapped[bool] = mapped_column(
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
    # Independent of has_assessment/suggested_reassessment above: on-ice
    # rink access is scheduled separately from off-ice training, so the
    # on-ice test's own completion/retake-window state must be tracked on
    # its own, not piggybacked on the off-ice flags.
    has_onice_assessment: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    suggested_onice_reassessment: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    # Phase 5 structural overload brake: subtracted from whichever
    # readiness cap ScheduleService._apply_difficulty_gate computed
    # (off-ice: UserStat-based, on-ice: max_difficulty_for_level),
    # floored at 1 -- never touches level/XP or UserStat itself (see
    # app.services.overload_service). 0 = no throttle. Refreshed in place
    # (derived fresh from recent session feedback history, not
    # incrementally event-driven -- see app.core.overload) at the top of
    # every session-assembly request, the same read-refresh-then-use shape
    # as TrainingBlockService.resolve_active_block.
    difficulty_throttle_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # The coach's ice theme (2026-10-09, release plan 7.1): 1-3 ice focus
    # ids (app.core.ice_focus) the player confirmed from the coach chat,
    # shown before any other pick until the date passes.
    coach_ice_focus_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    coach_ice_focus_until: Mapped[date | None] = mapped_column(Date, nullable=True)

    # One-time welcome tour shown on first Home visit after onboarding --
    # never reset, so a re-login or a second device just sees Home directly.
    has_seen_onboarding_tour: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    # One-time SetLogger hint (suggested weight + feedback), shown on first
    # real encounter with that UI rather than in the general onboarding
    # tour. Flag is per-user, not per-exercise -- once dismissed on any
    # tracks_weight exercise, it never shows again on any other one either.
    has_seen_weight_hint: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    xp: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    # Personal code for the code-based friend-request flow (see
    # FriendService), same generation pattern as Team.invite_code but one
    # per user rather than per team. No open name search for regular users
    # -- a deliberate call, not an oversight (see diagnosis).
    #
    # Nullable (unlike Team.invite_code) purely to avoid a NOT NULL column
    # with no default breaking the ~30 existing test files that construct
    # User(...) directly without a service layer -- Postgres allows any
    # number of NULLs under a UNIQUE constraint, so this doesn't weaken the
    # uniqueness guarantee. Every *real* row gets one: backfilled for
    # existing users by this column's migration, and always generated by
    # AuthService.register for new ones -- NULL only ever appears on
    # test-only User rows built without going through either path.
    friend_code: Mapped[str | None] = mapped_column(String(16), unique=True, index=True, nullable=True)

    # "Меня можно найти по имени" (2026-10-08): the player's own choice, or
    # NULL for the default -- found by name from 18, hidden below it (and
    # when the age is unknown), so a kid isn't findable unless they chose
    # it. See findable_by_name and FriendService.search.
    name_search: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # IANA zone name (e.g. "Europe/Moscow"), auto-detected client-side via
    # Intl.DateTimeFormat().resolvedOptions().timeZone when the user turns
    # reminders on -- without it, reminder_scheduler would have no way to
    # know when "09:00" actually is for this person. "UTC" default keeps the
    # column non-nullable for rows created before this existed.
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="UTC")
    reminder_preference: Mapped[ReminderPreference] = mapped_column(
        enum_column(ReminderPreference, "reminder_preference"),
        nullable=False,
        server_default=ReminderPreference.NONE.value,
    )

    # Phase: П.4 seasonal mode -- manually chosen (no game-schedule access to
    # detect it automatically), affects off-ice training volume and deload
    # frequency during SEASON/PLAYOFFS (see app.core.training_block).
    # OFFSEASON default is behaviorally inert, safe for existing rows.
    season_period: Mapped[SeasonPeriod] = mapped_column(
        enum_column(SeasonPeriod, "season_period"),
        nullable=False,
        server_default=SeasonPeriod.OFFSEASON.value,
    )
    # When the player last changed season_period themselves (2026-10-10):
    # the default OFFSEASON of a new account is not a switch to the
    # off-season, so «Мой сезон» does not open on it.
    season_period_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # P3 #9: chosen in Settings (not onboarding -- a preference people may
    # want to change later, not a one-time setup step). CALM default keeps
    # existing users' reminder wording behaviorally unchanged.
    coach_personality: Mapped[CoachPersonality] = mapped_column(
        enum_column(CoachPersonality, "coach_personality"),
        nullable=False,
        server_default=CoachPersonality.CALM.value,
    )
    # One-time explainer shown on first /coach visit (2026-08-30 follow-up):
    # personality was silently defaulted to CALM for every user and buried
    # in Settings with no explanation that it also drives reminder/check-in
    # wording, not just this chat -- CoachPage now offers the real choice
    # once, same "has_seen_X" pattern as has_seen_onboarding_tour above.
    # False for every existing row too (not just new ones) since none of
    # them ever actually saw this explanation.
    has_seen_coach_personality_intro: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    # Phase: П.5 tournament taper -- user-set target date for the deterministic
    # taper override (see app.core.training_block.is_tapering/
    # is_final_taper_week). An algorithm, not an AI-coach decision, per the
    # product spec -- an AI coach could someday be the *interface* to set this
    # field ("скажи тренеру про турнир 15 марта"), not the mechanism that
    # computes taper behavior. Nullable, no default -- most users have no
    # upcoming tournament to taper for.
    tournament_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Set at registration time, only when the required consent checkbox was
    # checked (AuthService.register rejects the request with 400 otherwise)
    # -- 152-FZ requires being able to point to when consent was given, so
    # this is never backfilled/defaulted for existing rows.
    privacy_consent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def local_today(self) -> date:
        try:
            return datetime.now(ZoneInfo(self.timezone or "UTC")).date()
        except Exception:
            return datetime.now(timezone.utc).date()

    @hybrid_property
    def age(self) -> int | None:
        """Full years from the birth date, in the player's own time zone;
        the old typed-in age until a birth date is given."""
        if self.birth_date is None:
            return self.age_stored
        return full_years(self.birth_date, self.local_today())

    @age.inplace.setter
    def _age_setter(self, value: int | None) -> None:
        self.age_stored = value

    @age.inplace.expression
    @classmethod
    def _age_expression(cls):
        return case(
            (cls.birth_date.is_not(None), cast(func.date_part("year", func.age(cls.birth_date)), Integer)),
            else_=cls.age_stored,
        )

    @property
    def years_of_experience(self) -> float | None:
        if self.hockey_since_year is None:
            return self.experience_stored
        today = self.local_today()
        years = today.year - self.hockey_since_year
        if years >= 1:
            return float(years)
        # Started this year (review 12.10, 3): a typed-in fraction (half a
        # season) is kept; else half of the year gone so far -- a beginner's
        # partial baseline credit isn't rounded down to 0.
        if self.experience_stored is not None and 0 < self.experience_stored < 1:
            return self.experience_stored
        elapsed = (today - date(today.year, 1, 1)).days / (366 if calendar.isleap(today.year) else 365)
        return round(elapsed / 2, 2)

    @years_of_experience.setter
    def years_of_experience(self, value: float | None) -> None:
        # An old client still sends years: kept as the start year.
        self.experience_stored = value
        self.hockey_since_year = None if value is None else self.local_today().year - round(value)

    @property
    def birthday_festive(self) -> bool:
        """From the birthday (player's own date) for BIRTHDAY_FESTIVE_DAYS."""
        if self.birth_date is None:
            return False
        today = self.local_today()
        return any(
            birthday_in(self.birth_date, year) <= today < birthday_in(self.birth_date, year) + timedelta(days=BIRTHDAY_FESTIVE_DAYS)
            for year in (today.year, today.year - 1)
        )

    @property
    def shared_birthday_festive(self) -> bool:
        """The festive card others see -- only when the player shares their
        birthday with the team (team_birthdays)."""
        return self.team_birthdays is not False and self.birthday_festive

    @property
    def findable_by_name(self) -> bool:
        if self.name_search is not None:
            return self.name_search
        return self.age is not None and self.age >= ADULT_AGE

    @property
    def avatar_url(self) -> str | None:
        if self.avatar_path is None:
            return None
        return f"/static/avatars/{self.avatar_path}"
