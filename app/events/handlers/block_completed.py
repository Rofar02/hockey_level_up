import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from app.db.session import AsyncSessionLocal
from app.events.registry import register_handler
from app.models.exercise import TargetStat
from app.models.progress import StatHistory, TrainingStreak, UserStat
from app.models.user import User

EVENT_TYPE = "block_completed"


@register_handler(EVENT_TYPE)
async def stat_consumer(payload: dict) -> None:
    user_id = uuid.UUID(payload["user_id"])
    exercise_id = payload["exercise_id"]
    stat_type = TargetStat(payload["target_stat"])
    difficulty_level = payload["difficulty_level"]
    gain = difficulty_level * 0.5

    async with AsyncSessionLocal() as session:
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
async def streak_consumer(payload: dict) -> None:
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

        if streak.last_activity_date == today:
            pass  # already counted today, don't touch the streak
        elif streak.last_activity_date == today - timedelta(days=1):
            streak.current_streak += 1
        else:
            streak.current_streak = 1

        if streak.current_streak > streak.longest_streak:
            streak.longest_streak = streak.current_streak
        streak.last_activity_date = today

        await session.commit()


@register_handler(EVENT_TYPE)
async def xp_consumer(payload: dict) -> None:
    user_id = uuid.UUID(payload["user_id"])
    difficulty_level = payload["difficulty_level"]
    gain = difficulty_level * 10

    async with AsyncSessionLocal() as session:
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
        threshold = level * 100
        if xp >= threshold:
            level += 1
            xp -= threshold
            await session.execute(
                update(User).where(User.id == user_id).values(xp=xp, level=level)
            )

        await session.commit()
