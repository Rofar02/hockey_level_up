""""Путь новичка" (2026-10-08): a short checklist on the home screen that
walks a new player through the one main loop -- plan, workout, report,
coach, team -- with XP for each step. Every task is read off what the player
actually did (no "mark as done" buttons), so it completes itself.

XP once per task: User.onboarding_state["claimed"] lists the paid ones. On
the first sync an account older than VETERAN_AFTER gets everything it has
already done claimed silently -- the checklist isn't a bonus for history.
The card hides once everything is claimed or the player dismissed it.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.coach_chat import CoachChatMessage, CoachChatRole
from app.models.friend import FriendRequest, FriendRequestStatus
from app.models.schedule import DayPlan, SessionBlock, TrainingSession, WeeklyPlan
from app.models.team import TeamMembership
from app.models.training_diary import TrainingDiaryEntry
from app.models.user import User
from app.schemas.onboarding import OnboardingRead, OnboardingTaskRead
from app.services.stat_award import award_xp

VETERAN_AFTER = timedelta(days=7)
FINISH_BONUS_XP = 50


@dataclass(frozen=True)
class OnboardingTask:
    id: str
    title: str
    hint: str
    xp: int
    # In-app path the task's row opens.
    to: str


TASKS: tuple[OnboardingTask, ...] = (
    OnboardingTask("plan_week", "Составьте первую неделю", "Отметьте лёд, игры и зал", 20, "/schedule/new"),
    OnboardingTask("first_workout", "Проведите первую тренировку", "Начните с экрана «Сегодня»", 30, "/"),
    OnboardingTask("three_workouts", "Проведите три тренировки", "Статы растут от регулярности", 40, "/"),
    OnboardingTask("first_report", "Отчитайтесь после льда или игры", "Пара тапов — и растут катание и интеллект", 30, "/diary"),
    OnboardingTask("ask_coach", "Задайте вопрос тренеру", "Он знает ваш план и статы", 20, "/coach"),
    OnboardingTask("join_team", "Вступите в команду или добавьте друга", "Вместе тренироваться интереснее", 20, "/team"),
)


class OnboardingService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def sync(self, user: User) -> OnboardingRead:
        """Checks every task, pays the newly done ones (and the finish
        bonus once all are), and returns the card's state."""
        state = dict(user.onboarding_state or {})
        claimed: list[str] = list(state.get("claimed", []))
        done = await self._done_tasks(user)

        first_sync = not state.get("seen", False)
        is_veteran = user.created_at is not None and datetime.now(timezone.utc) - user.created_at > VETERAN_AFTER
        newly: list[str] = []
        for task in TASKS:
            if task.id in done and task.id not in claimed:
                claimed.append(task.id)
                if not (first_sync and is_veteran):
                    newly.append(task.id)

        xp = sum(task.xp for task in TASKS if task.id in newly)
        all_done = all(task.id in claimed for task in TASKS)
        bonus = 0
        if all_done and not state.get("finished", False):
            state["finished"] = True
            bonus = 0 if (first_sync and is_veteran) else FINISH_BONUS_XP
        if xp + bonus > 0:
            await award_xp(self._session, user.id, xp + bonus)

        state.update(seen=True, claimed=claimed)
        user.onboarding_state = state
        await self._session.commit()
        return OnboardingRead(
            visible=not all_done and not state.get("dismissed", False),
            tasks=[
                OnboardingTaskRead(
                    id=task.id, title=task.title, hint=task.hint, xp=task.xp, to=task.to, done=task.id in claimed
                )
                for task in TASKS
            ],
            newly_done=newly,
            xp_awarded=xp + bonus,
            finish_bonus_xp=FINISH_BONUS_XP,
        )

    async def dismiss(self, user: User) -> None:
        user.onboarding_state = {**(user.onboarding_state or {}), "dismissed": True}
        await self._session.commit()

    async def _done_tasks(self, user: User) -> set[str]:
        done: set[str] = set()
        if await self._exists(select(WeeklyPlan.id).where(WeeklyPlan.user_id == user.id)):
            done.add("plan_week")
        workouts = await self._session.scalar(
            select(func.count(func.distinct(TrainingSession.id)))
            .join(SessionBlock, SessionBlock.session_id == TrainingSession.id)
            .join(DayPlan, DayPlan.id == TrainingSession.day_plan_id)
            .join(WeeklyPlan, WeeklyPlan.id == DayPlan.weekly_plan_id)
            .where(WeeklyPlan.user_id == user.id, SessionBlock.completed_at.isnot(None))
        )
        if workouts >= 1:
            done.add("first_workout")
        if workouts >= 3:
            done.add("three_workouts")
        if await self._exists(
            select(TrainingDiaryEntry.id).where(
                TrainingDiaryEntry.user_id == user.id,
                TrainingDiaryEntry.reported_at.isnot(None),
                TrainingDiaryEntry.skipped.is_(False),
            )
        ):
            done.add("first_report")
        if await self._exists(
            select(CoachChatMessage.id).where(
                CoachChatMessage.user_id == user.id, CoachChatMessage.role == CoachChatRole.USER
            )
        ):
            done.add("ask_coach")
        if await self._exists(
            select(TeamMembership.id).where(TeamMembership.user_id == user.id)
        ) or await self._exists(
            select(FriendRequest.id).where(
                FriendRequest.status == FriendRequestStatus.ACCEPTED,
                or_(FriendRequest.sender_id == user.id, FriendRequest.receiver_id == user.id),
            )
        ):
            done.add("join_team")
        return done

    async def _exists(self, query) -> bool:
        return await self._session.scalar(query.limit(1)) is not None
