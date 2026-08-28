import type { ExerciseRead } from '../types/exercise'

export type ExercisePlayerMode = 'duration' | 'sets_reps' | 'none'

// Which of ExerciseFocusScreen's two player modes an exercise gets --
// icelevel_player_master_prompt.md (2026-08-28): "брать из существующего
// атрибута ... если единого флага нет — вывести режим из наличия полей".
// ExerciseRead.exercise_type (SETS_REPS/DURATION) exists but is null on
// nearly every catalog row today (see app/models/exercise.py's own
// comment), so it can't be the sole source yet -- target_duration_seconds
// vs target_sets+rep_range is the reliable signal, matching every real
// exercise seen in the catalog so far (never both set on one row).
// target_duration_seconds wins when somehow both are present, since a
// duration exercise with target_sets set just means "N timed rounds", not
// a reps exercise.
export function exercisePlayerMode(exercise: ExerciseRead): ExercisePlayerMode {
  if (exercise.target_duration_seconds !== null) {
    return 'duration'
  }
  if (exercise.target_sets !== null) {
    return 'sets_reps'
  }
  return 'none'
}
