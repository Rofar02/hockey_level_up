import { useEffect, useState } from 'react'
import * as exercisesApi from '../api/exercises'
import type { ExerciseRead } from '../types/exercise'
import { SET_FEEDBACK_LABELS } from '../types/setCompletion'
import type { ExerciseHistorySession, SetCompletionSummary } from '../types/setCompletion'
import { WEEKDAY_LABELS, formatShortDate } from '../utils/date'

// One logged set in the athlete's own words -- weight x reps for a weighted
// exercise, plain reps otherwise, seconds for a timed one. Whatever the set
// actually recorded wins over the exercise's mode, so an old row logged
// before a catalog edit still reads honestly.
function formatSet(set: SetCompletionSummary, tracksWeight: boolean): string | null {
  if (set.duration_seconds_completed !== null) {
    return `${set.duration_seconds_completed} сек`
  }
  if (set.reps_completed === null) {
    return null
  }
  return tracksWeight && set.weight_kg !== null
    ? `${set.weight_kg} кг × ${set.reps_completed}`
    : `${set.reps_completed} повт.`
}

function formatSessionDate(iso: string): string {
  const date = new Date(iso)
  return `${WEEKDAY_LABELS[(date.getDay() + 6) % 7]}, ${formatShortDate(date)}.${date.getFullYear()}`
}

// "История выполнения" under the player (user request 2026-09-28, modelled
// on a competitor's diary screen): the athlete's last few sessions of this
// exercise, so what to beat is right there instead of only in Analytics.
// Past sessions only -- the current one is already SetLogger/TimerPlayer's
// own rows above. Collapsed to a single row by default (user feedback
// 2026-09-28: open it on request, don't push the player's own controls
// around) -- still fetched up front so that row can say when the exercise
// was last done, and so it renders nothing at all until the first time
// the exercise is logged rather than a toggle that opens onto nothing.
export function ExerciseHistory({
  exercise,
  trainingSessionId,
  accessToken,
}: {
  exercise: ExerciseRead
  trainingSessionId: string
  accessToken: string
}) {
  const [sessions, setSessions] = useState<ExerciseHistorySession[] | null>(null)
  const [isOpen, setIsOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    setSessions(null)
    setIsOpen(false)
    exercisesApi
      .getExerciseHistory(exercise.id, accessToken, trainingSessionId)
      .then((history) => {
        if (!cancelled) {
          setSessions(history.sessions)
        }
      })
      .catch(() => {
        // Best-effort like the suggestion fetches -- the section just
        // stays hidden.
        if (!cancelled) {
          setSessions([])
        }
      })
    return () => {
      cancelled = true
    }
  }, [exercise.id, trainingSessionId, accessToken])

  if (sessions === null || sessions.length === 0) {
    return null
  }

  return (
    <div className="flex flex-col gap-2 border-t border-white/5 pt-3">
      <button
        type="button"
        onClick={() => setIsOpen((value) => !value)}
        aria-expanded={isOpen}
        className="flex items-center justify-between gap-2 text-left"
      >
        <span className="flex min-w-0 flex-col">
          <span className="text-xs font-medium uppercase tracking-wide text-text-secondary">История выполнения</span>
          {!isOpen && (
            <span className="truncate text-xs text-text-secondary/70">
              последний раз: {formatSessionDate(sessions[0].performed_at)}
            </span>
          )}
        </span>
        <i
          className={`ti ti-chevron-down shrink-0 text-lg text-text-secondary transition-transform ${
            isOpen ? 'rotate-180' : ''
          }`}
          aria-hidden="true"
        />
      </button>
      {isOpen &&
        sessions.map((session) => (
          <div key={session.training_session_id} className="overflow-hidden rounded-md border border-white/5">
            <div className="flex items-center justify-between gap-2 bg-white/5 px-3 py-1.5">
              <span className="font-display text-sm font-semibold text-text-primary">
                {formatSessionDate(session.performed_at)}
              </span>
              {session.feedback !== null && (
                <span className="text-xs text-text-secondary">{SET_FEEDBACK_LABELS[session.feedback]}</span>
              )}
            </div>
            {session.sets.map((set) => {
              const value = formatSet(set, exercise.tracks_weight)
              return (
                value !== null && (
                  <div
                    key={set.set_number}
                    className="flex items-center gap-3 border-t border-white/5 px-3 py-1.5 text-sm"
                  >
                    <span className="w-6 shrink-0 font-mono text-xs text-text-secondary">#{set.set_number}</span>
                    <span className="font-mono text-text-primary">{value}</span>
                  </div>
                )
              )
            })}
          </div>
        ))}
    </div>
  )
}
