import { apiPostAuth } from './client'
import type { SetCompletionCreate, SetCompletionRead, SetFeedbackIn } from '../types/setCompletion'

export function saveSet(
  payload: SetCompletionCreate,
  accessToken: string,
): Promise<SetCompletionRead> {
  return apiPostAuth<SetCompletionRead>('/set-completions', payload, accessToken)
}

export function saveFeedback(
  payload: SetFeedbackIn,
  accessToken: string,
): Promise<SetCompletionRead> {
  return apiPostAuth<SetCompletionRead>('/set-completions/feedback', payload, accessToken)
}
