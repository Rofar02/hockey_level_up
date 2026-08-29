// Same tiered thresholds as max_skill_slots_for_level in
// app/core/level_unlocks.py (backend) -- mirrored here so the skill picker
// can show "Выбрано X из Y" and disable further picks without a round
// trip. Hard-capped at 6 from level 15 on -- no unlimited tier (retuned
// 2026-08-30, see that module's own docstring for why the numbers moved).
const SKILL_SLOT_TIERS: [threshold: number, cap: number][] = [
  [5, 3],
  [10, 4],
  [15, 5],
]
export const SKILL_SLOT_CAP = 6

export function maxSkillPreferencesForLevel(level: number): number {
  for (const [threshold, cap] of SKILL_SLOT_TIERS) {
    if (level < threshold) {
      return cap
    }
  }
  return SKILL_SLOT_CAP
}
