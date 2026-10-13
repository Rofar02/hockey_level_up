import { expect, test, type Page } from '@playwright/test'
import { addDays, api, createTeamWithPlayer, localIso, localNow, loginAs, shot, type TeamSetup } from './helpers'

// В (2026-10-13): the team training plan "like reels" -- one drill per
// screen, its scheme playing by itself, swipe/arrows to the next, «Иду» at
// the end. Opened from the push link (?reel=1) and the event page.

const SCHEME = {
  tokens: [
    { id: 'p1', kind: 'own', x: 0.3, y: 0.75, number: 17 },
    { id: 'p2', kind: 'own', x: 0.7, y: 0.75, number: 9 },
  ],
  arrows: [
    { id: 'a1', kind: 'skate_puck', from_token: 'p1', start: { x: 0.3, y: 0.75 }, end: { x: 0.35, y: 0.5 }, step: 1 },
    { id: 'a2', kind: 'pass', start: { x: 0.35, y: 0.5 }, end: { x: 0.7, y: 0.45 }, step: 2 },
  ],
}

let setup: TeamSetup
let eventId: string

test.beforeAll(async () => {
  setup = await createTeamWithPlayer()
  const tomorrow = addDays(localNow().date, 1)
  const event = await api<{ id: string }>('POST', `/teams/${setup.teamId}/events`, {
    token: setup.captain.token,
    body: { event_type: 'training', starts_at: localIso(tomorrow, 12) },
  })
  eventId = event.id
  const base = `/teams/${setup.teamId}/events/${eventId}`
  const warmup = await api<{ id: string }>('POST', `${base}/sections`, { token: setup.captain.token, body: { name: 'Разминка' } })
  const main = await api<{ id: string }>('POST', `${base}/sections`, { token: setup.captain.token, body: { name: 'Основная часть' } })
  await api('POST', `${base}/drills`, {
    token: setup.captain.token,
    body: {
      section_id: warmup.id,
      title: 'Передачи в парах',
      duration_minutes: 8,
      diagram: SCHEME,
      keywords: ['Пас в крюк', 'Скорость'],
    },
  })
  await api('POST', `${base}/drills`, {
    token: setup.captain.token,
    body: { section_id: main.id, title: 'Бросок с хода', description: 'Два круга, бросок в касание.', duration_minutes: 12 },
  })
  await api('POST', `${base}/board/publish`, { token: setup.captain.token })
})

const reel = (page: Page) => page.getByRole('heading', { name: 'ПЛАН ТРЕНИРОВКИ' })

test('the push link opens the reel: scheme plays, swipe through, «Иду» at the end', async ({ page }) => {
  await loginAs(page, setup.player)
  await page.goto(`/teams/${setup.teamId}/events/${eventId}?reel=1`)
  await expect(reel(page)).toBeVisible()
  await expect(page.getByText('2 упражнения · 20 мин')).toBeVisible()
  await expect(page.getByText('УПРАЖНЕНИЕ 1 / 2')).toBeVisible()
  await expect(page.getByText('Пас в крюк  /  Скорость')).toBeVisible()
  // Plays by itself: the whole scheme, then frame by frame.
  await expect(page.getByText('ВСЯ СХЕМА')).toBeVisible()
  await expect(page.getByText('ТАКТ 1 / 2')).toBeVisible({ timeout: 5000 })
  await shot(page, 'reel-drill-scheme')
  // A tap pauses.
  await page.getByRole('button', { name: 'Пауза' }).click()
  await expect(page.getByRole('button', { name: 'Воспроизвести схему' })).toBeVisible()

  // Next drill (another section: its name flashes up), no scheme -> a card.
  await page.getByRole('button', { name: 'Следующее упражнение' }).click()
  await expect(page.getByText('УПРАЖНЕНИЕ 2 / 2')).toBeVisible()
  await expect(page.getByText('Два круга, бросок в касание.').first()).toBeVisible()
  await shot(page, 'reel-drill-card')

  // Swipe left -> the end screen.
  const box = (await page.getByText('УПРАЖНЕНИЕ 2 / 2').boundingBox())!
  await page.mouse.move(box.x + box.width - 10, box.y)
  await page.mouse.down()
  await page.mouse.move(box.x + 10, box.y, { steps: 5 })
  await page.mouse.up()
  await expect(page.getByRole('heading', { name: 'УВИДИМСЯ НА ЛЬДУ' })).toBeVisible()
  await expect(page.getByText(/Идут 0 из 2/)).toBeVisible()
  await page.getByRole('button', { name: 'Иду' }).click()
  await expect(page.getByText('Ты отметился: иду')).toBeVisible()
  await expect(page.getByText(/Идут 1 из 2/)).toBeVisible()
  await shot(page, 'reel-end')

  // Segments jump straight to a drill; close drops ?reel from the address.
  await page.getByRole('tab', { name: /Упражнение 1:/ }).click()
  await expect(page.getByText('УПРАЖНЕНИЕ 1 / 2')).toBeVisible()
  await page.getByRole('button', { name: 'Закрыть', exact: true }).click()
  await expect(reel(page)).toBeHidden()
  await expect(page).not.toHaveURL(/reel=1/)
  await page.getByRole('button', { name: 'Смотреть план' }).click()
  await expect(reel(page)).toBeVisible()
})

test.describe('reduced motion', () => {
  test.use({ reducedMotion: 'reduce' })

  test('nothing plays by itself; ▶ starts it', async ({ page }) => {
    await loginAs(page, setup.player)
    await page.goto(`/teams/${setup.teamId}/events/${eventId}?reel=1`)
    await expect(reel(page)).toBeVisible()
    await page.waitForTimeout(3000)
    await expect(page.getByText('ВСЯ СХЕМА')).toBeVisible()
    await page.getByRole('button', { name: 'Воспроизвести схему' }).click()
    await expect(page.getByText('ТАКТ 1 / 2')).toBeVisible({ timeout: 5000 })
  })
})

test('opened once online, the reel shows offline too (needs the production build)', async ({ page, context }) => {
  test.skip(process.env.E2E_PREVIEW !== '1', 'needs a production build (see sw-offline.spec.ts)')
  await loginAs(page, setup.player)
  await page.goto(`/teams/${setup.teamId}/events/${eventId}?reel=1`)
  await expect(reel(page)).toBeVisible()
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null)
  await page.waitForTimeout(1500)
  await context.setOffline(true)
  await page.reload()
  await expect(reel(page)).toBeVisible()
  await expect(page.getByText('УПРАЖНЕНИЕ 1 / 2')).toBeVisible()
  await expect(page.getByText('ТАКТ 1 / 2')).toBeVisible({ timeout: 5000 })
  await context.setOffline(false)
})
