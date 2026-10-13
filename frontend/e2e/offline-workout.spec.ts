import { expect, test } from '@playwright/test'
import { api, createUser, dayPlan, declareWeek, localNow, loginAs, shot } from './helpers'

// Б2 (2026-10-13): a workout done with no connection at all is sent once
// the phone is back online -- every exercise once, XP credited.
// Needs the production build (service worker) and the backend with
// OFFLINE_QUEUE_ENABLED=true; see sw-offline.spec.ts for how to run.
test.skip(process.env.E2E_PREVIEW !== '1', 'needs a production build (see sw-offline.spec.ts)')

type Block = { id: string; completed_at: string | null; skipped_at: string | null; exercise: { name: string } }
type Day = { training_session: { blocks: Block[] } }

test('a whole workout offline, synced once the connection is back', async ({ page, context }) => {
  const me = await createUser('offworkout', 47, 'forward')
  const today = localNow().date
  await declareWeek(me, today)
  const plan = await dayPlan(me, today)
  const before = await api<{ xp: number }>('GET', '/auth/me', { token: me.token })

  await loginAs(page, me)
  await page.goto('/')
  await expect(page.getByRole('navigation', { name: 'Основная навигация' })).toBeVisible()
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null)
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('icelevel.offlineQueue')), { timeout: 15_000 })
    .toBe('1')
  await page.goto(`/training/${plan.id}`)
  await expect(page.getByRole('button', { name: 'Начать тренировку' })).toBeVisible()

  await context.setOffline(true)
  await page.getByRole('button', { name: 'Начать тренировку' }).click()
  await page.waitForTimeout(500)
  await shot(page, 'offline-workout-started')
  // Tick every exercise on screen, phase after phase.
  let ticked = 0
  const finished = page.getByRole('heading', { name: 'Тренировка завершена' })
  for (let round = 0; round < 60; round += 1) {
    if (await finished.isVisible().catch(() => false)) {
      break
    }
    // The player opens full screen on start and after each exercise --
    // the list underneath has a checkbox per exercise.
    const collapse = page.getByRole('button', { name: 'Свернуть плеер' })
    if (await collapse.isVisible().catch(() => false)) {
      await collapse.click()
      await page.waitForTimeout(200)
    }
    const open = page.locator('[role="checkbox"][aria-checked="false"]:not([disabled])')
    if ((await open.count()) === 0) {
      const next = page.getByRole('button', { name: /^Завершить/ })
      if (await next.isVisible().catch(() => false)) {
        await next.click()
        continue
      }
      break
    }
    await open.first().click({ timeout: 5000 })
    ticked += 1
    await page.waitForTimeout(150)
  }
  expect(ticked).toBeGreaterThan(0)
  await expect(finished).toBeVisible()
  // Nothing reached the server yet: XP and the streak wait for it.
  await expect(page.getByText('Начислится, когда появится связь')).toBeVisible()
  await expect(page.getByRole('status').filter({ hasText: /ждут отправки/ })).toBeVisible()
  await shot(page, 'offline-workout-done')

  // Closed and reopened, still offline: the ticks are still there.
  await page.reload()
  await expect(page.locator('[role="checkbox"][aria-checked="true"]').first()).toBeVisible()

  const server = await api<Day>('GET', `/schedule/day-plans/${plan.id}`, { token: me.token })
  expect(server.training_session.blocks.filter((b) => b.completed_at !== null)).toHaveLength(0)

  await context.setOffline(false)
  await page.evaluate(() => window.dispatchEvent(new Event('online')))
  await expect(page.getByRole('status').filter({ hasText: 'Нет связи' })).toBeHidden({ timeout: 30_000 })
  await expect
    .poll(
      async () => {
        const day = await api<Day>('GET', `/schedule/day-plans/${plan.id}`, { token: me.token })
        return day.training_session.blocks.filter((b) => b.completed_at !== null).length
      },
      { timeout: 30_000 },
    )
    .toBe(ticked)
  await expect
    .poll(async () => (await api<{ xp: number }>('GET', '/auth/me', { token: me.token })).xp, { timeout: 30_000 })
    .toBeGreaterThan(before.xp)
  await expect.poll(() => page.evaluate(() => localStorage.getItem('icelevel.offlineQueue'))).toBe('1')
})
