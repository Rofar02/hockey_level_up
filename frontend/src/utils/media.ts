import { API_BASE_URL } from '../api/client'

// Where the exercise clips and their poster frames live. One setting so the
// files can move (a bigger disk, object storage, a CDN) without touching any
// player code:
//  - production: nginx serves them straight from disk at
//    /media/exercise-videos (VITE_MEDIA_BASE_URL, baked in at build time);
//  - local dev: the backend's /static mount does (the default below).
export const EXERCISE_MEDIA_BASE_URL: string =
  import.meta.env.VITE_MEDIA_BASE_URL || `${API_BASE_URL}/static/exercise-videos`

export function exerciseVideoUrl(id: string): string {
  return `${EXERCISE_MEDIA_BASE_URL}/${id}.mp4`
}

export function exercisePosterUrl(id: string): string {
  return `${EXERCISE_MEDIA_BASE_URL}/${id}.jpg`
}

interface NetworkInformationLike {
  saveData?: boolean
  effectiveType?: string
}

// Warming the cache for the NEXT exercise only makes sense on a decent,
// unmetered-feeling connection: never with the browser's data-saver on, and
// not on 2g/3g-class links where it would compete with the clip being watched.
// Browsers without the Network Information API (Safari, Firefox) are treated
// as fine -- the clips are ~1 MB, so the downside is small.
export function canPrefetchMedia(): boolean {
  const connection = (navigator as Navigator & { connection?: NetworkInformationLike }).connection
  if (connection === undefined) {
    return true
  }
  if (connection.saveData === true) {
    return false
  }
  return connection.effectiveType === undefined || connection.effectiveType === '4g'
}

// Fire-and-forget: pulls the poster and the clip into the HTTP cache so the
// next exercise starts instantly. Failures are irrelevant (the real player
// just loads it normally), so they are swallowed.
export function prefetchExerciseMedia(id: string): void {
  if (!canPrefetchMedia()) {
    return
  }
  const poster = new Image()
  poster.src = exercisePosterUrl(id)
  fetch(exerciseVideoUrl(id), { cache: 'force-cache' }).catch(() => undefined)
}
