// Same tiered thresholds as max_skill_preferences_for_level in
// app/core/skill_preferences.py (backend) -- mirrored here so the skill
// picker can show "Выбрано X из Y" and disable further picks without a
// round trip. null means unlimited (level 25+).
const SKILL_PREFERENCE_CAPS: [threshold: number, cap: number][] = [
  [8, 3],
  [15, 6],
  [25, 9],
]

export function maxSkillPreferencesForLevel(level: number): number | null {
  for (const [threshold, cap] of SKILL_PREFERENCE_CAPS) {
    if (level < threshold) {
      return cap
    }
  }
  return null
}
