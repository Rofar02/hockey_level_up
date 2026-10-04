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
