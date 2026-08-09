import type { Position } from './user'

export interface LeaderboardEntryRead {
  id: string
  last_name: string
  first_name: string
  patronymic: string | null
  avatar_url: string | null
  position: Position | null
  jersey_number: number | null
  rating_excess: number
}

export interface LeaderboardMeRead {
  rank: number
  rating_excess: number
}
