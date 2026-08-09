export function isPushSupported(): boolean {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
}

// Called once at app startup so the worker is already active by the time
// the user opens Settings and toggles notifications on -- register() is
// idempotent (the browser reuses the existing registration when the script
// hasn't changed), so calling it again lazily from getRegistration() below
// is harmless.
export function registerServiceWorker(): void {
  if (!('serviceWorker' in navigator)) {
    return
  }
  navigator.serviceWorker.register('/sw.js').catch(() => {
    // Best-effort -- push notifications are an enhancement, not something
    // the rest of the app depends on (e.g. blocked on a plain-HTTP LAN IP).
  })
}

function urlBase64ToUint8Array(base64Url: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (base64Url.length % 4)) % 4)
  const base64 = (base64Url + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = window.atob(base64)
  const output = new Uint8Array(rawData.length)
  for (let i = 0; i < rawData.length; i += 1) {
    output[i] = rawData.charCodeAt(i)
  }
  return output
}

async function getRegistration(): Promise<ServiceWorkerRegistration | null> {
  if (!isPushSupported()) {
    return null
  }
  try {
    return await navigator.serviceWorker.register('/sw.js')
  } catch {
    return null
  }
}

export async function getActivePushSubscription(): Promise<PushSubscription | null> {
  const registration = await getRegistration()
  if (registration === null) {
    return null
  }
  return registration.pushManager.getSubscription()
}

export async function subscribeToPush(vapidPublicKey: string): Promise<PushSubscription> {
  const registration = await getRegistration()
  if (registration === null) {
    throw new Error('Service worker недоступен в этом браузере.')
  }
  return registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
  })
}
