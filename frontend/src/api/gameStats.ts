import { apiGet, apiPostAuth } from './client'
import type { SeasonRead, SeasonSummaryRead, TeamStatsRead, TeamStatsScope } from '../types/gameStats'

export function getMySeason(accessToken: string): Promise<SeasonRead> {
  return apiGet<SeasonRead>('/users/me/season', accessToken)
}

export function getTeamStats(teamId: string, scope: TeamStatsScope, accessToken: string): Promise<TeamStatsRead> {
  return apiGet<TeamStatsRead>(`/teams/${teamId}/stats?scope=${scope}`, accessToken)
}

export function remindTeamReports(teamId: string, accessToken: string): Promise<{ reminded: number }> {
  return apiPostAuth<{ reminded: number }>(`/teams/${teamId}/stats/remind`, {}, accessToken)
}

// «Мой сезон» (release plan step 10); preview builds it before spring.
export function getSeasonSummary(accessToken: string, preview = false): Promise<SeasonSummaryRead> {
  return apiGet<SeasonSummaryRead>(`/users/me/season-summary${preview ? '?preview=true' : ''}`, accessToken)
}
