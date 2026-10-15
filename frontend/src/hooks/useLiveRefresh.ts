import { useEffect, useRef } from 'react'

// Keeps a screen's "something new arrived" numbers current without a reload
// (15.10: a captain's list of join requests only changed on a page reload).
// `refresh` runs:
// - when a push arrives while the app is open (sw.ts forwards it, see
//   utils/serviceWorker.ts -> PUSH_EVENT);
// - when the app comes back to the foreground;
// - every `intervalMs` while it's visible (a fallback for phones without
//   push).
export const PUSH_EVENT = 'icelevel:push'

export function useLiveRefresh(refresh: () => void, { enabled = true, intervalMs = 60_000 } = {}): void {
  const latest = useRef(refresh)
  useEffect(() => {
    latest.current = refresh
  })

  useEffect(() => {
    if (!enabled) {
      return
    }
    const run = () => {
      if (document.visibilityState === 'visible') {
        latest.current()
      }
    }
    window.addEventListener(PUSH_EVENT, run)
    document.addEventListener('visibilitychange', run)
    const timer = window.setInterval(run, intervalMs)
    return () => {
      window.removeEventListener(PUSH_EVENT, run)
      document.removeEventListener('visibilitychange', run)
      window.clearInterval(timer)
    }
  }, [enabled, intervalMs])
}
