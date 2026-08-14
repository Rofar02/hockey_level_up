import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from app.db.session import AsyncSessionLocal
from app.events.idempotency import try_claim
from app.events.registry import register_handler
from app.models.exercise import TargetStat
from app.models.progress import StatHistory, TrainingStreak, UserStat
from app.models.skill import SkillStatWeight, SkillTag
from app.models.user import User
from app.repositories.outbox_repository import OutboxRepository
from app.services.streak_service import has_missed_training_day

EVENT_TYPE = "block_completed"

# Read directly from outbox_events for the friend activity feed
# (FriendActivityService) -- no consumer registered for either, since
# nothing needs to react to them, only display them after the fact.
LEVEL_UP_EVENT = "level_up"

RELEVANCE_WEIGHT_THRESHOLD = 0.6
RELEVANT_MULTIPLIER = 1.3
BASE_MULTIPLIER = 1.0
DIMINISHING_CAP = 120

STAT_CONSUMER_HANDLER_NAME = "stat_consumer"
STREAK_CONSUMER_HANDLER_NAME = "streak_consumer"
XP_CONSUMER_HANDLER_NAME = "xp_consumer"


def xp_to_next_level(level: int) -> int:
    return round(100 * 1.2 ** (level - 1))


@register_handler(EVENT_TYPE)
async def stat_consumer(payload: dict, event_id: uuid.UUID) -> None:
    user_id = uuid.UUID(payload["user_id"])
    exercise_id = payload["exercise_id"]
    stat_types = [TargetStat(value) for value in payload["target_stats"]]
    difficulty_level = payload["difficulty_level"]

    # An exercise can now carry more than one target_stat (see
    # ExerciseTargetStat) -- the base award (before per-stat diminishing
    # returns/relevance) is split evenly across all of them, so a 2-stat
    # exercise doesn't award twice what a 1-stat exercise at the same
    # difficulty would. Each stat still gets its own diminishing_factor and
    # relevance_multiplier below, computed independently, since those are
    # legitimately per-(user, stat) and per-(exercise, stat) quantities, not
    # something to also split.
    base_gain = (difficulty_level * 0.5) / len(stat_types)

    async with AsyncSessionLocal() as session:
        # Claimed first, in the same transaction every stat's side-effect
        # below commits in: at-least-once redelivery of this event finds its
        # claim already here and returns without touching UserStat/
        # StatHistory at all. If anything below raises, the whole
        # transaction (including this claim) rolls back, so a genuine retry
        # can still claim it -- one claim per event, not per stat, same
        # idempotency granularity as before this became multi-stat.
        if not await try_claim(session, event_id, STAT_CONSUMER_HANDLER_NAME):
            return

        skill_ids = (
            await session.execute(
                select(SkillTag.skill_id).where(
                    SkillTag.exercise_id == uuid.UUID(exercise_id)
                )
            )
        ).scalars().all()

        for stat_type in stat_types:
            # Pre-increment value, used only to shape this event's gain.
            # Reading it outside the atomic upsert below means two
            # concurrent events for the same user/stat can compute their
            # gain off the same starting value -- both gains still land (the
            # upsert itself stays atomic), just without seeing each other's
            # diminishing returns. Same accepted tradeoff as the non-atomic
            # XP level-up below.
            current_value = (
                await session.execute(
                    select(UserStat.current_value).where(
                        UserStat.user_id == user_id, UserStat.stat_type == stat_type
                    )
                )
            ).scalar_one_or_none() or 0.0
            diminishing_factor = 1 - (current_value / DIMINISHING_CAP)

            relevance_multiplier = BASE_MULTIPLIER
            if skill_ids:
                max_weight = (
                    await session.execute(
                        select(func.max(SkillStatWeight.weight)).where(
                            SkillStatWeight.skill_id.in_(skill_ids),
                            SkillStatWeight.stat_type == stat_type,
                        )
                    )
                ).scalar()
                if max_weight is not None and max_weight > RELEVANCE_WEIGHT_THRESHOLD:
                    relevance_multiplier = RELEVANT_MULTIPLIER

            gain = round(base_gain * diminishing_factor * relevance_multiplier, 2)

            upsert = pg_insert(UserStat).values(
                user_id=user_id,
                stat_type=stat_type,
                current_value=gain,
                last_updated_at=datetime.now(timezone.utc),
            )
            upsert = upsert.on_conflict_do_update(
                constraint="uq_user_stats_user_stat_type",
                set_={
                    "current_value": UserStat.current_value + upsert.excluded.current_value,
                    "last_updated_at": upsert.excluded.last_updated_at,
                },
            ).returning(UserStat.current_value)
            new_value = (await session.execute(upsert)).scalar_one()

            session.add(
                StatHistory(
                    user_id=user_id,
                    stat_type=stat_type,
                    value=new_value,
                    reason=f"quest_completed:{exercise_id}",
                )
            )

        await session.commit()


@register_handler(EVENT_TYPE)
async def streak_consumer(payload: dict, event_id: uuid.UUID) -> None:
    user_id = uuid.UUID(payload["user_id"])
    today = date.today()

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TrainingStreak).where(TrainingStreak.user_id == user_id).with_for_update()
        )
        streak = result.scalar_one_or_none()
        if streak is None:
            # with_for_update() only locks rows that already exist, so two
            # concurrent first-ever-activity events can both miss here and
            # both try to insert -> unique violation on user_id. Fall back to
            # a locked re-read instead of losing the event like stat_consumer
            # used to.
            streak = TrainingStreak(
                user_id=user_id, current_streak=0, longest_streak=0, last_activity_date=None
            )
            session.add(streak)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                result = await session.execute(
                    select(TrainingStreak)
                    .where(TrainingStreak.user_id == user_id)
                    .with_for_update()
                )
                streak = result.scalar_one()

        # Claimed here rather than at the top of the function: the
        # IntegrityError fallback above can call session.rollback(), which
        # would wipe out an earlier claim before it's ever committed. From
        # this point on nothing in this function rolls back, so the claim
        # and the streak mutation below always commit together.
        if not await try_claim(session, event_id, STREAK_CONSUMER_HANDLER_NAME):
            return

        if streak.last_activity_date == today:
            pass  # already counted today, don't touch the streak
        elif streak.last_activity_date is not None and not await has_missed_training_day(
            session, user_id, streak.last_activity_date, today
        ):
            # No gap, or the gap was only rest days / days with no plan.
            streak.current_streak += 1
        else:
            streak.current_streak = 1

        if streak.current_streak > streak.longest_streak:
            streak.longest_streak = streak.current_streak
        streak.last_activity_date = today

        await session.commit()


@register_handler(EVENT_TYPE)
async def xp_consumer(payload: dict, event_id: uuid.UUID) -> None:
    user_id = uuid.UUID(payload["user_id"])
    difficulty_level = payload["difficulty_level"]
    gain = difficulty_level * 10

    async with AsyncSessionLocal() as session:
        if not await try_claim(session, event_id, XP_CONSUMER_HANDLER_NAME):
            return

        # Atomic SQL increment (xp = xp + gain) so concurrent events can't
        # clobber each other. RETURNING gives us the post-increment values in
        # the same round trip, so there's no read-after-write gap to reread.
        result = await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(xp=User.xp + gain)
            .returning(User.xp, User.level)
        )
        row = result.first()
        if row is None:
            return
        xp, level = row

        # Level-up is a separate, non-atomic write: a concurrent xp increment
        # landing between the update above and this one could be overwritten.
        # Acceptable per spec -- only the increment itself needs to be atomic.
        threshold = xp_to_next_level(level)
        if xp >= threshold:
            old_level = level
            level += 1
            xp -= threshold
            await session.execute(
                update(User).where(User.id == user_id).values(xp=xp, level=level)
            )
            # Same outbox pattern as SessionBlockService.complete_block: the
            # event row is written in the same transaction as the level
            # bump, so a broker/relay outage can't lose it. No consumer
            # needed here (see LEVEL_UP_EVENT above) -- FriendActivityService
            # reads outbox_events directly.
            OutboxRepository(session).add(
                LEVEL_UP_EVENT,
                {"user_id": str(user_id), "old_level": old_level, "new_level": level},
            )

        await session.commit()
