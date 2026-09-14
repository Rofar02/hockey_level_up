export type CoachChatRole = 'user' | 'assistant'

export type CoachActionType = 'skill_priority_add' | 'set_tournament_date' | 'report_restriction'

export type CoachActionStatus = 'pending' | 'confirmed' | 'dismissed' | 'expired'

// `summary` is ready-to-render, already-localized text built server-side
// (see ProposedActionRead in app/schemas/coach_chat.py) -- no per-action_type
// copy dictionary needed here.
export interface ProposedActionRead {
  id: string
  action_type: CoachActionType
  payload: Record<string, unknown>
  status: CoachActionStatus
  summary: string
}

export interface CoachChatMessageRead {
  id: string
  role: CoachChatRole
  content: string
  created_at: string
  proposed_action: ProposedActionRead | null
}

export interface CoachChatReplyRead {
  reply: CoachChatMessageRead
}
