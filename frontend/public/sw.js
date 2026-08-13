self.addEventListener('push', (event) => {
  const data = event.data ? event.data.json() : {}
  const title = data.title || 'IceLevel'
  event.waitUntil(
    self.registration.showNotification(title, {
      body: data.body,
      icon: '/favicon.png',
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  event.waitUntil(self.clients.openWindow('/'))
})
