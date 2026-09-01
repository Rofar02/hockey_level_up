import { useEffect, useRef, useState } from 'react'
import { CountdownRing } from './ui/CountdownRing'
import { Stepper } from './ui/Stepper'
import { ExerciseFeedbackPrompt } from './ExerciseFeedbackPrompt'
import * as progressApi from '../api/progress'
import * as setCompletionsApi from '../api/setCompletions'
import type { ExerciseRead } from '../types/exercise'
import {
  alertTimerDone,
  ensureNotificationPermission,
  scheduleRestDoneNotification,
  type ScheduledRestNotification,
} from '../utils/restNotification'

// Fallback rest between rounds when the exercise has no configured
// rest_seconds -- preserves the old always-advances behavior instead of
// skipping straight to the next round with zero pause.
const FALLBACK_REST_SECONDS = 3

// Mode A ("на время") -- one CountdownRing that IS the player (media-player
// redesign, 2026-08-28: "хочу чтобы это было прям как медиаплеер"). Tapping
// the ring itself starts/pauses a round; the same ring switches to a
// persimmon "Отдых" state between rounds using the exercise's real
// rest_seconds, then auto-continues into the next round -- no separate
// button, no fake pause-with-cancel.
export function TimerPlayer({
  exercise,
  trainingSessionId,
  accessToken,
  durationSeconds,
  rounds,
  isDone,
  onComplete,
  onSettled,
}: {
  exercise: ExerciseRead
  trainingSessionId: string
  accessToken: string
  durationSeconds: number
  rounds: number
  isDone: boolean
  onComplete?: () => void
  // Fires once the post-completion feedback prompt is answered -- see
  // ExerciseDetailBodyProps' own comment for how this differs from
  // onComplete (which fires earlier, right as the last round finishes).
  onSettled?: () => void
}) {
  const [completedRounds, setCompletedRounds] = useState(0)
  const [phase, setPhase] = useState<'work' | 'rest'>('work')
  const [remaining, setRemaining] = useState(durationSeconds)
  const [running, setRunning] = useState(false)
  // Honest-fact override for the round currently paused mid-count (referencing
  // a competitor's flow the athlete asked to bring over, 2026-08-31): null
  // means "not paused mid-round" (either still running, or never started).
  // Set to the elapsed seconds the instant the ring is paused, so the
  // athlete can confirm early with what they actually did instead of only
  // ever being able to log the full target duration -- editable via the
  // Stepper below before confirming, same "suggestion, not a mandate"
  // pattern SetLogger's reps/weight steppers already use.
  const [manualSeconds, setManualSeconds] = useState<number | null>(null)
  // Flips once the last round finishes -- gates the "Как ощущения?" prompt
  // below. Deliberately local-only (not derived from `isDone`): `isDone`
  // covers reopening an exercise that was ALREADY completed on a previous
  // visit, which must never re-show the prompt or re-fire onSettled.
  const [showFeedback, setShowFeedback] = useState(false)
  // Separate from showFeedback -- found live-testing this exact flow
  // (2026-08-28): when this is the LAST exercise in its phase,
  // handleExerciseSettled has nowhere to advance to, so this component
  // never unmounts and showFeedback never resets. Without this flag the
  // answered prompt just sat there, still tappable, instead of settling
  // into a plain "Готово" like SetLogger's own (`feedback !== null`)
  // read-only branch already does for the exact same last-exercise case.
  const [feedbackAnswered, setFeedbackAnswered] = useState(false)
  const onCompleteRef = useRef(onComplete)
  onCompleteRef.current = onComplete
  // Wall-clock deadline for the currently-running segment, not a tick
  // counter -- a plain "decrement once a second" timer stalls while the
  // screen is locked (mobile browsers throttle/suspend setTimeout in a
  // backgrounded tab), then just resumes counting from wherever it was
  // frozen once unlocked, silently eating however long the phone was
  // locked (found live-testing 2026-08-30: "поставил плей, заблокировал
  // экран, всё сбилось"). Anchoring to Date.now() means the countdown is
  // always correct the instant it's read, locked or not. A ref, not state
  // -- it's an implementation detail the effect below reads, never
  // something a render should react to.
  const deadlineRef = useRef<number | null>(null)
  // Background (on-device) notification for the current rest segment, same
  // mechanism as ExerciseDetailModal's RestTimer -- scheduled the instant
  // rest starts (see advanceWork below) and cancelled the instant it's no
  // longer relevant (rest ends naturally, is skipped, or this component
  // unmounts mid-rest), so it never fires stale.
  const scheduledRestNotificationRef = useRef<ScheduledRestNotification>({ cancel: () => {} })

  const restSeconds = exercise.rest_seconds ?? FALLBACK_REST_SECONDS

  // Ticks the visible countdown down from deadlineRef while running. Only
  // depends on `running`, not `remaining`/`phase` -- advanceWork/advanceRest
  // below flip running false then true again in the same batch when moving
  // between work and rest, which React collapses into a no-op transition,
  // so this effect keeps the same interval/listener alive across a phase
  // change rather than tearing down and missing that transition. Each
  // advance*() call moves deadlineRef itself, which is all this effect
  // needs to pick up the new segment.
  useEffect(() => {
    if (!running) {
      return
    }
    function sync() {
      const deadline = deadlineRef.current
      if (deadline === null) {
        return
      }
      setRemaining(Math.max(0, (deadline - Date.now()) / 1000))
    }
    sync()
    const interval = setInterval(sync, 1000)
    // Recompute immediately on regaining visibility (screen unlock, tab
    // refocus) instead of waiting for the next 1s tick -- the whole point
    // is snapping to the true elapsed time right away rather than however
    // long is left on the throttled interval.
    document.addEventListener('visibilitychange', sync)
    return () => {
      clearInterval(interval)
      document.removeEventListener('visibilitychange', sync)
    }
  }, [running])

  // Separate from the ticking effect above -- this one only reacts to
  // remaining actually crossing zero, regardless of how it got there.
  // alertTimerDone() (vibration + beep) fires here for both segments: the
  // work ring running out and the rest ring running out, matching what
  // RestTimer already does for the sets/reps flow. Deliberately not inside
  // advanceWork() itself -- that function is also called from the manual
  // early-confirm button below, which shouldn't play the "time's up" alert.
  useEffect(() => {
    if (!running || remaining > 0) {
      return
    }
    setRunning(false)
    alertTimerDone()
    if (phase === 'work') {
      advanceWork()
    } else {
      advanceRest()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running, remaining, phase])

  // Cancels any still-pending background rest notification if the athlete
  // navigates away mid-rest -- same cleanup RestTimer's own unmount does.
  useEffect(() => {
    return () => {
      scheduledRestNotificationRef.current.cancel()
    }
  }, [])

  // actualSeconds defaults to the full target -- the natural "ring counted
  // down to zero" path below always means the whole thing was done. A
  // manual early confirm (see the paused-mid-round controls further down)
  // passes whatever the athlete actually logged instead.
  function advanceWork(actualSeconds: number = durationSeconds) {
    const finishedSetNumber = completedRounds + 1
    // Honest record of what was actually done -- previously duration-mode
    // exercises left zero SetCompletion rows at all (found 2026-08-28
    // reviewing this against the backend's own already-built
    // duration_seconds_completed column). Best-effort/fire-and-forget: a
    // dropped save shouldn't block the athlete from continuing their
    // workout, same "don't let a network blip stall the flow" choice
    // SetLogger's own suggestion fetches make elsewhere in this file.
    setCompletionsApi
      .saveSet(
        {
          exercise_id: exercise.id,
          training_session_id: trainingSessionId,
          set_number: finishedSetNumber,
          weight_kg: null,
          reps_completed: null,
          duration_seconds_completed: actualSeconds,
        },
        accessToken,
      )
      .catch(() => {})

    setManualSeconds(null)

    if (finishedSetNumber >= rounds) {
      setCompletedRounds(rounds)
      onCompleteRef.current?.()
      setShowFeedback(true)
      return
    }
    setCompletedRounds(finishedSetNumber)
    setPhase('rest')
    deadlineRef.current = Date.now() + restSeconds * 1000
    setRemaining(restSeconds)
    setRunning(true)

    // Same local-notification safety net as RestTimer, for whenever the
    // athlete backgrounds the tab mid-rest -- see utils/restNotification.ts
    // for why this is web-PWA best-effort, not a native guarantee.
    ensureNotificationPermission()
      .then(() => progressApi.getRestDonePhrase(accessToken))
      .then((phrase) => {
        scheduledRestNotificationRef.current = scheduleRestDoneNotification(restSeconds, phrase.text)
      })
      .catch(() => {
        // Best-effort -- worst case this specific rest period just has no
        // background notification, the on-screen countdown still works.
      })
  }

  function advanceRest() {
    scheduledRestNotificationRef.current.cancel()
    setPhase('work')
    deadlineRef.current = Date.now() + durationSeconds * 1000
    setRemaining(durationSeconds)
    setRunning(true)
  }

  function skipRest() {
    setRunning(false)
    advanceRest()
  }

  // showFeedback checked BEFORE isDone -- once the last round's advance()
  // fires onComplete, the parent's own completed_at updates and re-renders
  // this component with isDone now true (found live-testing this exact
  // flow, 2026-08-28: the terminal "Готово" state below was winning the
  // race and hiding the feedback prompt before the athlete ever saw it).
  // showFeedback captures "still mid-flow, waiting on the feedback tap" and
  // must take priority regardless of what isDone becomes in the meantime.
  if (showFeedback && !feedbackAnswered) {
    return (
      <div className="flex flex-col items-center gap-3 py-4">
        <div className="flex h-20 w-20 items-center justify-center rounded-full border-2 border-accent-ice bg-accent-ice/15">
          <i className="ti ti-check text-4xl text-accent-ice" aria-hidden="true" />
        </div>
        <span className="text-sm font-medium text-accent-ice">Готово</span>
        <ExerciseFeedbackPrompt
          exercise={exercise}
          trainingSessionId={trainingSessionId}
          accessToken={accessToken}
          onSubmitted={() => {
            setFeedbackAnswered(true)
            onSettled?.()
          }}
        />
      </div>
    )
  }

  if (isDone || feedbackAnswered) {
    return (
      <div className="flex flex-col items-center gap-3 py-4">
        <div className="flex h-20 w-20 items-center justify-center rounded-full border-2 border-accent-ice bg-accent-ice/15">
          <i className="ti ti-check text-4xl text-accent-ice" aria-hidden="true" />
        </div>
        <span className="text-sm font-medium text-accent-ice">Готово</span>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center gap-4 py-2">
      {phase === 'work' ? (
        <div className="flex flex-col items-center gap-3">
          <CountdownRing
            totalSeconds={durationSeconds}
            remainingSeconds={remaining}
            label={`из ${durationSeconds} сек`}
            accent="ice"
            interactive
            running={running}
            onToggle={() =>
              setRunning((value) => {
                const next = !value
                if (next) {
                  // Resuming (or starting fresh) anchors a new deadline off
                  // whatever `remaining` currently is, and drops any
                  // honest-fact override from a previous pause -- the
                  // athlete chose to keep going, so the round isn't
                  // finishing early after all.
                  deadlineRef.current = Date.now() + remaining * 1000
                  setManualSeconds(null)
                } else {
                  // Paused mid-round -- capture what's actually elapsed so
                  // far as the starting point for an early honest confirm.
                  setManualSeconds(Math.round(durationSeconds - remaining))
                }
                return next
              })
            }
          />
          {manualSeconds !== null && (
            <div className="flex flex-col items-center gap-2">
              <span className="text-xs text-text-secondary">Сколько сек. реально сделали</span>
              <div className="flex items-center gap-3">
                <Stepper
                  value={manualSeconds}
                  unit="сек"
                  step={1}
                  min={0}
                  ariaLabel="Секунд выполнено"
                  onChange={setManualSeconds}
                />
                <button
                  type="button"
                  onClick={() => advanceWork(manualSeconds)}
                  aria-label="Подтвердить подход"
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-accent-ice text-dark-bg transition-opacity hover:opacity-90"
                >
                  <i className="ti ti-check text-lg" aria-hidden="true" />
                </button>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-col items-center gap-2">
          <CountdownRing
            totalSeconds={restSeconds}
            remainingSeconds={remaining}
            label="Отдых"
            accent="persimmon"
          />
          <button
            type="button"
            onClick={skipRest}
            className="text-xs text-text-secondary underline underline-offset-2 hover:text-text-primary"
          >
            Пропустить
          </button>
        </div>
      )}

      {rounds > 1 && (
        <div className="flex items-center gap-2">
          {Array.from({ length: rounds }, (_, index) => index).map((index) => (
            <div
              key={index}
              className={`flex h-6 w-6 items-center justify-center rounded-full border-2 font-display text-xs ${
                index < completedRounds
                  ? 'border-accent-ice bg-accent-ice text-dark-bg'
                  : index === completedRounds
                    ? 'border-accent-persimmon text-accent-persimmon'
                    : 'border-white/15 text-text-secondary'
              }`}
            >
              {index < completedRounds ? <i className="ti ti-check text-xs" aria-hidden="true" /> : index + 1}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
