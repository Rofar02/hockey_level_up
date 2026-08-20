"""Phase 5: session-level overload signal, and the two brakes it feeds.

All pure functions over already-fetched data -- the DB-querying side
(pulling a user's recent per-session feedback counts) lives in
OverloadRepository/OverloadService. Mirrors app.core.rest/
app.core.training_block's split between pure decision rules here and
DB-touching orchestration in the service layer.
"""
import enum

MIN_FEEDBACK_SETS_FOR_SIGNAL = 3
_HARD_OR_MAX_OVERLOAD_RATIO = 0.5
_MAX_ONLY_OVERLOAD_RATIO = 0.25

# Stage 2.4's own plan text (2026-08-20 planning session): a POWER-archetype
# set (Exercise.stimulus_type == StimulusType.POWER) subjectively feels
# harder than a STRENGTH set carrying the same objective load -- "one
# correction factor in the existing formula", not a separate mechanism.
# Applied in OverloadRepository.list_recent_session_feedback_counts to that
# set's contribution to hard_count/max_count before classify_session ever
# sees it (so this module doesn't need to know about exercises at all) --
# HARD/MAX feedback on a POWER set counts as half a HARD/MAX toward the
# overload ratio, not a full one. total_with_feedback (the denominator) is
# never discounted -- a POWER set still logged real feedback, this only
# softens how much a *hard-feeling* one weighs toward "you're overloaded".
POWER_DAY_FEEDBACK_DISCOUNT = 0.5


class SessionSignal(enum.Enum):
    """Ephemeral per-request classification -- never persisted, so this is
    a plain Enum, not a StrEnum/DB column type."""

    OVERLOAD = "overload"
    OK = "ok"


def classify_session(
    *, hard_count: float, max_count: float, total_with_feedback: int
) -> SessionSignal | None:
    """None when the session has too little feedback to mean anything
    (< MIN_FEEDBACK_SETS_FOR_SIGNAL) -- callers must drop it from both
    brakes' windows entirely, not treat it as a neutral/OK data point.

    hard_count/max_count are floats, not plain set-counts, since
    POWER_DAY_FEEDBACK_DISCOUNT above means a POWER-archetype set's HARD/MAX
    feedback can contribute half a "count" rather than a whole one --
    total_with_feedback stays an exact integer set-count (never discounted).
    """
    if total_with_feedback < MIN_FEEDBACK_SETS_FOR_SIGNAL:
        return None
    if (hard_count + max_count) / total_with_feedback >= _HARD_OR_MAX_OVERLOAD_RATIO:
        return SessionSignal.OVERLOAD
    if max_count / total_with_feedback >= _MAX_ONLY_OVERLOAD_RATIO:
        return SessionSignal.OVERLOAD
    return SessionSignal.OK


# -- Tactical brake: forces exercise assembly to use BlockPhase.DELOAD,
# without touching the TrainingBlock's own persisted phase/session-count
# progression (see ScheduleService/OverloadService) -- so recovery is just
# "the override stops applying", not "figure out what phase we would have
# organically been in".

TACTICAL_BRAKE_WINDOW = 2


def tactical_brake_engaged(recent_signals_newest_first: list[SessionSignal]) -> bool:
    """True iff the user's most recent TACTICAL_BRAKE_WINDOW valid-signal
    sessions are ALL overload. Cold start (fewer than that many valid-signal
    sessions exist yet) never engages -- "no data" isn't "all clear", but
    there's nothing here to trigger on either.
    """
    window = recent_signals_newest_first[:TACTICAL_BRAKE_WINDOW]
    return len(window) == TACTICAL_BRAKE_WINDOW and all(s == SessionSignal.OVERLOAD for s in window)


# -- Structural brake: a difficulty-cap throttle, persisted on
# User.difficulty_throttle_steps but re-derived fresh (not incrementally
# event-driven) every time it's needed -- see compute_difficulty_throttle_steps.

STRUCTURAL_BRAKE_WINDOW = 5
STRUCTURAL_BRAKE_THRESHOLD = 3
STRUCTURAL_RECOVERY_STREAK = 2

# How far back (in valid-signal sessions) to replay when deriving the
# current throttle level. The push rule is edge-triggered (see below), so
# throttle can only climb roughly once per genuinely distinct overload
# episode rather than every session a persistent bad streak continues --
# 50 valid-signal sessions is comfortably more history than any realistic
# accumulated throttle state needs to fully resolve.
STRUCTURAL_REPLAY_LOOKBACK = 50


def compute_difficulty_throttle_steps(signals_oldest_first: list[SessionSignal]) -> int:
    """Replays a user's ordered (oldest-first) valid-signal session history
    to derive the CURRENT throttle level, rather than maintaining it as
    separately-mutated incremental state -- there's no reliable single
    trigger point to update it exactly once per session (SetCompletion
    feedback can be logged well after a session's blocks all complete, see
    SetCompletionService.save_feedback), so recomputing fresh from history
    on every read is both simpler and correct by construction.

    The push rule (3-of-trailing-5 overload) is EDGE-triggered: it fires
    once when the condition first becomes true, not again on every later
    session for as long as it remains true -- otherwise a long unbroken bad
    stretch would throttle down without bound. A genuinely new episode
    (condition goes true again after having gone false) still pushes again,
    so persistent-but-improving patterns aren't under-counted.

    Recovery (STRUCTURAL_RECOVERY_STREAK consecutive OK sessions -> -1
    step, floored at 0) is tracked independently of the push rule -- a
    session's own signal counts toward the recovery streak even if that
    same session is also the one whose trailing window just triggered a
    push; the two are separate facts about a session (its own signal, vs.
    the 5-session window's aggregate), and the spec's recovery rule is
    about the former alone.
    """
    throttle = 0
    recovery_streak = 0
    push_condition_was_active = False

    for index, signal in enumerate(signals_oldest_first):
        window = signals_oldest_first[max(0, index - STRUCTURAL_BRAKE_WINDOW + 1) : index + 1]
        overload_in_window = sum(1 for s in window if s == SessionSignal.OVERLOAD)
        push_condition_active = (
            len(window) == STRUCTURAL_BRAKE_WINDOW and overload_in_window >= STRUCTURAL_BRAKE_THRESHOLD
        )

        if push_condition_active and not push_condition_was_active:
            throttle += 1
            recovery_streak = 0
        push_condition_was_active = push_condition_active

        if signal == SessionSignal.OK:
            recovery_streak += 1
            if recovery_streak >= STRUCTURAL_RECOVERY_STREAK:
                throttle = max(0, throttle - 1)
                recovery_streak = 0
        else:
            recovery_streak = 0

    return throttle
