import { expect, test } from '@playwright/test'
import { createUser, loginAs } from './helpers'

// Б0 (2026-10-13): the installed app opens with no connection at all. Needs
// a production build with the service worker, served same-origin:
//   VITE_API_BASE_URL=/api npx vite build && npx vite preview --port 4173
//   E2E_BASE_URL=http://localhost:4173 E2E_PREVIEW=1 npx playwright test sw-offline
test.skip(process.env.E2E_PREVIEW !== '1', 'needs a production build (see above)')

const NAV = { name: 'Основная навигация' }

test('opened online once, the app starts offline: logged in, "Нет связи" shown', async ({ page, context }) => {
  const me = await createUser('swoffline', 41, 'forward')
  await loginAs(page, me)
  await page.goto('/')
  await expect(page.getByRole('navigation', NAV)).toBeVisible()
  // The worker has installed (precache done) and controls the page.
  await page.waitForFunction(async () => {
    const registration = await navigator.serviceWorker.ready
    return registration.active !== null && navigator.serviceWorker.controller !== null
  })

  await context.setOffline(true)
  await page.reload()
  await expect(page.getByRole('navigation', NAV)).toBeVisible()
  await expect(page.getByRole('status').filter({ hasText: 'Нет связи' })).toBeVisible()
  await expect(page).not.toHaveURL(/\/login/)

  // A deep link too, and a lazily loaded page.
  await page.goto('/profile')
  await expect(page.getByRole('navigation', NAV)).toBeVisible()

  await context.setOffline(false)
  await page.evaluate(() => window.dispatchEvent(new Event('online')))
  await expect(page.getByRole('status').filter({ hasText: 'Нет связи' })).toBeHidden({ timeout: 20_000 })
})

test('the worker never caches the API or version.json', async ({ page }) => {
  const me = await createUser('swcache', 42, 'forward')
  await loginAs(page, me)
  await page.goto('/')
  await expect(page.getByRole('navigation', NAV)).toBeVisible()
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null)
  const cached = await page.evaluate(async () => {
    const urls: string[] = []
    for (const name of await caches.keys()) {
      const cache = await caches.open(name)
      for (const request of await cache.keys()) {
        urls.push(new URL(request.url).pathname)
      }
    }
    return urls
  })
  expect(cached).toContain('/index.html')
  expect(cached.filter((path) => path.startsWith('/api/') || path.startsWith('/media/') || path.startsWith('/version.json'))).toEqual([])
})
