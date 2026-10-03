import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import Exercise, ExerciseType, StimulusType, TrainingPhase
from app.models.set_completion import SetFeedback
from app.models.user import User
from app.repositories.set_completion_repository import SetCompletionRepository
from app.repositories.training_block_repository import TrainingBlockRepository

# Double progression (Phase: П.1): how many more reps to suggest than last
# time, when the user didn't hit the top of the range with easy/normal
# feedback (that case resets to rep_range_min instead -- see
# suggest_reps). Fills in the handoff spec's "1-2 more reps" as a concrete,
# feedback-scaled rule: felt fine but hadn't hit the top yet -> push by 2;
# felt hard -> push by 1; felt maximal -> don't push further at all; no
# feedback recorded yet -> conservative +1.
_REPS_BUMP_BY_FEEDBACK: dict[SetFeedback | None, int] = {
    SetFeedback.EASY: 2,
    SetFeedback.NORMAL: 2,
    SetFeedback.HARD: 1,
    SetFeedback.MAX: 0,
    None: 1,
}


# Time progression (2026-10-03): the same double-progression idea for
# timed strength holds (planks, hangs, isometrics) -- seconds instead of
# reps. Starts at target_duration_seconds, never goes below it, ceiling at
# DURATION_CEILING_FACTOR times it. Endurance work is excluded on purpose:
# there the catalog itself progresses by difficulty level (6 km run is
# level 1, 8 km level 2, ...), and skill/power drills are about quality and
# speed, not longer work.
DURATION_STEP_SECONDS = 5
DURATION_CEILING_FACTOR = 2
_DURATION_BUMP_BY_FEEDBACK: dict[SetFeedback | None, int] = {
    SetFeedback.EASY: 10,
    SetFeedback.NORMAL: 5,
    SetFeedback.HARD: 0,
    SetFeedback.MAX: -5,
    None: 0,
}


def has_time_progression(exercise: Exercise) -> bool:
    return (
        exercise.exercise_type == ExerciseType.DURATION
        and exercise.phase == TrainingPhase.MAIN
        and exercise.stimulus_type == StimulusType.STRENGTH
        and bool(exercise.target_duration_seconds)
    )


def _round_down_to_step(seconds: int) -> int:
    return seconds - seconds % DURATION_STEP_SECONDS


def _has_rep_range(exercise: Exercise) -> bool:
    return (
        exercise.exercise_type == ExerciseType.SETS_REPS
        and exercise.rep_range_min is not None
        and exercise.rep_range_max is not None
    )


class RepsSuggestionService:
    def __init__(self, session: AsyncSession) -> None:
        self._sets = SetCompletionRepository(session)
        self._blocks = TrainingBlockRepository(session)

    async def suggest_reps(self, user: User, exercise: Exercise) -> int | None:
        if not _has_rep_range(exercise):
            return None

        if await self._is_macrocycle_deload(user.id):
            # Floor regardless of history -- same whether this is the
            # user's first-ever set or their hundredth, so this skips the
            # SetCompletion lookups entirely (Phase: П.2).
            return exercise.rep_range_min

        last_set = await self._sets.get_last_for_user_exercise(user.id, exercise.id)
        if last_set is None:
            return exercise.rep_range_min

        if last_set.reps_completed is None:
            return exercise.rep_range_min

        last_session_sets = await self._sets.list_for_session_exercise(
            last_set.training_session_id, exercise.id
        )
        hit_top = bool(last_session_sets) and all(
            s.reps_completed is not None and s.reps_completed >= exercise.rep_range_max
            for s in last_session_sets
        )
        good_feedback = last_set.feedback in (SetFeedback.EASY, SetFeedback.NORMAL)

        if hit_top and good_feedback:
            return exercise.rep_range_min

        bump = _REPS_BUMP_BY_FEEDBACK[last_set.feedback]
        suggested = last_set.reps_completed + bump
        return max(exercise.rep_range_min, min(suggested, exercise.rep_range_max))

    async def is_stuck_at_ceiling(self, user: User, exercise: Exercise) -> bool:
        """Stage 2.6 (2026-08-20 planning session): the "hit the top of the
        range with good feedback" branch above hands off to
        WeightSuggestionService in the normal case -- raise weight, reps
        reset back down. For a tracks_weight=false exercise that handoff
        goes nowhere (suggest_weight returns None outright for those), so
        reps alone would otherwise just cycle at rep_range_max forever with
        no further progression. Same signal as suggest_reps's own reset
        branch, exposed standalone so ScheduleService._pick_main can react
        to it (break the variant pin, prefer a harder same-pattern
        candidate) instead of this service silently looping in place.
        Deliberately doesn't check tracks_weight itself -- meaningful only
        in that context, so it's the caller's job to ask at the right time.
        """
        if has_time_progression(exercise):
            return await self.is_duration_stuck_at_ceiling(user, exercise)
        if not _has_rep_range(exercise):
            return False

        last_set = await self._sets.get_last_for_user_exercise(user.id, exercise.id)
        if last_set is None or last_set.reps_completed is None:
            return False

        last_session_sets = await self._sets.list_for_session_exercise(
            last_set.training_session_id, exercise.id
        )
        hit_top = bool(last_session_sets) and all(
            s.reps_completed is not None and s.reps_completed >= exercise.rep_range_max
            for s in last_session_sets
        )
        good_feedback = last_set.feedback in (SetFeedback.EASY, SetFeedback.NORMAL)
        return hit_top and good_feedback

    async def _last_session_durations(
        self, user: User, exercise: Exercise
    ) -> tuple[list[int], SetFeedback | None] | None:
        """Seconds actually held in each round of the last session of this
        exercise, plus that session's feedback (saved on its last set).
        None when there is no usable history."""
        last_set = await self._sets.get_last_for_user_exercise(user.id, exercise.id)
        if last_set is None:
            return None
        rounds = await self._sets.list_for_session_exercise(last_set.training_session_id, exercise.id)
        held = [s.duration_seconds_completed for s in rounds if s.duration_seconds_completed]
        if not held:
            return None
        return held, last_set.feedback

    async def suggest_duration(self, user: User, exercise: Exercise) -> int | None:
        """Seconds per round for a timed strength hold. Every round held as
        long as the previous session's longest one counts as "done in full"
        (the timer logs the full target when it simply runs out; an early
        stop logs less), and then feedback moves it by +10/+5/0/-5 s. A
        round cut short means the next target is what was actually held,
        rounded down to 5 s. Always within [target, target * 2]; a
        macrocycle deload goes back to the start value."""
        if not has_time_progression(exercise):
            return None
        base = exercise.target_duration_seconds
        assert base is not None
        if await self._is_macrocycle_deload(user.id):
            return base
        last = await self._last_session_durations(user, exercise)
        if last is None:
            return base
        held, feedback = last
        weakest = min(held)
        if weakest >= max(held):
            suggested = _round_down_to_step(weakest + _DURATION_BUMP_BY_FEEDBACK[feedback])
        else:
            suggested = _round_down_to_step(weakest)
        return max(base, min(suggested, base * DURATION_CEILING_FACTOR))

    async def is_duration_stuck_at_ceiling(self, user: User, exercise: Exercise) -> bool:
        """Every round of the last session held for the full ceiling (2x the
        start value) with easy/normal feedback -- the timed counterpart of
        is_stuck_at_ceiling, used the same way: time to a harder variant."""
        if not has_time_progression(exercise):
            return False
        last = await self._last_session_durations(user, exercise)
        if last is None:
            return False
        held, feedback = last
        ceiling = exercise.target_duration_seconds * DURATION_CEILING_FACTOR
        return min(held) >= ceiling and feedback in (SetFeedback.EASY, SetFeedback.NORMAL)

    async def _is_macrocycle_deload(self, user_id: uuid.UUID) -> bool:
        """Phase: П.2. Pure read, see WeightSuggestionService._active_macrocycle_deload_block."""
        block = await self._blocks.get_active_for_user(user_id)
        return block is not None and block.is_macrocycle_deload
