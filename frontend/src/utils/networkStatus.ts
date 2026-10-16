// "Is there a connection?" for the whole app (Б0, 2026-10-13). navigator.onLine
// alone lies both ways on a phone at the rink (a Wi-Fi with no internet says
// "online"), so a request that fails at the network level also counts as
// offline, and any answer from the server counts as online again. While
// offline a cheap probe retries every few seconds, so the banner goes away
// without the player having to do anything.

type Listener = () => void

const PROBE_INTERVAL_MS = 15_000

let online = typeof navigator === 'undefined' ? true : navigator.onLine !== false
const listeners = new Set<Listener>()
let probeTimer: ReturnType<typeof setInterval> | null = null

function emit() {
  for (const listener of listeners) {
    listener()
  }
}

async function probe() {
  try {
    const response = await fetch(`/version.json?probe=${Date.now()}`, { cache: 'no-store' })
    // Any answer at all means the network is there (a 404 in `vite dev` too).
    if (response.status > 0) {
      markOnline()
    }
  } catch {
    // Still offline.
  }
}

function setOnline(next: boolean) {
  if (next === online) {
    return
  }
  online = next
  if (!online && probeTimer === null) {
    probeTimer = setInterval(() => void probe(), PROBE_INTERVAL_MS)
  }
  if (online && probeTimer !== null) {
    clearInterval(probeTimer)
    probeTimer = null
  }
  emit()
}

export function markOnline(): void {
  setOnline(true)
}

export function markOffline(): void {
  setOnline(false)
}

export function isOnline(): boolean {
  return online
}

export function subscribeNetworkStatus(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

// A fetch that failed before any response (TypeError), not an HTTP error.
export function isNetworkError(err: unknown): boolean {
  return err instanceof TypeError
}

if (typeof window !== 'undefined') {
  window.addEventListener('online', () => {
    // The OS says the radio is back -- let a real request confirm it.
    void probe()
  })
  window.addEventListener('offline', markOffline)
}
