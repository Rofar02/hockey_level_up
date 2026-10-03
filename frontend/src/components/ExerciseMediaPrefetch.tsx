import { useEffect } from 'react'
import type { ExerciseRead } from '../types/exercise'
import { prefetchExerciseMedia } from '../utils/media'

// Renders nothing: while the athlete works through one exercise, this warms
// the browser cache with the NEXT exercise's poster and clip so it starts
// instantly when the player auto-advances. Only self-hosted clips are
// prefetched, and prefetchExerciseMedia itself backs off on data-saver mode
// and slow connections.
export function ExerciseMediaPrefetch({ exercise }: { exercise: ExerciseRead | null }) {
  const videoId =
    exercise !== null && exercise.video_source_type === 'file' ? exercise.video_source_id : null

  useEffect(() => {
    if (videoId !== null) {
      prefetchExerciseMedia(videoId)
    }
  }, [videoId])

  return null
}
