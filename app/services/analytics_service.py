import uuid
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import TargetStat
from app.models.user import User
from app.repositories.progress_repository import ProgressRepository
from app.repositories.skill_repository import SkillRepository
from app.schemas.analytics import AnalyticsMilestoneRead, AnalyticsMoverRead, AnalyticsSummaryRead
from app.schemas.skill import NextMilestoneRead
from app.services.skill_service import SkillService
from app.services.stat_service import (
    get_effective_value,
    get_idle_days,
    get_stat_value_at_from_history,
    is_decay_active,
)

# The only decline explanation this can honestly attribute from real data --
# a genuinely lower assessment retake, for instance, has no signal to point
# to, so decline_reason stays None rather than inventing one (see the task
# note: "если явной причины нет -- оставь null, не выдумывай").
DECLINE_REASON_DECAY = "Давно не было тренировок этого типа."


class _Candidate(NamedTuple):
    """Exactly one of stat_type/skill_id is set -- which one tells
    _decline_reason how to look up the underlying decay state."""

    mover: AnalyticsMoverRead
    stat_type: TargetStat | None
    skill_id: uuid.UUID | None


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self._progress = ProgressRepository(session)
        self._skills_repo = SkillRepository(session)
        self._skills = SkillService(session)

    async def get_summary(self, user: User, days: int) -> AnalyticsSummaryRead:
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=days)

        candidates = await self._stat_candidates(user.id, since, now)
        candidates += await self._skill_candidates(user.id, since)

        # Always present (never null in the response schema) -- with 6
        # TargetStat entries always in the pool, there's always a max, even
        # if it's 0 or negative for a user with nothing but decline this
        # window.
        top_gainer_candidate = max(candidates, key=lambda c: c.mover.delta)

        # Only real declines count, and the top gainer's own entity is
        # excluded so the summary never reads as "X grew the most... and
        # also declined the most" for the same stat/skill.
        decline_pool = [
            c for c in candidates if c.mover.delta < 0 and c is not top_gainer_candidate
        ]
        top_decliner_candidate = min(decline_pool, key=lambda c: c.mover.delta) if decline_pool else None

        decline_reason = None
        if top_decliner_candidate is not None:
            decline_reason = await self._decline_reason(user.id, top_decliner_candidate, now)

        return AnalyticsSummaryRead(
            top_gainer=top_gainer_candidate.mover,
            top_decliner=top_decliner_candidate.mover if top_decliner_candidate is not None else None,
            closest_to_milestone=await self._closest_to_milestone(user.id),
            decline_reason=decline_reason,
        )

    async def _stat_candidates(
        self, user_id: uuid.UUID, since: datetime, now: datetime
    ) -> list[_Candidate]:
        candidates = []
        for stat_type in TargetStat:
            stat = await self._progress.get_user_stat(user_id, stat_type)
            current_value = get_effective_value(stat, now) if stat is not None else 0.0
            history = await self._progress.list_stat_history(user_id, stat_type)
            baseline_value = get_stat_value_at_from_history(stat_type, history, since)
            candidates.append(
                _Candidate(
                    mover=AnalyticsMoverRead(
                        name=stat_type.value,
                        type="stat",
                        delta=current_value - baseline_value,
                        current_value=current_value,
                    ),
                    stat_type=stat_type,
                    skill_id=None,
                )
            )
        return candidates

    async def _skill_candidates(self, user_id: uuid.UUID, since: datetime) -> list[_Candidate]:
        skills = await self._skills_repo.list_skills()
        candidates = []
        for skill in skills:
            current_value = await self._skills.get_skill_value(skill.id, user_id)
            baseline_value = await self._skills.get_skill_value_at(skill.id, user_id, since)
            candidates.append(
                _Candidate(
                    mover=AnalyticsMoverRead(
                        name=skill.name,
                        type="skill",
                        delta=current_value - baseline_value,
                        current_value=current_value,
                    ),
                    stat_type=None,
                    skill_id=skill.id,
                )
            )
        return candidates

    async def _decline_reason(
        self, user_id: uuid.UUID, candidate: _Candidate, now: datetime
    ) -> str | None:
        if candidate.stat_type is not None:
            return await self._stat_decay_reason(user_id, candidate.stat_type, now)
        if candidate.skill_id is not None:
            # A skill has no decay state of its own -- if any stat it's
            # weighted on is currently decaying, that's the honest
            # explanation for the skill's own decline too.
            weights = await self._skills_repo.list_stat_weights(candidate.skill_id)
            for weight in weights:
                reason = await self._stat_decay_reason(user_id, weight.stat_type, now)
                if reason is not None:
                    return reason
        return None

    async def _stat_decay_reason(
        self, user_id: uuid.UUID, stat_type: TargetStat, now: datetime
    ) -> str | None:
        stat = await self._progress.get_user_stat(user_id, stat_type)
        if stat is not None and is_decay_active(get_idle_days(stat, now), stat_type):
            return DECLINE_REASON_DECAY
        return None

    async def _closest_to_milestone(self, user_id: uuid.UUID) -> AnalyticsMilestoneRead | None:
        # Same selection HomePage's "Ближайшие пороги" card uses on the
        # frontend (topSkillsNearMilestone: filter to an open milestone,
        # pick the smallest points_remaining) -- just the single closest
        # one, computed here instead of reimplemented client-side.
        skills = await self._skills.list_skills_for_user(user_id)
        open_milestones: list[tuple[str, NextMilestoneRead]] = [
            (skill.name, skill.next_milestone) for skill in skills if skill.next_milestone is not None
        ]
        if not open_milestones:
            return None
        closest_name, closest_milestone = min(
            open_milestones, key=lambda pair: pair[1].points_remaining
        )
        return AnalyticsMilestoneRead(
            skill_name=closest_name,
            points_remaining=closest_milestone.points_remaining,
            threshold=closest_milestone.threshold,
        )
