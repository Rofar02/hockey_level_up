# Expected stat baseline for a user's age + experience, used to turn raw
# stat values into a fair "excess over expectation" competitive rating (see
# ProgressService.get_stat_excess) -- curated calibration, not user data.

from app.config.norm_tables import age_group
from app.models.exercise import TargetStat

AGE_BASELINE: dict[str, float] = {
    "18-29": 40.0,
    "30-39": 38.0,
    "40-49": 35.0,
    "50+": 30.0,
}

EXPERIENCE_BONUS_PER_YEAR = 1.5
EXPERIENCE_BONUS_CAP = 30.0

# Same base/rate as AssessmentService's starting-intellect formula -- kept
# here as the single source of truth, AssessmentService delegates to it.
INTELLECT_BASE = 30.0
INTELLECT_BONUS_PER_YEAR = 2.0
INTELLECT_BONUS_CAP = 30.0


def experience_bonus(years: float) -> float:
    return min(years * EXPERIENCE_BONUS_PER_YEAR, EXPERIENCE_BONUS_CAP)


def intellect_baseline(years_of_experience: float | None) -> float:
    years = years_of_experience or 0
    return INTELLECT_BASE + min(years * INTELLECT_BONUS_PER_YEAR, INTELLECT_BONUS_CAP)


def get_expected_baseline(
    stat_type: TargetStat, age: int, years_of_experience: float | None
) -> float:
    if stat_type == TargetStat.INTELLECT:
        return intellect_baseline(years_of_experience)
    years = years_of_experience or 0
    return AGE_BASELINE[age_group(age)] + experience_bonus(years)
