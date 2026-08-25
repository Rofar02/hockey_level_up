// Mirrors xp_to_next_level in app/events/handlers/block_completed.py -- that
// file (the xp_consumer event handler) is the source of truth for the
// actual level-up write; this is purely cosmetic (an XP-bar fill percentage)
// so a client-side duplicate is fine, same reasoning as avatarTier.ts's own
// duplicated level thresholds.
export function xpToNextLevel(level: number): number {
  return Math.round(100 * 1.2 ** (level - 1))
}
