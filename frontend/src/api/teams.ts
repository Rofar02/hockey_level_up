import { apiDeleteAuth, apiGet, apiGetPublic, apiPostAuth, apiPostMultipartAuth } from './client'
import type {
  TeamCreatePayload,
  TeamInvitationRead,
  TeamInviteCandidateRead,
  TeamInvitePreviewRead,
  TeamJoinPayload,
  TeamJoinRequestRead,
  TeamRead,
  TeamScoreRead,
  TeamSummaryRead,
  TeamTransferCaptaincyPayload,
} from '../types/team'
import type { LeaderboardEntryRead } from '../types/leaderboard'

export function listMyTeams(accessToken: string): Promise<TeamSummaryRead[]> {
  return apiGet<TeamSummaryRead[]>('/teams/me', accessToken)
}

export function getTeam(teamId: string, accessToken: string): Promise<TeamRead> {
  return apiGet<TeamRead>(`/teams/${teamId}`, accessToken)
}

export function createTeam(payload: TeamCreatePayload, accessToken: string): Promise<TeamRead> {
  return apiPostAuth<TeamRead>('/teams', payload, accessToken)
}

export function disbandTeam(teamId: string, accessToken: string): Promise<void> {
  return apiDeleteAuth<void>(`/teams/${teamId}`, accessToken)
}

// Captain-only -- the backend 403s for anyone else (TeamService._require_captain).
export function uploadTeamLogo(teamId: string, file: File, accessToken: string): Promise<TeamRead> {
  const formData = new FormData()
  formData.append('file', file)
  return apiPostMultipartAuth<TeamRead>(`/teams/${teamId}/logo`, formData, accessToken)
}

export function joinTeam(
  payload: TeamJoinPayload,
  accessToken: string,
): Promise<TeamJoinRequestRead> {
  return apiPostAuth<TeamJoinRequestRead>('/teams/join', payload, accessToken)
}

export function listMyJoinRequests(accessToken: string): Promise<TeamJoinRequestRead[]> {
  return apiGet<TeamJoinRequestRead[]>('/teams/join-requests/me', accessToken)
}

export function cancelJoinRequest(requestId: string, accessToken: string): Promise<void> {
  return apiDeleteAuth<void>(`/teams/join-requests/${requestId}`, accessToken)
}

export function listTeamJoinRequests(
  teamId: string,
  accessToken: string,
): Promise<TeamJoinRequestRead[]> {
  return apiGet<TeamJoinRequestRead[]>(`/teams/${teamId}/join-requests`, accessToken)
}

export function approveJoinRequest(
  requestId: string,
  accessToken: string,
): Promise<TeamJoinRequestRead> {
  return apiPostAuth<TeamJoinRequestRead>(`/teams/join-requests/${requestId}/approve`, {}, accessToken)
}

export function rejectJoinRequest(
  requestId: string,
  accessToken: string,
): Promise<TeamJoinRequestRead> {
  return apiPostAuth<TeamJoinRequestRead>(`/teams/join-requests/${requestId}/reject`, {}, accessToken)
}

export function leaveTeam(teamId: string, accessToken: string): Promise<void> {
  return apiDeleteAuth<void>(`/teams/${teamId}/members/me`, accessToken)
}

// Captain-only -- the backend 403s for anyone else (TeamService.kick_member).
export function kickMember(teamId: string, userId: string, accessToken: string): Promise<void> {
  return apiDeleteAuth<void>(`/teams/${teamId}/members/${userId}`, accessToken)
}

// Captain-only -- reassigns Team.owner_id to an existing member.
export function transferCaptaincy(
  teamId: string,
  payload: TeamTransferCaptaincyPayload,
  accessToken: string,
): Promise<TeamRead> {
  return apiPostAuth<TeamRead>(`/teams/${teamId}/captain`, payload, accessToken)
}

export function getTeamLeaderboard(
  teamId: string,
  accessToken: string,
): Promise<LeaderboardEntryRead[]> {
  return apiGet<LeaderboardEntryRead[]>(`/teams/${teamId}/leaderboard`, accessToken)
}

// Cross-team rating -- separate from getTeamLeaderboard above, which stays
// scoped to one team's own members.
export function getTeamScore(teamId: string, accessToken: string): Promise<TeamScoreRead> {
  return apiGet<TeamScoreRead>(`/teams/${teamId}/score`, accessToken)
}

const TEAM_RANKING_PAGE_SIZE = 100

export function getTeamRankings(accessToken: string): Promise<TeamScoreRead[]> {
  return apiGet<TeamScoreRead[]>(`/teams/leaderboard?limit=${TEAM_RANKING_PAGE_SIZE}`, accessToken)
}

// The team behind an invite link -- no login needed.
export function getTeamInvite(code: string): Promise<TeamInvitePreviewRead> {
  return apiGetPublic<TeamInvitePreviewRead>(`/teams/invite/${encodeURIComponent(code)}`)
}

// Captain: their friends, or name-search hits with a query.
export function listInviteCandidates(
  teamId: string,
  query: string,
  accessToken: string,
): Promise<TeamInviteCandidateRead[]> {
  const q = query.trim() !== '' ? `?q=${encodeURIComponent(query.trim())}` : ''
  return apiGet<TeamInviteCandidateRead[]>(`/teams/${teamId}/invite-candidates${q}`, accessToken)
}

export function inviteToTeam(teamId: string, userId: string, accessToken: string): Promise<TeamInviteCandidateRead> {
  return apiPostAuth<TeamInviteCandidateRead>(`/teams/${teamId}/invitations`, { user_id: userId }, accessToken)
}

export function listMyTeamInvitations(accessToken: string): Promise<TeamInvitationRead[]> {
  return apiGet<TeamInvitationRead[]>('/teams/invitations/me', accessToken)
}

export function acceptTeamInvitation(invitationId: string, accessToken: string): Promise<TeamInvitationRead> {
  return apiPostAuth<TeamInvitationRead>(`/teams/invitations/${invitationId}/accept`, {}, accessToken)
}

export function declineTeamInvitation(invitationId: string, accessToken: string): Promise<TeamInvitationRead> {
  return apiPostAuth<TeamInvitationRead>(`/teams/invitations/${invitationId}/decline`, {}, accessToken)
}
