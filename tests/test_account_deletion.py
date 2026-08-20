"""DELETE /users/me (UserService.delete_account): password re-confirmation
gate, then verifying every table with a user_id/transitive FK is actually
gone -- this exercises the ON DELETE CASCADE chain configured on the DB
side (see app/models/*.py), not application-level per-table deletes, so the
point of these tests is to catch a table that's missing CASCADE just as much
as a bug in the service method itself.
"""
import uuid
from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.exercise import (
    Exercise,
    ExerciseCategory,
    ExerciseTargetStat,
    TargetStat,
    TrainingPhase,
)
from app.models.progress import StatHistory, TrainingStreak, UserStat
from app.models.push_subscription import PushSubscription
from app.models.schedule import DayPlan, DaySessionType, SessionBlock, TrainingBlock, TrainingSession, WeeklyPlan
from app.models.set_completion import SetCompletion
from app.models.skill import Skill, UserSkillPreference
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.user_service import UserService

PASSWORD = "correct-horse-battery"


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"del_{unique}",
        email=f"del_{unique}@example.com",
        password_hash=hash_password(PASSWORD),
    )


async def _seed_full_graph(db_session, user: User) -> dict:
    """Attach one row in every user-linked table (directly or transitively
    through the schedule tree) so deletion can be checked table-by-table."""
    exercise = Exercise(
        id=uuid.uuid4(),
        name=f"Exercise {uuid.uuid4().hex[:8]}",
        category=ExerciseCategory.OFF_ICE,
        phase=TrainingPhase.MAIN,
        difficulty_level=3,
    )
    exercise_target_stat = ExerciseTargetStat(
        exercise_id=exercise.id, target_stat=TargetStat.STRENGTH, order=0
    )
    skill = Skill(id=uuid.uuid4(), name=f"Skill {uuid.uuid4().hex[:8]}")
    db_session.add_all([exercise, exercise_target_stat, skill])
    await db_session.flush()

    session_block = SessionBlock(
        id=uuid.uuid4(), phase=TrainingPhase.MAIN, exercise_id=exercise.id, order=0
    )
    training_session = TrainingSession(id=uuid.uuid4(), blocks=[session_block])
    day_plan = DayPlan(
        id=uuid.uuid4(),
        date=date.today(),
        session_type=DaySessionType.OFF_ICE,
        training_session=training_session,
    )
    weekly_plan = WeeklyPlan(
        id=uuid.uuid4(), user_id=user.id, week_start_date=date.today(), day_plans=[day_plan]
    )
    training_block = TrainingBlock(id=uuid.uuid4(), user_id=user.id, block_number=1)
    user_stat = UserStat(id=uuid.uuid4(), user_id=user.id, stat_type=TargetStat.STRENGTH)
    stat_history = StatHistory(
        id=uuid.uuid4(),
        user_id=user.id,
        stat_type=TargetStat.STRENGTH,
        value=10.0,
        reason="test",
    )
    training_streak = TrainingStreak(id=uuid.uuid4(), user_id=user.id)
    user_skill_preference = UserSkillPreference(
        id=uuid.uuid4(), user_id=user.id, skill_id=skill.id
    )
    push_subscription = PushSubscription(
        id=uuid.uuid4(),
        user_id=user.id,
        endpoint=f"https://push.example.com/{uuid.uuid4().hex}",
        p256dh_key="p256dh",
        auth_key="auth",
    )
    db_session.add_all(
        [
            weekly_plan,
            training_block,
            user_stat,
            stat_history,
            training_streak,
            user_skill_preference,
            push_subscription,
        ]
    )
    await db_session.flush()

    set_completion = SetCompletion(
        id=uuid.uuid4(),
        user_id=user.id,
        exercise_id=exercise.id,
        training_session_id=training_session.id,
        set_number=1,
    )
    db_session.add(set_completion)
    await db_session.flush()

    return {
        "weekly_plan_id": weekly_plan.id,
        "day_plan_id": day_plan.id,
        "training_session_id": training_session.id,
        "session_block_id": session_block.id,
        "training_block_id": training_block.id,
        "user_stat_id": user_stat.id,
        "stat_history_id": stat_history.id,
        "training_streak_id": training_streak.id,
        "user_skill_preference_id": user_skill_preference.id,
        "push_subscription_id": push_subscription.id,
        "set_completion_id": set_completion.id,
        "exercise_id": exercise.id,
    }


@pytest.mark.asyncio
async def test_delete_account_without_password_returns_400(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await UserService(db_session).delete_account(user, "")

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_account_with_wrong_password_returns_403(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await UserService(db_session).delete_account(user, "not-the-password")

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_delete_account_with_correct_password_removes_all_related_rows(db_session) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    ids = await _seed_full_graph(db_session, user)

    upload_dir = Path(get_settings().avatar_upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    avatar_filename = f"{uuid.uuid4().hex}.png"
    avatar_path = upload_dir / avatar_filename
    avatar_path.write_bytes(b"not-a-real-image")
    user.avatar_path = avatar_filename
    await db_session.flush()

    user_id = user.id

    await UserService(db_session).delete_account(user, PASSWORD)

    # The rows below were removed by Postgres's ON DELETE CASCADE, not
    # through the ORM's unit of work, so the still-open session's identity
    # map doesn't know about it -- session.get() would otherwise happily
    # hand back the stale in-memory objects instead of re-querying. Clearing
    # the identity map (no DB interaction itself) forces every .get() below
    # to hit the database fresh.
    db_session.expunge_all()

    assert await db_session.get(User, user_id) is None
    assert await db_session.get(WeeklyPlan, ids["weekly_plan_id"]) is None
    assert await db_session.get(DayPlan, ids["day_plan_id"]) is None
    assert await db_session.get(TrainingSession, ids["training_session_id"]) is None
    assert await db_session.get(SessionBlock, ids["session_block_id"]) is None
    assert await db_session.get(TrainingBlock, ids["training_block_id"]) is None
    assert await db_session.get(UserStat, ids["user_stat_id"]) is None
    assert await db_session.get(StatHistory, ids["stat_history_id"]) is None
    assert await db_session.get(TrainingStreak, ids["training_streak_id"]) is None
    assert await db_session.get(UserSkillPreference, ids["user_skill_preference_id"]) is None
    assert await db_session.get(PushSubscription, ids["push_subscription_id"]) is None
    assert await db_session.get(SetCompletion, ids["set_completion_id"]) is None
    # Exercise itself is curated content, not user data -- must survive.
    assert await db_session.get(Exercise, ids["exercise_id"]) is not None

    assert not avatar_path.exists()

    # Re-login must be impossible: the username no longer resolves to a row.
    assert await UserRepository(db_session).get_by_username(user.username) is None
    with pytest.raises(HTTPException) as exc_info:
        await AuthService(db_session).authenticate(user.username, PASSWORD)
    assert exc_info.value.status_code == 401
