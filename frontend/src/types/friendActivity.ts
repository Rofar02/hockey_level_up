import type { DaySessionType } from './schedule'

export type ActivityFeedEventType = 'level_up' | 'training_completed' | 'party_completed'

// GET /friends/feed -- one row per outbox_events row (level_up,
// training_completed, or party_completed), reshaped for display.
// level/session_type/party_size are only set for the matching event_type.
export interface ActivityFeedEntryRead {
  id: string
  event_type: ActivityFeedEventType
  user_id: string
  first_name: string
  last_name: string
  avatar_url: string | null
  created_at: string
  level: number | null
  session_type: DaySessionType | null
  party_size: number | null
}
