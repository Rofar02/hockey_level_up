// The emergency service worker (15.10). Not part of the normal build's
// registration -- scripts/build-sw-safe.mjs only puts it next to sw.js as
// /sw-safe.js. If a release ever leaves installed phones stuck on a broken
// build (white screen, a page that never loads), it is copied over /sw.js on
// the server (docs/deploy.md, "Аварийный service worker"): every phone that
// opens the app picks it up as an ordinary update and
//
// - takes over at once (no waiting for a "safe moment" -- that logic lives
//   in the broken build);
// - deletes every cache, so nothing old is served any more;
// - has no fetch handler: the browser goes straight to the network, the app
//   works like a plain website;
// - reloads the open tabs so they start on the server's current build.
//
// Push stays exactly as in sw.ts. Never `registration.unregister()`: that
// drops the push subscription, and the players would stop getting
// notifications without knowing it.
//
// The next normal deploy rebuilds sw.js and the phones go back to the full
// worker (precache, offline) by themselves.
//
// No imports: compiled on its own (scripts/build-sw-safe.mjs), not bundled.

declare const self: ServiceWorkerGlobalScope

self.addEventListener('install', (event) => {
  event.waitUntil(self.skipWaiting())
})

// The broken build's own update flow (utils/serviceWorker.ts) may still ask
// a waiting worker to take over -- say yes.
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    void self.skipWaiting()
  }
})

self.addEventListener('activate', (event) => {
  const cleaned = (async () => {
    for (const name of await caches.keys()) {
      await caches.delete(name)
    }
    await self.clients.claim()
  })()
  event.waitUntil(cleaned)
  // Outside waitUntil: a tab's reload is itself waiting for this worker to
  // finish activating -- awaiting it here would deadlock.
  void cleaned.then(async () => {
    const windows = await self.clients.matchAll({ type: 'window' })
    for (const client of windows) {
      // A tab on a broken build may never ask for an update itself.
      void client.navigate(client.url).catch(() => undefined)
    }
  })
})

// -- Web Push (same as sw.ts) --

self.addEventListener('push', (event) => {
  const data = event.data ? event.data.json() : {}
  const title = data.title || 'IceLevel'
  event.waitUntil(
    self.registration.showNotification(title, {
      body: data.body,
      icon: '/favicon.png',
      data: { url: data.url },
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = event.notification.data && event.notification.data.url
  // Same-origin paths only.
  const target = typeof url === 'string' && url.startsWith('/') && !url.startsWith('//') ? url : '/'
  event.waitUntil(self.clients.openWindow(target))
})
