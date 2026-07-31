from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.norm_tables import score_from_value
from app.models.exercise import TargetStat
from app.models.user import FitnessTier, User
from app.repositories.progress_repository import ProgressRepository
from app.schemas.assessment import AssessmentResultRead, AssessmentTestIn

SCRATCH_STARTING_VALUE = 30.0


class AssessmentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._progress = ProgressRepository(session)

    async def run_test(self, user: User, body: AssessmentTestIn) -> AssessmentResultRead:
        if user.age is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="age is required to run the fitness test",
            )

        agility = float(score_from_value("long_jump_cm", user.age, body.long_jump_cm))
        strength = float(
            round(
                (
                    score_from_value("pushups_reps", user.age, body.pushups_reps)
                    + score_from_value("squats_reps", user.age, body.squats_reps)
                )
                / 2
            )
        )
        endurance = float(
            round(
                (
                    score_from_value("plank_seconds", user.age, body.plank_seconds)
                    + score_from_value("run_1km_seconds", user.age, body.run_1km_seconds)
                )
                / 2
            )
        )
        intellect = self._intellect_from_experience(user)

        tier = self._tier_from_average(agility, strength, endurance)
        return await self._apply_assessment(user, agility, strength, endurance, intellect, tier)

    async def start_from_scratch(self, user: User) -> AssessmentResultRead:
        intellect = self._intellect_from_experience(user)
        return await self._apply_assessment(
            user,
            SCRATCH_STARTING_VALUE,
            SCRATCH_STARTING_VALUE,
            SCRATCH_STARTING_VALUE,
            intellect,
            FitnessTier.BEGINNER,
        )

    async def _apply_assessment(
        self,
        user: User,
        agility: float,
        strength: float,
        endurance: float,
        intellect: float,
        tier: FitnessTier,
    ) -> AssessmentResultRead:
        now = datetime.now(timezone.utc)
        for stat_type, value in (
            (TargetStat.AGILITY, agility),
            (TargetStat.STRENGTH, strength),
            (TargetStat.ENDURANCE, endurance),
            (TargetStat.INTELLECT, intellect),
        ):
            await self._progress.set_stat_value(user.id, stat_type, value, now)

        user.fitness_tier = tier
        user.has_assessment = True
        await self._session.commit()

        return AssessmentResultRead(
            agility=agility,
            strength=strength,
            endurance=endurance,
            intellect=intellect,
            fitness_tier=tier,
        )

    async def dismiss_reassessment_suggestion(self, user: User) -> None:
        user.suggested_reassessment = False
        await self._session.commit()

    @staticmethod
    def _intellect_from_experience(user: User) -> float:
        years = user.years_of_experience or 0
        return float(40 + min(years * 3, 40))

    @staticmethod
    def _tier_from_average(agility: float, strength: float, endurance: float) -> FitnessTier:
        average = (agility + strength + endurance) / 3
        if average < 40:
            return FitnessTier.BEGINNER
        if average <= 70:
            return FitnessTier.INTERMEDIATE
        return FitnessTier.ADVANCED
