"""The week and the ice (2026-10-09, release plan step 5).

5.1, at generation: a gym day straight after an ice day or a game gets
light legs -- lower-body strength goes technical (the SKILL archetype, as
on a deload) and no sprint/jump locomotion as the explosive pick -- as long
as the week keeps at least one gym day with full legs.

5.2, the reaction to real load: after an ice day or a game, when a leg
muscle is clearly over the player's own habit and a gym day with heavy
legs is coming within 48 hours, the week would be changed. For now this
only runs in shadow mode -- it logs what it would do and changes nothing
(WEEK_LOAD_REACTION_ENABLED in config stays off until the log has been
reviewed and the year simulation rerun).
"""
from collections.abc import Iterable
from datetime import date, timedelta

from app.models.exercise import MuscleGroup
from app.models.schedule import DaySessionType

ICE_LIKE: frozenset[DaySessionType] = frozenset({DaySessionType.ON_ICE, DaySessionType.GAME})

# 5.2 thresholds.
LEG_MUSCLES: tuple[MuscleGroup, ...] = (MuscleGroup.GLUTES, MuscleGroup.QUADS)
ACUTE_WINDOW_HOURS = 48
HABITUAL_WINDOW_DAYS = 28
ACUTE_OVER_HABITUAL = 1.5
ACUTE_MINIMUM = 5.0
HEAVY_PLANNED_LOAD = 4.0
LOOKAHEAD_HOURS = 48


def light_legs_dates(days: Iterable[tuple[date, DaySessionType]]) -> set[date]:
    """Gym days of the week to build with light legs: the day after ice or
    a game. When every gym day of the week is right after ice, the first
    one keeps full legs -- legs at least once a week, always."""
    by_date = dict(days)
    gym_days = sorted(d for d, kind in by_date.items() if kind == DaySessionType.OFF_ICE)
    after_ice = [d for d in gym_days if by_date.get(d - timedelta(days=1)) in ICE_LIKE]
    if not after_ice:
        return set()
    if len(after_ice) == len(gym_days):
        return set(after_ice[1:])
    return set(after_ice)


def is_overloaded(acute: float, habitual: float) -> bool:
    """5.2: a muscle clearly over the player's own habit -- relative, so a
    student skating four times a week isn't "overloaded" by ice."""
    return acute >= ACUTE_MINIMUM and acute >= ACUTE_OVER_HABITUAL * habitual
