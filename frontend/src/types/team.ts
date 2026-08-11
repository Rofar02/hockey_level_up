import type { Position } from './user'

export const TEAM_JOIN_REQUEST_STATUSES = ['pending', 'approved', 'rejected'] as const
export type TeamJoinRequestStatus = (typeof TEAM_JOIN_REQUEST_STATUSES)[number]

export interface TeamMemberRead {
  id: string
  first_name: string
  last_name: string
  avatar_url: string | null
  level: number
  jersey_number: number | null
  position: Position | null
  is_captain: boolean
}

// GET /teams/me -- one row per team the caller belongs to.
export interface TeamSummaryRead {
  id: string
  name: string
  logo_url: string | null
  member_count: number
  is_captain: boolean
}

// GET /teams/{team_id} -- full detail.
export interface TeamRead {
  id: string
  name: string
  logo_url: string | null
  invite_code: string
  owner_id: string
  is_captain: boolean
  members: TeamMemberRead[]
  created_at: string
}

export interface TeamCreatePayload {
  name: string
}

export interface TeamJoinPayload {
  code: string
}

// Reused for both "my own pending requests" and the captain's incoming
// list -- same shape as the backend's TeamJoinRequestRead.
export interface TeamJoinRequestRead {
  id: string
  team_id: string
  team_name: string
  user_id: string
  first_name: string
  last_name: string
  avatar_url: string | null
  status: TeamJoinRequestStatus
  created_at: string
}
