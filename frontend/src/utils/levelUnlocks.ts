// Mirrors app.core.level_unlocks (backend) for display -- same convention
// as skillPreferenceLimit.ts's own mirror of the skill-slot tiers.
export const LEVEL_AVATAR_RING_CHOICE = 10
export const LEVEL_JERSEY_COLOR_CHOICE = 15

export function hasAvatarRingChoice(level: number): boolean {
  return level >= LEVEL_AVATAR_RING_CHOICE
}

export function hasJerseyColorChoice(level: number): boolean {
  return level >= LEVEL_JERSEY_COLOR_CHOICE
}

export interface LevelMilestone {
  level: number
  label: string
}

// Flat display list of every level-gated perk, for the level badge's "what
// does this open" modal -- a human-readable view of the same thresholds
// app.core.level_unlocks encodes as lookup tables (_SKILL_SLOT_TIERS,
// LEVEL_AVATAR_RING_CHOICE, LEVEL_JERSEY_COLOR_CHOICE). Keep in sync with
// that module if the tiers ever change.
export const LEVEL_MILESTONES: LevelMilestone[] = [
  { level: 1, label: '3 слота под приоритетные навыки' },
  { level: 5, label: '4-й слот под приоритетный навык' },
  { level: 10, label: '5-й слот, выбор акцента кольца аватарки' },
  { level: 15, label: '6-й слот (максимум), выбор цвета номера на джерси' },
]
