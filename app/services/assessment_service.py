from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.expected_baseline import intellect_baseline
from app.config.norm_tables import score_from_value
from app.models.exercise import TargetStat
from app.models.user import FitnessTier, User
from app.repositories.progress_repository import ProgressRepository
from app.schemas.assessment import (
    AssessmentResultRead,
    AssessmentTestIn,
    OnIceAssessmentResultRead,
    OnIceAssessmentTestIn,
)

SCRATCH_STARTING_VALUE = 30.0

REASON_ASSESSMENT_INITIAL = "assessment_initial"
REASON_ASSESSMENT_RETAKE = "assessment_retake"
REASON_ONICE_ASSESSMENT_INITIAL = "onice_assessment_initial"
REASON_ONICE_ASSESSMENT_RETAKE = "onice_assessment_retake"
# Seeded alongside the off-ice stats (see _apply_assessment) so the two
# on-ice stats exist for every user right after onboarding, not only for
# those who've separately taken the real on-ice test -- otherwise the
# frontend's per-stat tiles silently have nothing to render for them (no
# UserStat row at all, not even a zero). Distinct from
# REASON_ONICE_ASSESSMENT_INITIAL: this is a placeholder default, not a
# measured result.
REASON_ONICE_BASELINE_DEFAULT = "onice_baseline_default"

REASSESSMENT_LOCKED_DETAIL = "Переоценка станет доступна в начале следующего тренировочного блока"
ONICE_REASSESSMENT_LOCKED_DETAIL = (
    "Переоценка станет доступна в начале следующего тренировочного блока"
)


class AssessmentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._progress = ProgressRepository(session)

    # -- off-ice fitness test --

    async def run_test(self, user: User, body: AssessmentTestIn) -> AssessmentResultRead:
        self._check_gate(user.has_assessment, user.suggested_reassessment, REASSESSMENT_LOCKED_DETAIL)
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
        self._check_gate(user.has_assessment, user.suggested_reassessment, REASSESSMENT_LOCKED_DETAIL)
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
        reason = REASON_ASSESSMENT_RETAKE if user.has_assessment else REASON_ASSESSMENT_INITIAL
        for stat_type, value in (
            (TargetStat.AGILITY, agility),
            (TargetStat.STRENGTH, strength),
            (TargetStat.ENDURANCE, endurance),
            (TargetStat.INTELLECT, intellect),
        ):
            await self._progress.set_stat_value(user.id, stat_type, value, now, reason)

        # The off-ice test/scratch-start doesn't measure on-ice ability --
        # this is a placeholder baseline, not a computed value. Safe on
        # every call (including retakes): ensure_stat_exists only inserts
        # once and is a no-op forever after, so it can never overwrite a
        # real run_onice_test result recorded in the meantime.
        for stat_type in (TargetStat.ON_ICE_SKATING, TargetStat.PUCK_HANDLING):
            await self._progress.ensure_stat_exists(
                user.id, stat_type, SCRATCH_STARTING_VALUE, now, REASON_ONICE_BASELINE_DEFAULT
            )

        user.fitness_tier = tier
        user.has_assessment = True
        user.suggested_reassessment = False
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

    # -- on-ice test --
    # Same gating/write pattern as the off-ice test above, kept as a
    # separate method (rather than folding into run_test) because the two
    # tests measure different stats, gate on different flags, and one day
    # will very likely be submitted from a different screen/timing than the
    # other (rink availability vs. gym availability).

    async def run_onice_test(
        self, user: User, body: OnIceAssessmentTestIn
    ) -> OnIceAssessmentResultRead:
        self._check_gate(
            user.has_onice_assessment,
            user.suggested_onice_reassessment,
            ONICE_REASSESSMENT_LOCKED_DETAIL,
        )
        if user.age is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="age is required to run the on-ice test",
            )

        on_ice_skating = float(
            score_from_value("on_ice_skating_seconds", user.age, body.on_ice_skating_seconds)
        )
        puck_handling = float(
            score_from_value("puck_handling_seconds", user.age, body.puck_handling_seconds)
        )

        now = datetime.now(timezone.utc)
        reason = (
            REASON_ONICE_ASSESSMENT_RETAKE
            if user.has_onice_assessment
            else REASON_ONICE_ASSESSMENT_INITIAL
        )
        for stat_type, value in (
            (TargetStat.ON_ICE_SKATING, on_ice_skating),
            (TargetStat.PUCK_HANDLING, puck_handling),
        ):
            await self._progress.set_stat_value(user.id, stat_type, value, now, reason)

        user.has_onice_assessment = True
        user.suggested_onice_reassessment = False
        await self._session.commit()

        return OnIceAssessmentResultRead(on_ice_skating=on_ice_skating, puck_handling=puck_handling)

    # -- shared --

    @staticmethod
    def _check_gate(has_taken: bool, suggested_retake: bool, locked_detail: str) -> None:
        # First-ever attempt (has_taken=False) is always allowed. Once
        # taken, a retake requires the block-rollover window
        # (suggested_retake, set by ScheduleService._advance_one_week) --
        # otherwise the test could be replayed on demand to silently
        # rewrite current_value at will.
        if has_taken and not suggested_retake:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=locked_detail)

    @staticmethod
    def _intellect_from_experience(user: User) -> float:
        return intellect_baseline(user.years_of_experience)

    @staticmethod
    def _tier_from_average(agility: float, strength: float, endurance: float) -> FitnessTier:
        average = (agility + strength + endurance) / 3
        if average < 40:
            return FitnessTier.BEGINNER
        if average <= 70:
            return FitnessTier.INTERMEDIATE
        return FitnessTier.ADVANCED
