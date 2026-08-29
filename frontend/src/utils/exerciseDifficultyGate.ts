import type { ExerciseRead } from '../types/exercise'
import type { UserStatRead } from '../types/progress'

// Mirrors app.core.training_block._LEVEL_DIFFICULTY_CAPS (on-ice) and
// app.core.stat_difficulty._STAT_DIFFICULTY_BANDS (off-ice) for display only
// -- same "client-side mirror of a core formula" convention as
// TrainingSessionPage's estimateExerciseSeconds. Deliberately the *baseline*
// unlock threshold only: the real assembly pipeline also applies a momentary
// overload throttle on top (app.core.training_block.effective_difficulty_cap)
// that isn't included here -- that's a temporary recovery brake, not a
// stable "what do I need to grow to reach this" answer, and folding it in
// would make the catalog's lock state flicker for reasons unrelated to the
// player's own progress.

// level < 8 -> cap 2; level < 15 -> cap 3; else no cap (5) --
// _LEVEL_DIFFICULTY_CAPS inverted to "min level needed for this difficulty".
export function requiredLevelForOnIceDifficulty(difficultyLevel: number): number {
  if (difficultyLevel <= 2) {
    return 1
  }
  if (difficultyLevel === 3) {
    return 8
  }
  return 15
}

// stat < 20 -> cap 1; < 40 -> cap 2; < 60 -> cap 3; < 80 -> cap 4; else no
// cap (5) -- _STAT_DIFFICULTY_BANDS inverted the same way.
export function requiredStatForOffIceDifficulty(difficultyLevel: number): number {
  if (difficultyLevel <= 1) {
    return 0
  }
  return (difficultyLevel - 1) * 20
}

export type ExerciseLockState =
  | { locked: false }
  | { locked: true; reason: 'level'; requiredLevel: number }
  | { locked: true; reason: 'stat'; statLabel: string; requiredValue: number }
  // No primary target_stat tagged at all (a catalog gap, not a real
  // progression path) -- matches app.core.stat_difficulty's own
  // UNCLASSIFIED_EXERCISE_CAP treatment (always capped at 1) rather than
  // inventing a stat name/threshold that doesn't exist.
  | { locked: true; reason: 'unclassified' }

export function getExerciseLockState(
  exercise: ExerciseRead,
  userLevel: number,
  stats: UserStatRead[],
  statLabels: Record<string, string>,
): ExerciseLockState {
  if (exercise.category === 'on_ice') {
    const requiredLevel = requiredLevelForOnIceDifficulty(exercise.difficulty_level)
    if (userLevel >= requiredLevel) {
      return { locked: false }
    }
    return { locked: true, reason: 'level', requiredLevel }
  }

  const primaryStat = exercise.target_stats[0]
  if (primaryStat === undefined) {
    return exercise.difficulty_level <= 1 ? { locked: false } : { locked: true, reason: 'unclassified' }
  }

  const requiredValue = requiredStatForOffIceDifficulty(exercise.difficulty_level)
  const effectiveValue = stats.find((stat) => stat.stat_type === primaryStat)?.effective_value ?? 0
  if (effectiveValue >= requiredValue) {
    return { locked: false }
  }
  return { locked: true, reason: 'stat', statLabel: statLabels[primaryStat], requiredValue }
}
