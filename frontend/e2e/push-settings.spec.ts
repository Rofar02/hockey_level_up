import { expect, test } from '@playwright/test'
import { createUser, loginAs } from './helpers'

// 16.10: turning pushes off saves reminder_preference='none' first -- the
// next sign-in subscribes the phone again unless it says 'none'. A failed
// save keeps the subscription and shows the error.

test('pushes off: a failed save keeps the subscription, a good one drops it', async ({ page }) => {
  const player = await createUser('player', 9, 'forward')
  // A subscribed browser, without a real push service: getSubscription()
  // answers with a stand-in that records its unsubscribe().
  await page.addInitScript(() => {
    const w = window as unknown as { __unsubscribed: boolean }
    w.__unsubscribed = false
    PushManager.prototype.getSubscription = async () =>
      ({
        endpoint: 'https://push.example/e2e',
        options: { applicationServerKey: null },
        toJSON: () => ({ endpoint: 'https://push.example/e2e' }),
        unsubscribe: async () => {
          w.__unsubscribed = true
          return true
        },
      }) as unknown as PushSubscription
  })
  await loginAs(page, player)

  const deletes: string[] = []
  page.on('request', (request) => {
    if (request.method() === 'DELETE' && request.url().includes('/users/me/push-subscription')) {
      deletes.push(request.url())
    }
  })
  let failSave = true
  await page.route('**/users/me', async (route) => {
    if (route.request().method() === 'PATCH' && failSave) {
      await route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Сервер недоступен"}' })
      return
    }
    await route.continue()
  })

  await page.goto('/settings/notifications')
  // The first switch is the pushes' own (team birthdays etc. follow).
  const toggle = page.getByRole('switch').first()
  await expect(toggle).toBeChecked()
  await toggle.click()

  await expect(page.getByText(/Сервер недоступен|Не удалось/)).toBeVisible()
  await expect(toggle).toBeChecked()
  expect(deletes).toEqual([])
  expect(await page.evaluate(() => (window as unknown as { __unsubscribed: boolean }).__unsubscribed)).toBe(false)

  failSave = false
  await toggle.click()
  await expect(toggle).not.toBeChecked()
  expect(deletes).toHaveLength(1)
  expect(await page.evaluate(() => (window as unknown as { __unsubscribed: boolean }).__unsubscribed)).toBe(true)
})
