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
