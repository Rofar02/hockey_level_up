import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from app.core.muscle_load import GAIN_PER_DIFFICULTY_LEVEL, MAX_INTENSITY, get_effective_muscle_load
from app.db.session import AsyncSessionLocal
from app.events.idempotency import try_claim
from app.events.registry import register_handler
from app.models.exercise import ExerciseMuscleGroup, TargetStat
from app.models.progress import StatHistory, TrainingStreak, UserMuscleLoad, UserStat
from app.models.skill import SkillStatWeight, SkillTag
from app.models.user import User
from app.repositories.outbox_repository import OutboxRepository
from app.services.streak_service import has_missed_training_day, is_session_fully_completed

EVENT_TYPE = "block_completed"

# Read directly from outbox_events for the friend activity feed
# (FriendActivityService) -- no consumer registered for either, since
# nothing needs to react to them, only display them after the fact.
LEVEL_UP_EVENT = "level_up"

RELEVANCE_WEIGHT_THRESHOLD = 0.6
RELEVANT_MULTIPLIER = 1.3
BASE_MULTIPLIER = 1.0

# Hard cap 100 (2026-08-19: "максимум характеристик не больше 100, набор
# должен усложняться -- до 20 быстро, до 40 чуть медленнее... до 100 уже
# прям тяжко"). factor = max(0, 1 - value/STAT_HARD_CAP) ** DIMINISHING_EXPONENT
# instead of the old linear `1 - value/120`: a linear ramp slows down
# evenly, an exponent > 1 keeps early gains fast (0->20 barely dented) while
# stretching the last stretch (80->100) out asymptotically -- tuned via
# scripts/tune_stat_curve.py against the same event-frequency numbers
# scripts/simulate_long_term_usage.py's 'stable' scenario produced (see that
# report): p=2.2 crosses 20 in ~3 weeks, 40 in ~8, 60 in ~15, 80 in ~32, and
# doesn't realistically reach 100 in two years of steady training -- 100 is
# meant to stay a asymptotic ceiling, not a normal-play target.
STAT_HARD_CAP = 100.0
DIMINISHING_EXPONENT = 2.2

STAT_CONSUMER_HANDLER_NAME = "stat_consumer"
STREAK_CONSUMER_HANDLER_NAME = "streak_consumer"
XP_CONSUMER_HANDLER_NAME = "xp_consumer"
MUSCLE_LOAD_CONSUMER_HANDLER_NAME = "muscle_load_consumer"


def xp_to_next_level(level: int) -> int:
    return round(100 * 1.2 ** (level - 1))


@register_handler(EVENT_TYPE)
async def stat_consumer(payload: dict, event_id: uuid.UUID) -> None:
    user_id = uuid.UUID(payload["user_id"])
    exercise_id = payload["exercise_id"]
    # Sorted into a fixed, canonical order (not the exercise's own
    # ExerciseTargetStat.order) -- found via E2E stress test 2026-08-18:
    # two block_completed events for the same user, processed concurrently,
    # each upsert their own stat_types in whatever order their exercise
    # happened to declare them. If exercise A carries [strength, agility]
    # and exercise B carries [agility, strength], the two transactions grab
    # UserStat row locks in opposite order and Postgres deadlocks one of
    # them. Sorting here means every concurrent invocation, for any
    # exercise, always acquires this user's UserStat rows in the same
    # order -- the standard fix for a lock-ordering deadlock, cheaper than
    # serializing per-user and doesn't just mask the symptom the way a
    # catch-and-retry would.
    stat_types = sorted((TargetStat(value) for value in payload["target_stats"]), key=lambda s: s.value)
    difficulty_level = payload["difficulty_level"]

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

        if not stat_types:
            # An exercise with no ExerciseTargetStat rows yet (catalog entry
            # not fully classified) -- nothing to credit. Commit anyway so
            # the claim above sticks; without it, at-least-once redelivery
            # would retry this same no-op event forever.
            await session.commit()
            return

        # An exercise can now carry more than one target_stat (see
        # ExerciseTargetStat) -- the base award (before per-stat diminishing
        # returns/relevance) is split evenly across all of them, so a 2-stat
        # exercise doesn't award twice what a 1-stat exercise at the same
        # difficulty would. Each stat still gets its own diminishing_factor and
        # relevance_multiplier below, computed independently, since those are
        # legitimately per-(user, stat) and per-(exercise, stat) quantities, not
        # something to also split.
        base_gain = (difficulty_level * 0.5) / len(stat_types)

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
            diminishing_factor = max(0.0, 1 - current_value / STAT_HARD_CAP) ** DIMINISHING_EXPONENT

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
                    # Clamped in SQL, not just relied on via the asymptotic
                    # curve above -- the curve alone only makes gains *shrink*
                    # near the cap, it never mathematically guarantees the
                    # sum stays <= STAT_HARD_CAP, and two concurrent events for
                    # the same stat (see the lock-ordering note above) could
                    # otherwise both land and nudge a value just over it.
                    "current_value": func.least(
                        UserStat.current_value + upsert.excluded.current_value, STAT_HARD_CAP
                    ),
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
async def muscle_load_consumer(payload: dict, event_id: uuid.UUID) -> None:
    """Body-muscles map (2026-08-20 planning session). Reads ExerciseMuscleGroup
    itself rather than expecting muscle data in the payload -- same choice
    stat_consumer already made for SkillTag/SkillStatWeight above, so this
    event's own schema never needs to grow just because a new signal wants
    to read from the exercise's own catalog tags.

    Row-locks each touched UserMuscleLoad (like streak_consumer, not
    stat_consumer's atomic upsert) because the gain here isn't a pure
    additive delta -- it's "collapse today's already-decayed effective
    value, then add this session's contribution", which needs the current
    row's real state read first. See app.core.muscle_load's own module
    docstring for why this can't reuse stat_consumer's write-then-project
    shape.
    """
    user_id = uuid.UUID(payload["user_id"])
    exercise_id = uuid.UUID(payload["exercise_id"])
    difficulty_level = payload["difficulty_level"]

    async with AsyncSessionLocal() as session:
        if not await try_claim(session, event_id, MUSCLE_LOAD_CONSUMER_HANDLER_NAME):
            return

        muscle_weights = (
            await session.execute(
                select(ExerciseMuscleGroup.muscle_group, ExerciseMuscleGroup.weight).where(
                    ExerciseMuscleGroup.exercise_id == exercise_id
                )
            )
        ).all()

        if not muscle_weights:
            # Not yet muscle-tagged (catalog entry not fully classified) --
            # nothing to credit. Commit anyway so the claim above sticks,
            # same reasoning as stat_consumer's empty-stat_types branch.
            await session.commit()
            return

        now = datetime.now(timezone.utc)
        base_gain = difficulty_level * GAIN_PER_DIFFICULTY_LEVEL

        # Sorted for the same lock-ordering-deadlock reason stat_consumer's
        # stat_types sort exists: two concurrent block_completed events for
        # different exercises that happen to share a muscle group must
        # always acquire this user's UserMuscleLoad rows in the same
        # relative order.
        for muscle_group, weight in sorted(muscle_weights, key=lambda row: row[0].value):
            result = await session.execute(
                select(UserMuscleLoad)
                .where(
                    UserMuscleLoad.user_id == user_id,
                    UserMuscleLoad.muscle_group == muscle_group,
                )
                .with_for_update()
            )
            load = result.scalar_one_or_none()
            effective = get_effective_muscle_load(load, now) if load is not None else 0.0
            new_value = min(MAX_INTENSITY, effective + base_gain * weight)

            if load is None:
                session.add(
                    UserMuscleLoad(
                        user_id=user_id,
                        muscle_group=muscle_group,
                        current_value=new_value,
                        last_updated_at=now,
                    )
                )
            else:
                load.current_value = new_value
                load.last_updated_at = now

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
                # scalar_one_or_none(), not scalar_one(): the IntegrityError
                # above isn't always the expected concurrent-insert race --
                # it's also what a foreign-key violation looks like if the
                # account behind user_id was deleted (UserService.delete_
                # account, ON DELETE CASCADE) while this event was still
                # in flight. That case leaves the re-select genuinely empty,
                # not racing against a sibling insert, so scalar_one() raised
                # NoResultFound instead of resolving it. Nothing to do for a
                # user that no longer exists -- claim the event (so
                # redelivery doesn't retry forever) and stop.
                streak = result.scalar_one_or_none()
                if streak is None:
                    await try_claim(session, event_id, STREAK_CONSUMER_HANDLER_NAME)
                    await session.commit()
                    return

        # Claimed here rather than at the top of the function: the
        # IntegrityError fallback above can call session.rollback(), which
        # would wipe out an earlier claim before it's ever committed. From
        # this point on nothing in this function rolls back, so the claim
        # and the streak mutation below always commit together.
        if not await try_claim(session, event_id, STREAK_CONSUMER_HANDLER_NAME):
            return

        # 2026-08-19 fix: this event fires on *every* completed block, not
        # just the session's last one -- crediting the streak here
        # unconditionally meant the very first block clicked that day
        # (e.g. one warmup exercise) already counted as "trained today",
        # a much looser bar than count_completed_real_sessions uses for
        # periodization progression. Still claim the event above (so
        # redelivery doesn't retry this same no-op forever), just skip the
        # mutation until the block that actually finishes the session
        # fires this same handler again.
        if not await is_session_fully_completed(session, uuid.UUID(payload["session_block_id"])):
            await session.commit()
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
