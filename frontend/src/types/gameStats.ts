import type { PlayerTeamBadgeRead } from './user'
import type { GameResult, GameWorkOn } from './trainingDiary'

// Mirrors app/schemas/game_stats.py (2026-10-08).
export interface SeasonGame {
  date: string
  day_plan_id: string
  result: GameResult
  goals: number | null
  assists: number | null
  shots: number | null
  self_rating: number | null
}

export interface SeasonRead {
  label: string
  start: string
  end: string
  games: number
  wins: number
  draws: number
  losses: number
  goals: number
  assists: number
  points: number
  shots: number
  avg_self_rating: number | null
  // Oldest first.
  recent_games: SeasonGame[]
}

export interface TeamPlayerStats {
  user_id: string
  first_name: string
  last_name: string
  jersey_number: number | null
  games: number
  goals: number
  assists: number
  points: number
  shots: number
  avg_self_rating: number | null
  work_on: GameWorkOn[] | null
  missing_reports: number
}

export type TeamStatsScope = 'season' | 'last_game'

export interface TeamStatsRead {
  scope: TeamStatsScope
  season_label: string
  last_game_date: string | null
  players: TeamPlayerStats[]
}

// GET /users/me/season-summary -- «Мой сезон» (release plan step 10).
export interface SeasonSummaryRead {
  available: boolean
  reason: string | null
  season_label: string
  ice_days: number
  games: number
  gym_sessions: number
  team_attendance_percent: number | null
  stats: { stat: string; before: number; after: number }[]
  overall_before: number | null
  overall_after: number | null
  best_streak: number
  level: number
  frequent_linemate: string | null
  team: PlayerTeamBadgeRead | null
}
