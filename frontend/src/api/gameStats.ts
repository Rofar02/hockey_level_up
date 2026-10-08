import { apiGet, apiPostAuth } from './client'
import type { SeasonRead, TeamStatsRead, TeamStatsScope } from '../types/gameStats'

export function getMySeason(accessToken: string): Promise<SeasonRead> {
  return apiGet<SeasonRead>('/users/me/season', accessToken)
}

export function getTeamStats(teamId: string, scope: TeamStatsScope, accessToken: string): Promise<TeamStatsRead> {
  return apiGet<TeamStatsRead>(`/teams/${teamId}/stats?scope=${scope}`, accessToken)
}

export function remindTeamReports(teamId: string, accessToken: string): Promise<{ reminded: number }> {
  return apiPostAuth<{ reminded: number }>(`/teams/${teamId}/stats/remind`, {}, accessToken)
}
