import { apiGet } from './client'
import type { LeaderboardEntryRead, LeaderboardMeRead } from '../types/leaderboard'

// "Hundreds of testers" scale (see final concept doc) -- a single page
// comfortably covers the whole board, so the UI doesn't need pagination
// controls yet even though the backend supports limit/offset.
const LEADERBOARD_PAGE_SIZE = 200

export function getLeaderboard(accessToken: string): Promise<LeaderboardEntryRead[]> {
  return apiGet<LeaderboardEntryRead[]>(`/leaderboard?limit=${LEADERBOARD_PAGE_SIZE}`, accessToken)
}

export function getMyLeaderboardPosition(accessToken: string): Promise<LeaderboardMeRead> {
  return apiGet<LeaderboardMeRead>('/leaderboard/me', accessToken)
}
