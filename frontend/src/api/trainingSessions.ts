import { apiGet } from './client'
import type { ExerciseSetsRead, SetCompletionSummary } from '../types/setCompletion'
import { pendingSets, whenQueueLoaded } from '../utils/writeQueue'

export async function getExerciseSets(
  trainingSessionId: string,
  exerciseId: string,
  accessToken: string,
): Promise<ExerciseSetsRead> {
  const path = `/training-sessions/${trainingSessionId}/exercises/${exerciseId}/sets`
  // Б2: sets logged while their write still waits in the offline queue
  // (even with the flag since switched off) count as logged -- and without signal (nothing saved either) the queue
  // alone is what's known.
  await whenQueueLoaded()
  let fromServer: ExerciseSetsRead = { sets: [], feedback: null }
  try {
    fromServer = await apiGet<ExerciseSetsRead>(path, accessToken)
  } catch (err) {
    if (pendingSets(trainingSessionId, exerciseId).length === 0) {
      throw err
    }
  }
  const bySet = new Map<number, SetCompletionSummary>(fromServer.sets.map((set) => [set.set_number, set]))
  for (const body of pendingSets(trainingSessionId, exerciseId)) {
    bySet.set(Number(body.set_number), {
      set_number: Number(body.set_number),
      weight_kg: (body.weight_kg as number | null | undefined) ?? null,
      reps_completed: (body.reps_completed as number | null | undefined) ?? null,
      duration_seconds_completed: (body.duration_seconds_completed as number | null | undefined) ?? null,
      completed_at: String(body.performed_at),
    })
  }
  return { ...fromServer, sets: [...bySet.values()].sort((a, b) => a.set_number - b.set_number) }
}
