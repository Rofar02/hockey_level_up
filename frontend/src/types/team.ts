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
  // League and city -- raw codes for the settings form, display names
  // resolved server-side (app/core/leagues.py).
  city: string | null
  league_code: string
  division_code: string | null
  league_other_name: string | null
  league_name: string | null
  division_name: string | null
}

// GET /teams/{team_id}/score and /teams/leaderboard -- team_score is
// computed on the fly server-side, never stored, so this always reflects
// the current formula inputs. All components included (not just
// team_score) so a breakdown can be shown without re-deriving it.
export interface TeamScoreRead {
  team_id: string
  team_name: string
  team_score: number
  member_count: number
  sum_xp: number
  avg_trainings_per_member_per_week: number
  activity_bonus: number
  // Place among teams of the same league and city -- only from GET
  // /teams/{id}/score, null below 3 such teams.
  league_place?: number | null
  league_team_count?: number | null
}

export interface TeamLeagueFields {
  city: string | null
  league_code: string
  division_code: string | null
  league_other_name: string | null
}

export interface TeamCreatePayload extends TeamLeagueFields {
  name: string
}

// PATCH /teams/{id} -- captain only, every field sent.
export type TeamUpdatePayload = TeamCreatePayload

export interface LeagueRead {
  code: string
  name: string
  divisions: { code: string; name: string }[]
}

// Admin: GET /teams/admin/other-leagues.
export interface OtherLeagueNameRead {
  name: string
  team_count: number
}

export interface TeamJoinPayload {
  code: string
}

export interface TeamTransferCaptaincyPayload {
  user_id: string
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

// GET /teams/invite/{code} (2026-10-08) -- the team behind an invite link,
// shown to anyone; never its members.
export interface TeamInvitePreviewRead {
  id: string
  name: string
  logo_url: string | null
  member_count: number
  captain_first_name: string
  captain_last_name: string
}

export type TeamInviteStatus = 'none' | 'invited' | 'member' | 'in_team'

// A row in the captain's "Пригласить игрока" sheet.
export interface TeamInviteCandidateRead {
  id: string
  first_name: string
  last_name: string
  avatar_url: string | null
  level: number
  jersey_number: number | null
  position: Position | null
  team_name: string | null
  status: TeamInviteStatus
  match: 'exact' | 'similar'
}

// A captain's invitation, as the invited player sees it.
export interface TeamInvitationRead {
  id: string
  team_id: string
  team_name: string
  team_logo_url: string | null
  member_count: number
  invited_by_first_name: string
  invited_by_last_name: string
  status: 'pending' | 'accepted' | 'declined'
  created_at: string
}
