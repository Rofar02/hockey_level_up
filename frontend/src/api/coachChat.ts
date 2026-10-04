import { apiDeleteAuth, apiGet, apiPostAuth } from './client'
import type {
  CoachAttentionRead,
  CoachChatMessageRead,
  CoachChatReplyRead,
  CoachMemoryFactRead,
  ProposedActionRead,
  WeeklyReviewRead,
} from '../types/coachChat'

export function sendCoachChatMessage(
  message: string,
  accessToken: string,
): Promise<CoachChatReplyRead> {
  return apiPostAuth<CoachChatReplyRead>('/users/me/coach-chat', { message }, accessToken)
}

export function getCoachChatHistory(
  accessToken: string,
  limit = 50,
): Promise<CoachChatMessageRead[]> {
  return apiGet<CoachChatMessageRead[]>(`/users/me/coach-chat/history?limit=${limit}`, accessToken)
}

export function confirmProposedAction(
  actionId: string,
  accessToken: string,
): Promise<ProposedActionRead> {
  return apiPostAuth<ProposedActionRead>(
    `/users/me/coach-chat/actions/${actionId}/confirm`,
    {},
    accessToken,
  )
}

export function dismissProposedAction(
  actionId: string,
  accessToken: string,
): Promise<ProposedActionRead> {
  return apiPostAuth<ProposedActionRead>(
    `/users/me/coach-chat/actions/${actionId}/dismiss`,
    {},
    accessToken,
  )
}

export function getCoachAttention(accessToken: string): Promise<CoachAttentionRead> {
  return apiGet<CoachAttentionRead>('/users/me/coach-attention', accessToken)
}

// Coach memory notes ("Что помнит тренер", 2026-10-04).
export function getCoachMemory(accessToken: string): Promise<CoachMemoryFactRead[]> {
  return apiGet<CoachMemoryFactRead[]>('/users/me/coach-memory', accessToken)
}

export function deleteCoachMemoryFact(factId: string, accessToken: string): Promise<void> {
  return apiDeleteAuth<void>(`/users/me/coach-memory/${factId}`, accessToken)
}

export function forgetCoachMemory(accessToken: string): Promise<void> {
  return apiDeleteAuth<void>('/users/me/coach-memory', accessToken)
}

// Weekly coach review ("Разбор недели", 2026-10-04) -- null when none to show.
export function getWeeklyReview(accessToken: string): Promise<WeeklyReviewRead | null> {
  return apiGet<WeeklyReviewRead | null>('/users/me/weekly-review', accessToken)
}

export function markWeeklyReviewRead(reviewId: string, accessToken: string): Promise<void> {
  return apiPostAuth<void>(`/users/me/weekly-review/${reviewId}/read`, {}, accessToken)
}

// 👍/👎 on a coach reply that asked for it (2026-10-04).
export function sendCoachReplyFeedback(messageId: string, value: 1 | -1, accessToken: string): Promise<void> {
  return apiPostAuth<void>(`/users/me/coach-chat/messages/${messageId}/feedback`, { value }, accessToken)
}
