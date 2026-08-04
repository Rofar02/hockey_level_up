export const SET_FEEDBACK_OPTIONS = ['easy', 'normal', 'hard', 'max'] as const
export type SetFeedback = (typeof SET_FEEDBACK_OPTIONS)[number]

export const SET_FEEDBACK_LABELS: Record<SetFeedback, string> = {
  easy: 'Легко',
  normal: 'Нормально',
  hard: 'Тяжело',
  max: 'На пределе',
}

export interface SetCompletionCreate {
  exercise_id: string
  training_session_id: string
  set_number: number
  weight_kg: number | null
  reps_completed: number | null
}

export interface SetCompletionRead {
  id: string
  exercise_id: string
  training_session_id: string
  set_number: number
  weight_kg: number | null
  reps_completed: number | null
  duration_seconds_completed: number | null
  suggested_weight_kg: number | null
  was_weight_adjusted_manually: boolean
  feedback: SetFeedback | null
  completed_at: string
}

export interface SetFeedbackIn {
  exercise_id: string
  training_session_id: string
  feedback: SetFeedback
}

export interface SuggestedWeightRead {
  suggested_weight_kg: number | null
}

export interface SetCompletionSummary {
  set_number: number
  weight_kg: number | null
  reps_completed: number | null
  duration_seconds_completed: number | null
  completed_at: string
}

export interface ExerciseSetsRead {
  sets: SetCompletionSummary[]
  feedback: SetFeedback | null
}
