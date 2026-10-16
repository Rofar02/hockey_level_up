import { expect, test } from '@playwright/test'
import { API_URL, createUser, loginAs } from './helpers'

// Offline (2026-10-13): no signal at the rink must never look like being
// logged out. Only the server's own 401/403 ends a session.

const NAV = { name: 'Основная навигация' }

test('no connection at start keeps the player logged in', async ({ page }) => {
  const me = await createUser('offline', 31, 'forward')
  await loginAs(page, me)
  await page.goto('/')
  await expect(page.getByRole('navigation', NAV)).toBeVisible()

  await page.route(`${API_URL}/**`, (route) => route.abort('internetdisconnected'))
  await page.reload()
  await expect(page.getByRole('navigation', NAV)).toBeVisible()
  await expect(page).not.toHaveURL(/\/login/)
  expect(await page.evaluate(() => localStorage.getItem('hlu_refresh_token'))).toBe(me.refreshToken)

  // Back online: the session is checked for real and the app carries on.
  await page.unroute(`${API_URL}/**`)
  await page.evaluate(() => window.dispatchEvent(new Event('online')))
  await expect(page.getByRole('navigation', NAV)).toBeVisible()
})

test('a 503 or 429 from the server is not a logout', async ({ page }) => {
  const me = await createUser('flaky', 32, 'forward')
  await loginAs(page, me)
  await page.goto('/')
  await expect(page.getByRole('navigation', NAV)).toBeVisible()

  for (const status of [503, 429]) {
    await page.route(`${API_URL}/**`, (route) => route.fulfill({ status, body: 'busy' }))
    await page.reload()
    await expect(page.getByRole('navigation', NAV)).toBeVisible()
    await expect(page).not.toHaveURL(/\/login/)
    await page.unroute(`${API_URL}/**`)
  }
})

test('a refresh token the server rejects does log out', async ({ page }) => {
  const me = await createUser('expired', 33, 'forward')
  await loginAs(page, me)
  await page.evaluate(() => {
    localStorage.setItem('hlu_access_token', 'not-a-token')
    localStorage.setItem('hlu_refresh_token', 'not-a-token')
  })
  await page.goto('/')
  await expect(page).toHaveURL(/\/login/)
  expect(await page.evaluate(() => localStorage.getItem('hlu_refresh_token'))).toBeNull()
})

test('a server that hangs at start opens the app on the snapshot within seconds', async ({ page }) => {
  // Review 14.10 (3): one bar of signal -- the check never answers in time.
  const me = await createUser('slow', 34, 'forward')
  await loginAs(page, me)
  await page.goto('/')
  await expect(page.getByRole('navigation', NAV)).toBeVisible()

  // No saved answers to fall back on (wiped, or the first start after an
  // update) -- only the session snapshot is left.
  await page.evaluate(
    () =>
      new Promise((resolve) => {
        const request = indexedDB.deleteDatabase('icelevel-offline')
        request.onsuccess = request.onerror = request.onblocked = () => resolve(null)
      }),
  )
  await page.route(`${API_URL}/**`, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 15_000))
    await route.continue().catch(() => undefined)
  })
  const started = Date.now()
  await page.reload()
  // 4 s for the check plus the page's own load; the hung server takes 15.
  await expect(page.getByRole('navigation', NAV)).toBeVisible({ timeout: 11_000 })
  expect(Date.now() - started).toBeLessThan(11_000)
  await expect(page).not.toHaveURL(/\/login/)
  await page.unroute(`${API_URL}/**`)
})

test('signing out in another tab signs this one out too', async ({ page, context }) => {
  // Review 14.10 (6).
  const me = await createUser('twotabs', 35, 'forward')
  await loginAs(page, me)
  await page.goto('/')
  await expect(page.getByRole('navigation', NAV)).toBeVisible()
  const other = await context.newPage()
  await other.goto('/')
  await expect(other.getByRole('navigation', NAV)).toBeVisible()
  await other.evaluate(() => {
    localStorage.removeItem('hlu_access_token')
    localStorage.removeItem('hlu_refresh_token')
  })
  await expect(page).toHaveURL(/\/login/)
  await other.close()
})
