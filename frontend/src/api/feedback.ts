import { API_BASE_URL, apiGet, apiPatchAuth, apiPostMultipartAuth } from './client'
import type { FeedbackAdminRead, FeedbackKind, FeedbackStatus } from '../types/feedback'

export interface FeedbackInput {
  kind: FeedbackKind
  text: string
  page: string
  userAgent: string
  screen: string
  standalone: boolean
  screenshot: File | null
}

export function sendFeedback(input: FeedbackInput, accessToken: string): Promise<{ id: string }> {
  const form = new FormData()
  form.append('kind', input.kind)
  form.append('text', input.text)
  form.append('page', input.page)
  form.append('user_agent', input.userAgent)
  form.append('screen', input.screen)
  form.append('standalone', String(input.standalone))
  if (input.screenshot !== null) {
    form.append('screenshot', input.screenshot)
  }
  return apiPostMultipartAuth<{ id: string }>('/feedback', form, accessToken)
}

export function listFeedbackAdmin(status: FeedbackStatus | null, accessToken: string): Promise<FeedbackAdminRead[]> {
  return apiGet<FeedbackAdminRead[]>(`/admin/feedback${status !== null ? `?status=${status}` : ''}`, accessToken)
}

export function setFeedbackStatus(id: string, status: FeedbackStatus, accessToken: string): Promise<void> {
  return apiPatchAuth<void>(`/admin/feedback/${id}`, { status }, accessToken)
}

// Admin-only screenshot (private on the server) -- fetched with the token and
// shown from a blob URL, since an <img src> can't carry the Authorization header.
export async function fetchFeedbackScreenshot(id: string, accessToken: string): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}/admin/feedback/${id}/screenshot`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
  if (!response.ok) {
    throw new Error(`screenshot ${response.status}`)
  }
  return response.blob()
}
