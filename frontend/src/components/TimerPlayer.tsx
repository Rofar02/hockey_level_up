import { useEffect, useRef, useState } from 'react'
import { ExerciseFeedbackPrompt } from './ExerciseFeedbackPrompt'
import * as setCompletionsApi from '../api/setCompletions'
import type { ExerciseRead } from '../types/exercise'

function formatSeconds(totalSeconds: number): string {
  return String(Math.max(0, Math.ceil(totalSeconds)))
}

// Mode A ("на время") from icelevel_player_master_prompt.md, 2026-08-28:
// a real countdown ring instead of the old flat "Нужно/Старт/Подходы"
// circles -- big Oswald number in the center, play/pause below, round-pips
// only when there's more than one round (target_sets alongside a duration
// means "N rounds of M seconds", e.g. plank hold x3).
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
  const [remaining, setRemaining] = useState(durationSeconds)
  const [running, setRunning] = useState(false)
  // True for the brief auto-advance window after a round hits 0 -- lets
  // the athlete cancel and redo that same round instead of being swept
  // into the next one immediately.
  const [pendingAdvance, setPendingAdvance] = useState(false)
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
  const advanceTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onCompleteRef = useRef(onComplete)
  onCompleteRef.current = onComplete

  useEffect(() => {
    return () => {
      if (advanceTimeoutRef.current !== null) {
        clearTimeout(advanceTimeoutRef.current)
      }
    }
  }, [])

  useEffect(() => {
    if (!running || pendingAdvance) {
      return
    }
    if (remaining <= 0) {
      setRunning(false)
      setPendingAdvance(true)
      advanceTimeoutRef.current = setTimeout(() => {
        advance()
      }, 2000)
      return
    }
    const timer = setTimeout(() => setRemaining((value) => value - 1), 1000)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running, pendingAdvance, remaining])

  function advance() {
    if (advanceTimeoutRef.current !== null) {
      clearTimeout(advanceTimeoutRef.current)
      advanceTimeoutRef.current = null
    }
    setPendingAdvance(false)
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
          duration_seconds_completed: durationSeconds,
        },
        accessToken,
      )
      .catch(() => {})

    if (finishedSetNumber >= rounds) {
      setCompletedRounds(rounds)
      onCompleteRef.current?.()
      setShowFeedback(true)
      return
    }
    setCompletedRounds(finishedSetNumber)
    setRemaining(durationSeconds)
    setRunning(true)
  }

  function cancelAdvance() {
    if (advanceTimeoutRef.current !== null) {
      clearTimeout(advanceTimeoutRef.current)
      advanceTimeoutRef.current = null
    }
    setPendingAdvance(false)
    setRemaining(durationSeconds)
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

  const size = 148
  const strokeWidth = 10
  const radius = size / 2 - strokeWidth
  const circumference = 2 * Math.PI * radius
  const elapsed = durationSeconds - remaining
  const percent = durationSeconds > 0 ? Math.max(0, Math.min(1, elapsed / durationSeconds)) : 0
  const dashoffset = circumference * (1 - percent)
  const center = size / 2

  return (
    <div className="flex flex-col items-center gap-4 py-2">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          <circle cx={center} cy={center} r={radius} fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth={strokeWidth} />
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke="#D7EFFF"
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashoffset}
            transform={`rotate(-90 ${center} ${center})`}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-display text-4xl font-semibold leading-none text-text-primary">
            {formatSeconds(remaining)}
          </span>
          <span className="mt-1 text-[11px] uppercase tracking-wide text-text-secondary">
            из {durationSeconds} сек
          </span>
        </div>
      </div>

      {pendingAdvance ? (
        <button
          type="button"
          onClick={cancelAdvance}
          className="rounded-md border border-white/15 px-4 py-2 text-sm text-text-secondary hover:text-text-primary"
        >
          Отменить переход
        </button>
      ) : (
        <button
          type="button"
          onClick={() => setRunning((value) => !value)}
          className="flex h-14 w-14 items-center justify-center rounded-full bg-accent-ice text-dark-bg"
          aria-label={running ? 'Пауза' : 'Старт'}
        >
          <i className={`ti ${running ? 'ti-player-pause' : 'ti-player-play'} text-2xl`} aria-hidden="true" />
        </button>
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
