import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test } from '@playwright/test'
import { api, createUser, dayPlan, declareWeek, localNow, loginAs, shot } from './helpers'

// Б0 (2026-10-13): the installed app opens with no connection at all. Needs
// a production build with the service worker, served same-origin:
//   VITE_API_BASE_URL=/api npx vite build && npx vite preview --port 4173
//   E2E_BASE_URL=http://localhost:4173 E2E_PREVIEW=1 E2E_DIST=$PWD/dist npx playwright test sw-offline
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

test('online, "/" comes from the server, not the precached build', async ({ page, context }) => {
  const me = await createUser('swroot', 44, 'forward')
  await loginAs(page, me)
  await page.goto('/')
  await expect(page.getByRole('navigation', NAV)).toBeVisible()
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null)
  // "Build B" is on the server now (context.route also sees the worker's
  // own requests in Chromium).
  await context.route(
    (url) => url.pathname === '/' || url.pathname === '/profile',
    (route) =>
      route.fulfill({ contentType: 'text/html', body: '<!doctype html><title>B</title><p id="build-b">build B</p>' }),
  )
  for (const path of ['/', '/profile']) {
    await page.goto(path)
    await expect(page.locator('#build-b')).toBeVisible()
  }
  await context.unrouteAll()
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

test('Б1: the week and the workout opened online show offline after a restart', async ({ page, context }) => {
  const me = await createUser('offdata', 43, 'forward')
  const today = localNow().date
  await declareWeek(me, today)
  const plan = await dayPlan(me, today)
  const full = await api<{ training_session: { blocks: { exercise: { name: string } }[] } | null }>(
    'GET',
    `/schedule/day-plans/${plan.id}`,
    { token: me.token },
  )
  const firstExercise = full.training_session?.blocks[0]?.exercise.name
  expect(firstExercise).toBeTruthy()

  await loginAs(page, me)
  await page.goto('/')
  await expect(page.getByRole('navigation', NAV)).toBeVisible()
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null)
  await page.goto(`/training/${plan.id}`)
  await expect(page.getByText(firstExercise!).first()).toBeVisible()

  await context.setOffline(true)
  await page.reload()
  await expect(page.getByText(firstExercise!).first()).toBeVisible()
  await expect(page.getByRole('status').filter({ hasText: /Нет связи.*данные от/ })).toBeVisible()

  // Home (today + the week) too, without having been opened since the restart.
  await page.goto('/')
  await expect(page.getByRole('navigation', NAV)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Начать тренировку' })).toBeVisible()
  await shot(page, 'offline-home')
  await context.setOffline(false)
})

test('Б1: sign-out leaves no saved data behind', async ({ page }) => {
  const me = await createUser('offclear', 44, 'forward')
  await declareWeek(me, localNow().date)
  await loginAs(page, me)
  await page.goto('/')
  await expect(page.getByRole('navigation', NAV)).toBeVisible()
  const savedCount = () =>
    page.evaluate(
      () =>
        new Promise<number>((resolve) => {
          const open = indexedDB.open('icelevel-offline')
          open.onsuccess = () => {
            const db = open.result
            if (!db.objectStoreNames.contains('responses')) {
              resolve(0)
              return
            }
            const count = db.transaction('responses').objectStore('responses').count()
            count.onsuccess = () => resolve(count.result)
          }
          open.onerror = () => resolve(-1)
        }),
    )
  await expect.poll(savedCount, { timeout: 15_000 }).toBeGreaterThan(0)
  await page.goto('/settings/account')
  await page.getByRole('button', { name: 'Выйти из аккаунта' }).click()
  await expect(page).toHaveURL(/\/login/)
  await expect.poll(savedCount).toBe(0)
})

test('the emergency worker (sw-safe.js over sw.js) clears every cache and keeps the registration', async ({
  page,
}) => {
  // Swaps the file in the served build, exactly what docs/deploy.md does on
  // the server -- needs E2E_DIST pointing at the folder `vite preview` serves.
  test.skip(process.env.E2E_DIST === undefined, 'set E2E_DIST to the served dist/ folder')
  const dist = process.env.E2E_DIST!
  const me = await createUser('swsafe', 45, 'forward')
  await loginAs(page, me)
  await page.goto('/')
  await expect(page.getByRole('navigation', NAV)).toBeVisible()
  await page.waitForFunction(async () => {
    const registration = await navigator.serviceWorker.ready
    return registration.active !== null && navigator.serviceWorker.controller !== null && (await caches.keys()).length > 0
  })

  const swPath = join(dist, 'sw.js')
  const original = readFileSync(swPath)
  const safe = readFileSync(join(dist, 'sw-safe.js'), 'utf8')
  expect(safe).toContain('skipWaiting')
  expect(safe).not.toMatch(/addEventListener\(['"]fetch/)
  try {
    writeFileSync(swPath, safe)
    await page.evaluate(async () => {
      const registration = await navigator.serviceWorker.ready
      await registration.update()
    })
    // Usually it takes over the open tab at once; at the latest when the
    // app is opened again.
    const reopened = await page.context().newPage()
    await page.close()
    await reopened.goto('/')
    await expect
      .poll(async () => reopened.evaluate(async () => (await caches.keys()).length).catch(() => -1), { timeout: 20_000 })
      .toBe(0)
    await expect(reopened.getByRole('navigation', NAV)).toBeVisible()
    // No fetch handler: a reload is a plain network load and caches nothing.
    await reopened.reload()
    await expect(reopened.getByRole('navigation', NAV)).toBeVisible()
    expect(await reopened.evaluate(async () => (await caches.keys()).length)).toBe(0)
    const registered = await reopened.evaluate(async () => (await navigator.serviceWorker.getRegistrations()).length)
    expect(registered).toBe(1)
  } finally {
    writeFileSync(swPath, original)
  }
})
