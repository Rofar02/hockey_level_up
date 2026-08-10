export type CoachChatRole = 'user' | 'assistant'

export interface CoachChatMessageRead {
  id: string
  role: CoachChatRole
  content: string
  created_at: string
}

export interface CoachChatReplyRead {
  reply: CoachChatMessageRead
}
