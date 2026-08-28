import { useState } from 'react'
import { FormError } from './ui/FormError'
import * as setCompletionsApi from '../api/setCompletions'
import { ApiError } from '../api/client'
import type { ExerciseRead } from '../types/exercise'
import { SET_FEEDBACK_LABELS, SET_FEEDBACK_OPTIONS } from '../types/setCompletion'

// "Как ощущения?" step shown right after an exercise's last set/round
// completes (icelevel_player_master_prompt.md, 2026-08-28) -- used by both
// SetLogger's own inline flow and TimerPlayer's duration mode, in its own
// file so neither of those two components needs to import the other.
// SetLogger keeps its own read-only "already answered" summary separately
// (it needs to show that on reopening a previously-completed exercise,
// which this component never has to handle -- it only ever mounts while
// feedback hasn't been given yet, and stops rendering the moment
// onSubmitted fires and the parent advances away).
export function ExerciseFeedbackPrompt({
  exercise,
  trainingSessionId,
  accessToken,
  onSubmitted,
}: {
  exercise: ExerciseRead
  trainingSessionId: string
  accessToken: string
  onSubmitted: () => void
}) {
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSelect(value: (typeof SET_FEEDBACK_OPTIONS)[number]) {
    setError(null)
    setIsSaving(true)
    try {
      await setCompletionsApi.saveFeedback(
        { exercise_id: exercise.id, training_session_id: trainingSessionId, feedback: value },
        accessToken,
      )
      onSubmitted()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сохранить оценку.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="flex flex-col items-center gap-2 pt-1">
      <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">Как ощущения?</p>
      <div className="flex flex-wrap justify-center gap-2">
        {SET_FEEDBACK_OPTIONS.map((option) => (
          <button
            key={option}
            type="button"
            disabled={isSaving}
            onClick={() => handleSelect(option)}
            className="rounded border border-white/10 px-3 py-2 text-sm text-text-secondary transition-colors hover:border-white/30 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {SET_FEEDBACK_LABELS[option]}
          </button>
        ))}
      </div>
      <FormError message={error} />
    </div>
  )
}
