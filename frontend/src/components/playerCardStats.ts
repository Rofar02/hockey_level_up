import type { PlayerCardStat } from './PlayerCard'
import type { TargetStat } from '../types/exercise'

// Turning a player's stats into what PlayerCard shows -- shared by the own
// profile, a friend's profile and the settings preview.

const STAT_ABBREVIATIONS: Record<TargetStat, string> = {
  strength: 'СИЛ',
  agility: 'ЛОВ',
  intellect: 'ИНТ',
  endurance: 'ВЫН',
  on_ice_skating: 'ЛЁД',
  puck_handling: 'ШАЙ',
}

// Two columns on the card, read row by row: СИЛ/ВЫН, ЛОВ/ЛЁД, ИНТ/ШАЙ.
const CARD_STAT_ORDER: TargetStat[] = ['strength', 'endurance', 'agility', 'on_ice_skating', 'intellect', 'puck_handling']

interface StatValue {
  stat_type: TargetStat
  effective_value: number
}

// All six slots, in card order; a stat the player has no value for yet keeps
// its slot (shown as "—") so the two columns stay paired.
export function cardStatsFrom(stats: readonly StatValue[]): PlayerCardStat[] {
  const byType = new Map(stats.map((stat) => [stat.stat_type, stat.effective_value]))
  return CARD_STAT_ORDER.map((type) => ({ type, label: STAT_ABBREVIATIONS[type], value: byType.get(type) ?? null }))
}

// The card's big number: the average of the stats. Not the leaderboard's
// "рейтинг" (excess over the age/experience norm) -- the card calls it
// "ОБЩИЙ" so the two never read as the same thing.
export function overallRatingOf(stats: readonly StatValue[]): number | null {
  if (stats.length === 0) {
    return null
  }
  return Math.round(stats.reduce((sum, stat) => sum + stat.effective_value, 0) / stats.length)
}
