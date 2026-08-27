import { useState } from 'react'

// Backs every <Coachmark> in the app -- "seen" is per-device (localStorage),
// not synced from the backend, since a coachmark is a one-time hint about
// how a screen works, not user data that needs to follow them across
// devices. Keyed by a caller-supplied id (e.g. "schedule-week-tabs",
// "profile-stat-unlocks") so each hint is dismissed independently; ids must
// be unique app-wide, same requirement as a React `key`.
const STORAGE_PREFIX = 'coachmark:'

function readSeen(id: string): boolean {
  try {
    return localStorage.getItem(STORAGE_PREFIX + id) !== null
  } catch {
    // Private browsing / storage disabled -- treat as "never seen" rather
    // than crash; worst case the hint reappears every visit for that user.
    return false
  }
}

export function useCoachmark(id: string): { shouldShow: boolean; dismiss: () => void } {
  const [seen, setSeen] = useState(() => readSeen(id))

  function dismiss() {
    setSeen(true)
    try {
      localStorage.setItem(STORAGE_PREFIX + id, '1')
    } catch {
      // Best-effort -- see readSeen; the hint just won't stay dismissed
      // across a reload in that case.
    }
  }

  return { shouldShow: !seen, dismiss }
}
