import type { TeamEventDrillRead, TeamEventDrillSectionRead } from '../types/teamEvent'

// Sum of the drills' planned minutes -- null when none of them has one, so
// a board without durations shows nothing rather than "0 мин".
export function totalMinutes(drills: TeamEventDrillRead[]): number | null {
  const known = drills.filter((drill) => drill.duration_minutes !== null)
  if (known.length === 0) {
    return null
  }
  return known.reduce((sum, drill) => sum + (drill.duration_minutes ?? 0), 0)
}

export function boardTotalMinutes(sections: TeamEventDrillSectionRead[]): number | null {
  return totalMinutes(sections.flatMap((section) => section.drills))
}

export function formatMinutes(minutes: number): string {
  return `${minutes} мин`
}
