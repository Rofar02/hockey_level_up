import { apiGet, apiPostAuth } from './client'
import type { CoachAttentionRead, CoachChatMessageRead, CoachChatReplyRead, ProposedActionRead } from '../types/coachChat'

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
