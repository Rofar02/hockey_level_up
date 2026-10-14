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

// "Пас в крюк, Скорость" -> up to 3 cues of up to 20 characters (the
// server's limits), the rest dropped.
export const MAX_DRILL_KEYWORDS = 3
export const MAX_DRILL_KEYWORD_LENGTH = 20

// Same cleaning as the server (review 14.10, 24): invisible characters go,
// line breaks and runs of spaces become one space, repeats (any case) once.
// oxlint-disable-next-line no-control-regex -- control characters are exactly what goes
const INVISIBLE = /[\u0000-\u001f\u007f-\u009f\u00ad\u200b-\u200f\u2028-\u202e\u2060-\u2064\ufeff]/g

function keywordParts(value: string): string[] {
  const seen = new Set<string>()
  const parts: string[] = []
  for (const raw of value.split(',')) {
    const word = raw.replace(/\s+/g, ' ').replace(INVISIBLE, '').trim()
    if (word !== '' && !seen.has(word.toLowerCase())) {
      seen.add(word.toLowerCase())
      parts.push(word)
    }
  }
  return parts
}

export function parseKeywords(value: string): string[] {
  return keywordParts(value)
    .map((part) => part.slice(0, MAX_DRILL_KEYWORD_LENGTH).trim())
    .slice(0, MAX_DRILL_KEYWORDS)
}

// Whether parseKeywords had to cut something (a 4th cue, a long one) -- the
// editor says so instead of quietly saving less than was typed.
export function keywordsWereTrimmed(value: string): boolean {
  const parts = keywordParts(value)
  return parts.length > MAX_DRILL_KEYWORDS || parts.some((part) => part.length > MAX_DRILL_KEYWORD_LENGTH)
}
