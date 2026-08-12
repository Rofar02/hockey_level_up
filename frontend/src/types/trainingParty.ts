export const TRAINING_PARTY_STATUSES = ['pending', 'completed', 'cancelled', 'expired'] as const
export type TrainingPartyStatus = (typeof TRAINING_PARTY_STATUSES)[number]

export const TRAINING_PARTY_MEMBERSHIP_STATUSES = ['invited', 'joined', 'declined'] as const
export type TrainingPartyMembershipStatus = (typeof TRAINING_PARTY_MEMBERSHIP_STATUSES)[number]

export const MEMBER_TRAINING_STATUSES = [
  'no_plan_for_date',
  'resting',
  'game_day',
  'not_started',
  'in_progress',
  'completed',
] as const
export type MemberTrainingStatus = (typeof MEMBER_TRAINING_STATUSES)[number]

// GET /training-parties/{id} member row -- training_status/completed_blocks/
// total_blocks are null until the member has actually joined (see backend
// TrainingPartyService._to_detail_read).
export interface TrainingPartyMemberRead {
  user_id: string
  first_name: string
  last_name: string
  avatar_url: string | null
  membership_status: TrainingPartyMembershipStatus
  training_status: MemberTrainingStatus | null
  completed_blocks: number | null
  total_blocks: number | null
  day_plan_id: string | null
}

export interface TrainingPartyDetailRead {
  id: string
  created_by: string
  target_date: string
  status: TrainingPartyStatus
  members: TrainingPartyMemberRead[]
  created_at: string
  completed_at: string | null
}

// GET /training-parties/me -- one row per party the caller created or joined.
export interface TrainingPartySummaryRead {
  id: string
  target_date: string
  status: TrainingPartyStatus
  member_count: number
  is_creator: boolean
}

// GET /training-parties/invites -- requests sent *to* the caller.
export interface TrainingPartyInviteRead {
  party_id: string
  target_date: string
  created_by_id: string
  created_by_first_name: string
  created_by_last_name: string
  created_by_avatar_url: string | null
  member_count: number
}

export interface TrainingPartyCreatePayload {
  target_date: string
  friend_ids: string[]
}
