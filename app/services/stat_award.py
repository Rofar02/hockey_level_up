"""Direct stat credit for rewards that aren't tied to an exercise (a team
training, a diary entry for an ice/game day). Same curve and SQL shape as
block_completed.stat_consumer: the base gain shrinks with the stat's current
value (STAT_HARD_CAP/DIMINISHING_EXPONENT imported from there so the curves
can't drift apart), the upsert is atomic and clamped to the cap, and every
credit leaves a StatHistory row with `reason`. Doesn't commit.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.handlers.block_completed import (
    DIMINISHING_EXPONENT,
    LEVEL_UP_EVENT,
    STAT_HARD_CAP,
    xp_to_next_level,
)
from app.models.exercise import TargetStat
from app.models.progress import StatHistory, UserStat
from app.models.user import User
from app.repositories.outbox_repository import OutboxRepository


async def credit_stats(
    session: AsyncSession, user_id: uuid.UUID, base_gains: dict[TargetStat, float], reason: str
) -> dict[TargetStat, float]:
    """Returns the gain actually credited per stat (after diminishing returns)."""
    credited: dict[TargetStat, float] = {}
    # Fixed order, same lock-ordering reason as stat_consumer.
    for stat_type in sorted(base_gains, key=lambda s: s.value):
        current_value = (
            await session.execute(
                select(UserStat.current_value).where(UserStat.user_id == user_id, UserStat.stat_type == stat_type)
            )
        ).scalar_one_or_none() or 0.0
        diminishing_factor = max(0.0, 1 - current_value / STAT_HARD_CAP) ** DIMINISHING_EXPONENT
        gain = round(base_gains[stat_type] * diminishing_factor, 2)

        upsert = pg_insert(UserStat).values(
            user_id=user_id,
            stat_type=stat_type,
            current_value=gain,
            last_updated_at=datetime.now(timezone.utc),
        )
        upsert = upsert.on_conflict_do_update(
            constraint="uq_user_stats_user_stat_type",
            set_={
                "current_value": func.least(UserStat.current_value + upsert.excluded.current_value, STAT_HARD_CAP),
                "last_updated_at": upsert.excluded.last_updated_at,
            },
        ).returning(UserStat.current_value)
        new_value = (await session.execute(upsert)).scalar_one()
        session.add(StatHistory(user_id=user_id, stat_type=stat_type, value=new_value, reason=reason))
        credited[stat_type] = gain
    return credited


async def award_xp(session: AsyncSession, user_id: uuid.UUID, amount: int) -> None:
    """xp_consumer's atomic XP increment + level-up check, for the same
    exercise-less rewards as credit_stats. Doesn't commit."""
    result = await session.execute(
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
        await session.execute(update(User).where(User.id == user_id).values(xp=xp, level=level))
        OutboxRepository(session).add(
            LEVEL_UP_EVENT,
            {"user_id": str(user_id), "old_level": old_level, "new_level": level},
        )
