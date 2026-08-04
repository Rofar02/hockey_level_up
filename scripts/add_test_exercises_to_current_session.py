"""One-off helper: append the SetCompletion end-to-end test exercises to a
user's *already-existing* current training session, instead of generating a
whole new week from scratch.

Why not just re-plan the week and hope they show up: ScheduleService._pick_main
picks at most one exercise per target_stat, at random, from *all* matching
candidates (phase=main, category, equipment) -- see app/services/schedule_service.py.
Having these exercises in the catalog does not make them likely to be picked
over every other strength-tagged off_ice/gym exercise already seeded. This
script instead appends them directly as extra SessionBlock rows on top of
whatever the user's current session already has, guaranteeing they're there
to click through.

Requires:
  - the exercises already seeded (run scripts/seed_exercises.py first)
  - the target user to already have a current WeeklyPlan with at least one
    non-rest day today or later this week (plan a week via the app/API
    first if not -- this script does not create weeks or days, only appends
    SessionBlock rows to an existing TrainingSession)

Usage:
    poetry run python scripts/add_test_exercises_to_current_session.py <email>

Idempotent: skips any of the test exercises already present as a block in
that day's session.
"""
import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import Exercise  # noqa: E402
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingSession, WeeklyPlan  # noqa: E402
from app.models.user import User  # noqa: E402

TEST_EXERCISE_NAMES = [
    "Приседания со штангой",
    "Жим гантелей лёжа",
    "Планка",
    "Растяжка",
    "Румынская тяга",
]


async def seed(email: str) -> None:
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None:
            print(f"No user with email {email!r}.")
            return

        today = date.today()
        weekly_plan = (
            await session.execute(
                select(WeeklyPlan)
                .where(WeeklyPlan.user_id == user.id, WeeklyPlan.week_start_date <= today)
                .options(
                    selectinload(WeeklyPlan.day_plans)
                    .selectinload(DayPlan.training_session)
                    .selectinload(TrainingSession.blocks)
                )
                .order_by(WeeklyPlan.week_start_date.desc())
            )
        ).unique().scalars().first()
        if weekly_plan is None:
            print("No current weekly plan for this user -- plan a week first (POST /schedule/weekly).")
            return

        day_plan = next(
            (
                day
                for day in sorted(weekly_plan.day_plans, key=lambda d: d.date)
                if day.date >= today
                and day.session_type != DaySessionType.REST
                and day.training_session is not None
            ),
            None,
        )
        if day_plan is None:
            print("No non-rest day with a training session today or later in the current week.")
            return

        exercises_by_name = dict(
            (
                await session.execute(
                    select(Exercise.name, Exercise).where(Exercise.name.in_(TEST_EXERCISE_NAMES))
                )
            ).all()
        )
        missing = [name for name in TEST_EXERCISE_NAMES if name not in exercises_by_name]
        if missing:
            print(f"WARNING: not found, run scripts/seed_exercises.py first: {missing}")

        training_session = day_plan.training_session
        existing_exercise_ids = {block.exercise_id for block in training_session.blocks}
        next_order = max((block.order for block in training_session.blocks), default=-1) + 1

        added = 0
        for name in TEST_EXERCISE_NAMES:
            exercise = exercises_by_name.get(name)
            if exercise is None or exercise.id in existing_exercise_ids:
                continue
            session.add(
                SessionBlock(
                    session_id=training_session.id,
                    phase=exercise.phase,
                    exercise_id=exercise.id,
                    order=next_order,
                )
            )
            next_order += 1
            added += 1

        await session.commit()
        print(f"Added {added} test exercise block(s) to {day_plan.date} for {email}.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: poetry run python scripts/add_test_exercises_to_current_session.py <email>")
        sys.exit(1)
    asyncio.run(seed(sys.argv[1]))
