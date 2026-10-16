import { apiPostAuth } from './client'
import type { SetCompletionCreate, SetCompletionRead, SetFeedbackIn } from '../types/setCompletion'
import { enqueueWrite, isQueueEnabled } from '../utils/writeQueue'

// Б2: with the offline queue on, both go through utils/writeQueue -- the
// answer is the server's when it comes quickly, an optimistic copy otherwise.

function optimisticSet(payload: Partial<SetCompletionCreate>, performedAt: string): SetCompletionRead {
  return {
    id: `pending-${payload.exercise_id}-${payload.set_number}`,
    exercise_id: payload.exercise_id ?? '',
    training_session_id: payload.training_session_id ?? '',
    set_number: payload.set_number ?? 0,
    weight_kg: payload.weight_kg ?? null,
    reps_completed: payload.reps_completed ?? null,
    duration_seconds_completed: payload.duration_seconds_completed ?? null,
    suggested_weight_kg: null,
    was_weight_adjusted_manually: false,
    feedback: null,
    completed_at: performedAt,
  }
}

export function saveSet(
  payload: SetCompletionCreate,
  accessToken: string,
): Promise<SetCompletionRead> {
  if (isQueueEnabled()) {
    return enqueueWrite({
      method: 'POST',
      path: '/set-completions',
      body: { ...payload },
      label: `Подход ${payload.set_number}`,
      optimistic: (performedAt) => optimisticSet(payload, performedAt),
    })
  }
  return apiPostAuth<SetCompletionRead>('/set-completions', payload, accessToken)
}

export function saveFeedback(
  payload: SetFeedbackIn,
  accessToken: string,
): Promise<SetCompletionRead> {
  if (isQueueEnabled()) {
    return enqueueWrite({
      method: 'POST',
      path: '/set-completions/feedback',
      body: { ...payload },
      label: 'Оценка упражнения',
      optimistic: (performedAt) => ({ ...optimisticSet(payload, performedAt), feedback: payload.feedback }),
    })
  }
  return apiPostAuth<SetCompletionRead>('/set-completions/feedback', payload, accessToken)
}
