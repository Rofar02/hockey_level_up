import { useSyncExternalStore } from 'react'
import { failedActions, pendingCount, subscribeQueue } from '../utils/writeQueue'
import type { FailedAction } from '../utils/writeQueue'

// How many workout writes still wait in the offline queue (Б2).
export function usePendingWrites(): number {
  return useSyncExternalStore(subscribeQueue, pendingCount, () => 0)
}

let failedSnapshot: FailedAction[] = []
let failedKey = ''

function failedSnapshotNow(): FailedAction[] {
  const next = failedActions()
  const key = next.map((item) => item.key).join(',')
  if (key !== failedKey) {
    failedKey = key
    failedSnapshot = next
  }
  return failedSnapshot
}

// Writes the server refused after the fact (day rebuilt, exercise gone).
export function useFailedWrites(): FailedAction[] {
  return useSyncExternalStore(subscribeQueue, failedSnapshotNow, () => failedSnapshot)
}
