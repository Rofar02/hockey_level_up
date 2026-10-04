export type FeedbackKind = 'bug' | 'idea' | 'other'
export type FeedbackStatus = 'new' | 'seen' | 'done'

export const FEEDBACK_KIND_LABELS: Record<FeedbackKind, string> = {
  bug: 'Ошибка',
  idea: 'Идея',
  other: 'Другое',
}

export const FEEDBACK_STATUS_LABELS: Record<FeedbackStatus, string> = {
  new: 'Новое',
  seen: 'Прочитано',
  done: 'Сделано',
}

export interface FeedbackAdminRead {
  id: string
  kind: FeedbackKind
  status: FeedbackStatus
  text: string
  has_screenshot: boolean
  context: Record<string, string | number | boolean | null>
  created_at: string
  user_id: string
  user_name: string
  user_email: string
}
