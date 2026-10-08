import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.exercise import TargetStat
from app.models.schedule import DaySessionType
from app.models.training_diary import FocusResult, GameResult, GameWorkOn, IceEffort, IceHighlight


class DiaryReportIn(BaseModel):
    """The few-taps report after an ice day or a game (2026-10-08). Which
    fields are required depends on the day's type -- checked by
    TrainingDiaryService, which knows it; `skipped` ("Не был") needs none."""

    skipped: bool = False
    # Ice day.
    duration_minutes: int | None = Field(default=None, ge=10, le=300)
    effort: IceEffort | None = None
    highlights: list[IceHighlight] = []
    # The focus of the day shown on the form (app.core.ice_focus id).
    focus_id: str | None = Field(default=None, max_length=40)
    focus_result: FocusResult | None = None
    # Game. Counters stay None for a goalie.
    game_result: GameResult | None = None
    goals: int | None = Field(default=None, ge=0, le=30)
    assists: int | None = Field(default=None, ge=0, le=30)
    shots: int | None = Field(default=None, ge=0, le=100)
    self_rating: int | None = Field(default=None, ge=1, le=5)
    work_on: list[GameWorkOn] = []
    share_rating_with_coach: bool = False


class TrainingDiaryEntryIn(BaseModel):
    note: str | None = None
    # None: a note-only save (autosave while typing) that leaves any
    # earlier report as it is.
    report: DiaryReportIn | None = None


class TrainingDiaryEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    training_session_id: uuid.UUID
    note: str | None
    created_at: datetime
    updated_at: datetime
    reported_at: datetime | None = None
    skipped: bool = False
    duration_minutes: int | None = None
    effort: IceEffort | None = None
    highlights: list[IceHighlight] | None = None
    focus_id: str | None = None
    focus_result: FocusResult | None = None
    game_result: GameResult | None = None
    goals: int | None = None
    assists: int | None = None
    shots: int | None = None
    self_rating: int | None = None
    work_on: list[GameWorkOn] | None = None
    share_rating_with_coach: bool = False
    # Set by TrainingDiaryService as plain attributes on the entry (not
    # columns): whether this day's reward has been credited, and what this
    # particular save credited (empty/0 on every other save).
    rewarded: bool = False
    stat_rewards: dict[TargetStat, float] = {}
    xp_reward: int = 0

class TrainingDiaryEntryListItem(BaseModel):
    """GET /users/me/training-diary -- includes the day's own date/
    session_type (not on TrainingDiaryEntryRead, since a caller already
    scoped to one session doesn't need it) so the diary list can render
    without a second lookup per entry."""

    id: uuid.UUID
    training_session_id: uuid.UUID
    # 2026-09-18: lets the frontend list link each entry straight to
    # /training/<day_plan_id> (TrainingSessionPage) instead of being a dead
    # end -- see TrainingDiaryRepository.list_for_user's docstring.
    day_plan_id: uuid.UUID
    date: date
    session_type: DaySessionType
    note: str | None
    created_at: datetime
    updated_at: datetime
    # Report summary for the diary list (None/False on a note-only entry).
    reported_at: datetime | None = None
    skipped: bool = False
    duration_minutes: int | None = None
    effort: IceEffort | None = None
    game_result: GameResult | None = None
    goals: int | None = None
    assists: int | None = None
    shots: int | None = None
    # The player's own (and the AI coach's) view only -- never the team
    # coach's; that one goes through its own share_rating_with_coach check.
    highlights: list[IceHighlight] | None = None
    self_rating: int | None = None
    work_on: list[GameWorkOn] | None = None


class IceFocusRead(BaseModel):
    """GET /training-sessions/{id}/focus -- the focus of the day for an ice
    day (app.core.ice_focus)."""

    id: str
    stat: TargetStat
    title: str
    cues: list[str]
    reason: str
