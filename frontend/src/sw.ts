// The service worker (Б0, 2026-10-13): the app opens without a connection.
// Built by vite-plugin-pwa (injectManifest) into /sw.js -- the same URL the
// push-only worker had, so installed phones just update in place.
//
// - Precache: index.html, every hashed asset (js, css, fonts), icons,
//   manifest -- the list comes from the build (self.__WB_MANIFEST).
// - Navigations: network first (3 s), the cached index.html without signal.
// - /assets/*: cache first -- a lazy chunk of the running build stays
//   loadable offline even after the precache moved on.
// - /api/*, /media/*, /version.json: never touched here -- the browser goes
//   straight to the network (the API's own offline data lives in IndexedDB).
// - A new version waits until the app says it's a safe moment
//   (utils/appUpdate.ts: never in the middle of a workout).
import { cleanupOutdatedCaches, matchPrecache, precacheAndRoute, type PrecacheEntry } from 'workbox-precaching'
import { NavigationRoute, registerRoute } from 'workbox-routing'
import { CacheFirst } from 'workbox-strategies'
import { ExpirationPlugin } from 'workbox-expiration'

declare const self: ServiceWorkerGlobalScope & { __WB_MANIFEST: (string | PrecacheEntry)[] }

const NAVIGATION_TIMEOUT_MS = 3000
const ASSETS_CACHE = 'icelevel-assets'
const NEVER_HANDLED = [/^\/api\//, /^\/media\//, /^\/version\.json/]

precacheAndRoute(self.__WB_MANIFEST)
cleanupOutdatedCaches()

function delay(ms: number): Promise<'timeout'> {
  return new Promise((resolve) => setTimeout(() => resolve('timeout'), ms))
}

registerRoute(
  new NavigationRoute(
    async ({ request }) => {
      const live = fetch(request).then(
        (response) => response,
        () => null,
      )
      const first = await Promise.race([live, delay(NAVIGATION_TIMEOUT_MS)])
      // A gateway error page (deploy in progress) is worse than the app.
      if (first !== 'timeout' && first !== null && first.status < 500) {
        return first
      }
      const shell = await matchPrecache('/index.html')
      if (shell) {
        return shell
      }
      // Nothing cached yet (first visit, `vite dev`): the network is all
      // there is, however slow.
      const late = first === 'timeout' ? await live : first
      return late ?? Response.error()
    },
    { denylist: NEVER_HANDLED },
  ),
)

registerRoute(
  ({ url, request }) =>
    url.origin === self.location.origin && url.pathname.startsWith('/assets/') && request.method === 'GET',
  new CacheFirst({
    cacheName: ASSETS_CACHE,
    plugins: [new ExpirationPlugin({ maxEntries: 300, maxAgeSeconds: 60 * 60 * 24 * 60 })],
  }),
)

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    void self.skipWaiting()
  }
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      // Anything not ours any more (the precache of older builds is
      // cleaned up by workbox itself above).
      const known = new Set([ASSETS_CACHE])
      for (const name of await caches.keys()) {
        if (!name.startsWith('workbox-precache') && !known.has(name)) {
          await caches.delete(name)
        }
      }
      await self.clients.claim()
    })(),
  )
})

// -- Web Push (moved here from public/sw.js) --

self.addEventListener('push', (event) => {
  const data = event.data ? event.data.json() : {}
  const title = data.title || 'IceLevel'
  event.waitUntil(
    self.registration.showNotification(title, {
      body: data.body,
      icon: '/favicon.png',
      // Optional in-app path to open on tap (e.g. /admin/feedback).
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
