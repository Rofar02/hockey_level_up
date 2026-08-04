import type { ExerciseRead } from '../types/exercise'

// description !== null alone doesn't guard against an empty string ("" is
// not null) -- trim() so a blank/whitespace-only description doesn't count
// as real content.
export function hasExerciseDescription(exercise: ExerciseRead): boolean {
  return exercise.description !== null && exercise.description.trim() !== ''
}

export function hasExerciseVideo(exercise: ExerciseRead): boolean {
  return (
    (exercise.video_source_type === 'youtube' || exercise.video_source_type === 'vk') &&
    exercise.video_source_id !== null
  )
}

export function hasExerciseTechnique(exercise: ExerciseRead): boolean {
  return hasExerciseVideo(exercise) || hasExerciseDescription(exercise)
}
