// One place that knows where the service worker lives (Б0, 2026-10-13):
// src/sw.ts, built to /sw.js; in `vite dev` vite-plugin-pwa serves it as a
// module at /dev-sw.js. Push (src/push.ts) and updates (appUpdate.ts) both
// go through here.

import { PUSH_EVENT } from '../hooks/useLiveRefresh'

const SW_URL = import.meta.env.DEV ? '/dev-sw.js?dev-sw' : '/sw.js'
const SW_OPTIONS: RegistrationOptions = { scope: '/', type: import.meta.env.DEV ? 'module' : 'classic' }

// How long a reload waits for the new worker to take over before going
// ahead anyway -- the network-first page load is up to date either way.
const ACTIVATION_TIMEOUT_MS = 3000

export function isServiceWorkerSupported(): boolean {
  return 'serviceWorker' in navigator
}

// register() is idempotent: the browser reuses the existing registration
// when the script hasn't changed, and starts an update when it has.
let pushForwarding = false

// sw.ts posts {type: 'push'} to open tabs when a push arrives; screens hear
// it as a window event (hooks/useLiveRefresh.ts).
function forwardPushMessages(): void {
  if (pushForwarding) {
    return
  }
  pushForwarding = true
  navigator.serviceWorker.addEventListener('message', (event: MessageEvent) => {
    if (event.data && event.data.type === 'push') {
      window.dispatchEvent(new CustomEvent(PUSH_EVENT, { detail: { url: event.data.url } }))
    }
  })
}

export async function registerAppServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!isServiceWorkerSupported()) {
    return null
  }
  forwardPushMessages()
  try {
    return await navigator.serviceWorker.register(SW_URL, SW_OPTIONS)
  } catch {
    // Best-effort (e.g. blocked on a plain-HTTP LAN IP) -- the app works
    // without it, only offline start and push are lost.
    return null
  }
}

// Asks the browser to look for a new /sw.js now (it otherwise checks on
// navigations, at most once a day).
export async function checkForServiceWorkerUpdate(): Promise<void> {
  if (!isServiceWorkerSupported()) {
    return
  }
  const registration = await navigator.serviceWorker.getRegistration()
  await registration?.update().catch(() => undefined)
}

// A new build's worker installs in the background and then waits -- it
// takes over only here, right before the app reloads at a safe moment, so
// the running screen never has its cached files swapped underneath it.
export async function activateWaitingServiceWorker(): Promise<void> {
  if (!isServiceWorkerSupported()) {
    return
  }
  const registration = await navigator.serviceWorker.getRegistration()
  const waiting = registration?.waiting
  if (!waiting) {
    return
  }
  await new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, ACTIVATION_TIMEOUT_MS)
    navigator.serviceWorker.addEventListener(
      'controllerchange',
      () => {
        clearTimeout(timer)
        resolve()
      },
      { once: true },
    )
    waiting.postMessage({ type: 'SKIP_WAITING' })
  })
}
