import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.quests import QUEST_DEFINITIONS, QUEST_DEFINITIONS_BY_ID, QuestDefinition, QuestType
from app.events.handlers.block_completed import LEVEL_UP_EVENT, xp_to_next_level
from app.models.quest import UserQuestCompletion
from app.models.training_diary import TrainingDiaryEntry
from app.models.user import User
from app.models.user_temporary_restriction import UserTemporaryRestriction
from app.repositories.friend_repository import FriendRepository
from app.repositories.outbox_repository import OutboxRepository
from app.schemas.quest import QuestStatusRead
from app.services.streak_service import TRAINING_SESSION_TYPES, list_activity_calendar

# Fixed sentinel period for one_time quests -- there's only ever the one
# period, this just needs to be a stable value distinct from any real
# week's Monday for the (user, quest, period) uniqueness constraint to work.
ONE_TIME_PERIOD_KEY = date(1970, 1, 1)

# How far back "first full workout" / "no gap this month" look -- generous
# enough to always cover a real account's whole history without querying an
# unbounded range.
LONG_LOOKBACK_DAYS = 730
MONTHLY_GAP_WINDOW_DAYS = 30
MAX_ACCEPTABLE_GAP_DAYS = 3


def _monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


class QuestService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._friends = FriendRepository(session)

    async def list_status(self, user_id: uuid.UUID, today: date | None = None) -> list[QuestStatusRead]:
        """Evaluates every quest against current data, grants XP for any
        newly-satisfied one (idempotent -- see _grant), and returns the
        resulting status list. Lazy, read-time evaluation (same "check on
        read, no background job" convention as ProgressService.get_streak)
        rather than an event-driven consumer per quest -- most of these
        quests just ask "does at least one qualifying row already exist",
        which is cheaper to check on demand than to wire up a new outbox
        consumer for each of 5+ different trigger points.
        """
        today = today or datetime.now(timezone.utc).date()
        this_monday = _monday_of(today)
        seen_periods = await self._seen_periods(user_id)

        statuses: list[QuestStatusRead] = []
        for quest in QUEST_DEFINITIONS:
            period_key = ONE_TIME_PERIOD_KEY if quest.type == QuestType.ONE_TIME else this_monday
            completed = (quest.id, period_key) in seen_periods
            if not completed and quest.id != "reference_first_visit":
                if await self._check(quest.id, user_id, today, this_monday):
                    await self._grant(user_id, quest, period_key)
                    completed = True
            statuses.append(
                QuestStatusRead(
                    id=quest.id,
                    type=quest.type,
                    title=quest.title,
                    description=quest.description,
                    xp_reward=quest.xp_reward,
                    completed=completed,
                    period_start=None if quest.type == QuestType.ONE_TIME else this_monday.isoformat(),
                )
            )
        return statuses

    async def mark_reference_visited(self, user_id: uuid.UUID) -> None:
        """reference_first_visit has no natural DB trace (a page view isn't
        a row anywhere) -- this is the one quest granted by an explicit
        client signal instead of a server-side check. Idempotent, safe to
        call on every visit."""
        quest = QUEST_DEFINITIONS_BY_ID["reference_first_visit"]
        already = await self._session.execute(
            select(UserQuestCompletion.id).where(
                UserQuestCompletion.user_id == user_id,
                UserQuestCompletion.quest_id == quest.id,
            ).limit(1)
        )
        if already.scalar_one_or_none() is not None:
            return
        await self._grant(user_id, quest, ONE_TIME_PERIOD_KEY)

    async def _seen_periods(self, user_id: uuid.UUID) -> set[tuple[str, date]]:
        result = await self._session.execute(
            select(UserQuestCompletion.quest_id, UserQuestCompletion.period_key).where(
                UserQuestCompletion.user_id == user_id
            )
        )
        return set(result.all())

    async def _grant(self, user_id: uuid.UUID, quest: QuestDefinition, period_key: date) -> None:
        stmt = (
            pg_insert(UserQuestCompletion)
            .values(user_id=user_id, quest_id=quest.id, period_key=period_key, xp_awarded=quest.xp_reward)
            .on_conflict_do_nothing(constraint="uq_user_quest_completions_period")
        )
        result = await self._session.execute(stmt)
        if result.rowcount == 0:
            # Lost a race against a concurrent evaluation of the same
            # (user, quest, period) -- it already got granted, don't award
            # XP twice for one completion.
            return
        await self._grant_xp(user_id, quest.xp_reward)
        await self._session.commit()

    async def _grant_xp(self, user_id: uuid.UUID, amount: int) -> None:
        """Same atomic-increment + level-up shape as
        app.events.handlers.block_completed.xp_consumer, just running on
        this request's own session (a quest grant happens synchronously
        inside GET .../quests, not via the outbox) instead of a fresh
        AsyncSessionLocal."""
        result = await self._session.execute(
            update(User).where(User.id == user_id).values(xp=User.xp + amount).returning(User.xp, User.level)
        )
        row = result.first()
        if row is None:
            return
        xp, level = row
        threshold = xp_to_next_level(level)
        if xp >= threshold:
            old_level = level
            level += 1
            xp -= threshold
            await self._session.execute(update(User).where(User.id == user_id).values(xp=xp, level=level))
            OutboxRepository(self._session).add(
                LEVEL_UP_EVENT, {"user_id": str(user_id), "old_level": old_level, "new_level": level}
            )

    async def _check(self, quest_id: str, user_id: uuid.UUID, today: date, this_monday: date) -> bool:
        checker = getattr(self, f"_check_{quest_id}")
        return bool(await checker(user_id, today, this_monday))

    # -- one-time --

    async def _check_diary_first_entry(self, user_id: uuid.UUID, today: date, this_monday: date) -> bool:
        result = await self._session.execute(
            select(TrainingDiaryEntry.id).where(TrainingDiaryEntry.user_id == user_id).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _check_restriction_first_logged(
        self, user_id: uuid.UUID, today: date, this_monday: date
    ) -> bool:
        result = await self._session.execute(
            select(UserTemporaryRestriction.id)
            .where(UserTemporaryRestriction.user_id == user_id)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _check_first_friend_added(self, user_id: uuid.UUID, today: date, this_monday: date) -> bool:
        friend_ids = await self._friends.list_friend_ids(user_id)
        return len(friend_ids) > 0

    async def _check_first_full_workout(self, user_id: uuid.UUID, today: date, this_monday: date) -> bool:
        days = await list_activity_calendar(
            self._session, user_id, today - timedelta(days=LONG_LOOKBACK_DAYS), today
        )
        return any(d.fully_completed and d.session_type in TRAINING_SESSION_TYPES for d in days)

    # -- weekly --

    async def _check_weekly_three_workouts(self, user_id: uuid.UUID, today: date, this_monday: date) -> bool:
        days = await list_activity_calendar(self._session, user_id, this_monday, today)
        count = sum(1 for d in days if d.fully_completed and d.session_type in TRAINING_SESSION_TYPES)
        return count >= 3

    async def _check_weekly_no_missed_day(self, user_id: uuid.UUID, today: date, this_monday: date) -> bool:
        days = await list_activity_calendar(self._session, user_id, this_monday, today)
        training_days = [d for d in days if d.session_type in TRAINING_SESSION_TYPES]
        # No training day scheduled yet this week isn't "no misses" -- it's
        # "nothing to judge yet", so this only turns true once there's at
        # least one real attempt to have honestly gone right.
        if not training_days:
            return False
        return all(d.fully_completed for d in training_days)

    async def _check_weekly_restrictions_updated(
        self, user_id: uuid.UUID, today: date, this_monday: date
    ) -> bool:
        monday_start = datetime.combine(this_monday, time.min, tzinfo=timezone.utc)
        result = await self._session.execute(
            select(UserTemporaryRestriction.id)
            .where(
                UserTemporaryRestriction.user_id == user_id,
                or_(
                    UserTemporaryRestriction.created_at >= monday_start,
                    UserTemporaryRestriction.lifted_at >= monday_start,
                ),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    # -- long-term --

    async def _check_monthly_no_big_gap(self, user_id: uuid.UUID, today: date, this_monday: date) -> bool:
        window_start = today - timedelta(days=MONTHLY_GAP_WINDOW_DAYS)
        days = await list_activity_calendar(self._session, user_id, window_start, today)
        training_dates = sorted(
            d.date for d in days if d.fully_completed and d.session_type in TRAINING_SESSION_TYPES
        )
        if not training_dates:
            return False
        checkpoints = [window_start, *training_dates, today]
        return all(
            (current - previous).days <= MAX_ACCEPTABLE_GAP_DAYS
            for previous, current in zip(checkpoints, checkpoints[1:])
        )

    async def _check_four_week_streak_goal(self, user_id: uuid.UUID, today: date, this_monday: date) -> bool:
        # The 4 immediately-preceding *complete* weeks -- deliberately not
        # including the current (possibly still in-progress) one, so this
        # can't flip true/false mid-week depending on what hour you check.
        for weeks_back in range(1, 5):
            week_start = this_monday - timedelta(days=7 * weeks_back)
            week_end = week_start + timedelta(days=6)
            days = await list_activity_calendar(self._session, user_id, week_start, week_end)
            count = sum(1 for d in days if d.fully_completed and d.session_type in TRAINING_SESSION_TYPES)
            if count < 3:
                return False
        return True
