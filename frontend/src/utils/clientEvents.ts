// Tells the server what went wrong on this phone (15.10): POST
// /client-events -> a warning in the backend log and GlitchTip. Fire and
// forget -- never throws, never waits, at most once per kind+message per
// app start, and nothing about the player beyond what the message says.

type ClientEventKind = 'sw_register_failed' | 'queue_action_failed' | 'app_error'

const sent = new Set<string>()
const MAX_PER_START = 20

export function reportClientEvent(kind: ClientEventKind, message: string, detail?: string | null): void {
  const key = `${kind}:${message}`
  if (sent.has(key) || sent.size >= MAX_PER_START) {
    return
  }
  sent.add(key)
  try {
    void fetch(`${import.meta.env.VITE_API_BASE_URL}/client-events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        kind,
        message: message.slice(0, 500),
        detail: detail ? detail.slice(0, 2000) : null,
        path: window.location.pathname.slice(0, 300),
        app_version: __APP_BUILD_ID__,
      }),
      keepalive: true,
    }).catch(() => undefined)
  } catch {
    // Reporting must never break anything.
  }
}
