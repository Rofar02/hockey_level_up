import { apiGet, apiPostAuth } from './client'
import type { CoachChatMessageRead, CoachChatReplyRead } from '../types/coachChat'

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
