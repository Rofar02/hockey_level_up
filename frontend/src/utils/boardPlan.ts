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

export interface BoardStats {
  sections: number
  drills: number
  minutes: number | null
}

export function boardStats(sections: TeamEventDrillSectionRead[]): BoardStats {
  return {
    sections: sections.length,
    drills: sections.reduce((sum, section) => sum + section.drills.length, 0),
    minutes: boardTotalMinutes(sections),
  }
}

// Russian plural: pluralRu(3, ['раздел', 'раздела', 'разделов']) -> 'раздела'.
export function pluralRu(count: number, forms: [string, string, string]): string {
  const mod10 = count % 10
  const mod100 = count % 100
  if (mod10 === 1 && mod100 !== 11) {
    return forms[0]
  }
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return forms[1]
  }
  return forms[2]
}

// "3 раздела · 8 упражнений · 85 мин" -- null for an empty board.
export function boardSummaryText(sections: TeamEventDrillSectionRead[]): string | null {
  const stats = boardStats(sections)
  if (stats.drills === 0) {
    return null
  }
  const parts = [
    `${stats.sections} ${pluralRu(stats.sections, ['раздел', 'раздела', 'разделов'])}`,
    `${stats.drills} ${pluralRu(stats.drills, ['упражнение', 'упражнения', 'упражнений'])}`,
  ]
  if (stats.minutes !== null) {
    parts.push(formatMinutes(stats.minutes))
  }
  return parts.join(' · ')
}
