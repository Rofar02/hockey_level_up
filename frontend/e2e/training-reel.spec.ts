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

const reel = (page: Page) => page.getByRole('dialog', { name: 'План тренировки' })

test('the push link opens the reel: scheme plays, swipe through, «Иду» at the end', async ({ page }) => {
  await loginAs(page, setup.player)
  await page.goto(`/teams/${setup.teamId}/events/${eventId}?reel=1`)
  await expect(reel(page)).toBeVisible()
  await expect(reel(page).getByText('2 упражнения · 20 мин')).toBeVisible()
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
  await expect(page.getByText('Вы отметились: иду')).toBeVisible()
  await expect(page.getByText(/Идут 1 из 2/)).toBeVisible()
  await shot(page, 'reel-end')

  // Segments jump straight to a drill; close drops ?reel from the address.
  await page.getByRole('tab', { name: /Упражнение 1:/ }).click()
  await expect(page.getByText('УПРАЖНЕНИЕ 1 / 2')).toBeVisible()
  await page.getByRole('button', { name: 'Закрыть', exact: true }).click()
  await expect(reel(page)).toBeHidden()
  await expect(page).not.toHaveURL(/reel=1/)
  await page.getByRole('button', { name: 'Смотреть план' }).first().click()
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

// Review 14.10 (17): a real finger -- touch events through CDP, the way a
// phone sends them. A horizontal swipe turns the page; a vertical drag
// doesn't.
test('a finger swipe turns the page, a vertical drag does not', async ({ page }) => {
  await loginAs(page, setup.player)
  await page.goto(`/teams/${setup.teamId}/events/${eventId}?reel=1`)
  await expect(page.getByText('УПРАЖНЕНИЕ 1 / 2')).toBeVisible()
  const zone = (await page.getByTestId('reel-swipe-zone').boundingBox())!
  const cdp = await page.context().newCDPSession(page)
  async function drag(from: { x: number; y: number }, to: { x: number; y: number }) {
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [from] })
    for (let step = 1; step <= 6; step++) {
      const x = from.x + ((to.x - from.x) * step) / 6
      const y = from.y + ((to.y - from.y) * step) / 6
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x, y }] })
    }
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
  }
  const midY = zone.y + zone.height / 2
  await drag({ x: zone.x + zone.width / 2, y: zone.y + 40 }, { x: zone.x + zone.width / 2, y: zone.y + zone.height - 40 })
  await expect(page.getByText('УПРАЖНЕНИЕ 1 / 2')).toBeVisible()
  await drag({ x: zone.x + zone.width - 20, y: midY }, { x: zone.x + 20, y: midY })
  await expect(page.getByText('УПРАЖНЕНИЕ 2 / 2')).toBeVisible()
  await drag({ x: zone.x + 60, y: midY }, { x: zone.x + zone.width - 20, y: midY })
  await expect(page.getByText('УПРАЖНЕНИЕ 1 / 2')).toBeVisible()
})

// Review 14.10 (20): a modal dialog -- focus on «Закрыть», arrows turn the
// page, Escape closes the description first and then the reel, focus comes
// back to what opened it.
test('keyboard: focus, arrows, Escape', async ({ page }) => {
  await loginAs(page, setup.player)
  await page.goto(`/teams/${setup.teamId}/events/${eventId}`)
  const open = page.getByRole('button', { name: 'Смотреть план' }).first()
  await open.click()
  const reel = page.getByRole('dialog', { name: 'План тренировки' })
  await expect(reel.getByRole('button', { name: 'Закрыть', exact: true })).toBeFocused()
  expect(await page.evaluate(() => document.getElementById('root')?.inert)).toBe(true)
  await page.keyboard.press('ArrowRight')
  await expect(reel.getByText('УПРАЖНЕНИЕ 2 / 2')).toBeVisible()
  await page.keyboard.press('ArrowLeft')
  await expect(reel.getByText('УПРАЖНЕНИЕ 1 / 2')).toBeVisible()

  await page.keyboard.press('Escape')
  await expect(reel).toBeHidden()
  expect(await page.evaluate(() => document.getElementById('root')?.inert)).toBe(false)
  await expect(open).toBeFocused()
})

// Review 14.10 (22): opened inside the app, the reel is a step in the
// history -- Android's «Назад» closes it and stays on the page.
test('«Назад» closes a reel opened in the app', async ({ page }) => {
  await loginAs(page, setup.player)
  await page.goto(`/teams/${setup.teamId}/events/${eventId}`)
  await page.getByRole('button', { name: 'Смотреть план' }).first().click()
  await expect(reel(page)).toBeVisible()
  await expect(page).toHaveURL(/reel=1/)
  await page.goBack()
  await expect(reel(page)).toBeHidden()
  await expect(page).toHaveURL(new RegExp(`/events/${eventId}$`))
})

// Review 14.10 (23): the push opened with nobody signed in -- after the
// login the player lands on the plan, not the home screen.
test('a push link opened signed out leads back to the plan after the login', async ({ page }) => {
  await page.goto(`/teams/${setup.teamId}/events/${eventId}?reel=1`)
  await expect(page).toHaveURL(/\/login/)
  await page.getByLabel('Email').fill(setup.player.email)
  await page.getByLabel('Пароль').fill('E2ePass123!')
  await page.getByRole('button', { name: 'Войти' }).click()
  await expect(page).toHaveURL(new RegExp(`/events/${eventId}\\?reel=1`))
  await expect(reel(page)).toBeVisible()
})

// The captain watches a draft as the players will («Как видит игрок»).
test('the captain previews an unpublished plan as the reel', async ({ page }) => {
  const draft = await api<{ id: string }>('POST', `/teams/${setup.teamId}/events`, {
    token: setup.captain.token,
    body: { event_type: 'training', starts_at: localIso(addDays(localNow().date, 2), 12) },
  })
  const base = `/teams/${setup.teamId}/events/${draft.id}`
  const section = await api<{ id: string }>('POST', `${base}/sections`, { token: setup.captain.token, body: { name: 'Разминка' } })
  await api('POST', `${base}/drills`, {
    token: setup.captain.token,
    body: { section_id: section.id, title: 'Черновое упражнение', diagram: SCHEME },
  })
  await loginAs(page, setup.captain)
  await page.goto(`${base}?tab=board`)
  await page.getByRole('button', { name: 'Как видит игрок' }).click()
  await expect(page.getByRole('dialog', { name: 'План тренировки' }).getByText('ЧЕРНОВОЕ УПРАЖНЕНИЕ', { exact: false }).or(page.getByText('Черновое упражнение')).first()).toBeVisible()
})

// Review 14.10 (21): offline with no roster saved -- «Иду» is there, greyed,
// with the reason, instead of missing.
test('offline end screen: «Иду» waits for the connection (needs the production build)', async ({ page, context }) => {
  test.skip(process.env.E2E_PREVIEW !== '1', 'needs a production build (see sw-offline.spec.ts)')
  // The captain: the player already said «Иду» in the first test.
  await loginAs(page, setup.captain)
  await page.goto(`/teams/${setup.teamId}/events/${eventId}?reel=1`)
  await expect(reel(page)).toBeVisible()
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null)
  await page.waitForTimeout(1500)
  await context.setOffline(true)
  await page.reload()
  await page.getByRole('tab', { name: /Упражнение 2:/ }).click()
  await page.getByRole('button', { name: 'Следующее упражнение' }).click()
  await expect(page.getByRole('heading', { name: 'УВИДИМСЯ НА ЛЬДУ' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Иду' })).toBeDisabled()
  await expect(page.getByText('Нужна связь')).toBeVisible()
  await context.setOffline(false)
})

// 15.10: a drill with a scheme shows the coach's description too -- the
// title (with its «i») opens it; a 4th keyword in the editor says it's cut.
test('scheme drill: the title opens the description; a 4th keyword is flagged', async ({ page }) => {
  const draft = await api<{ id: string }>('POST', `/teams/${setup.teamId}/events`, {
    token: setup.captain.token,
    body: { event_type: 'training', starts_at: localIso(addDays(localNow().date, 3), 12) },
  })
  const base = `/teams/${setup.teamId}/events/${draft.id}`
  const section = await api<{ id: string }>('POST', `${base}/sections`, { token: setup.captain.token, body: { name: 'Разминка' } })
  await api('POST', `${base}/drills`, {
    token: setup.captain.token,
    body: { section_id: section.id, title: 'Выход из зоны', description: 'Защитник отдаёт в борт, центр открывается.', diagram: SCHEME },
  })
  await loginAs(page, setup.captain)
  await page.goto(`${base}?tab=board`)
  await page.getByRole('button', { name: 'Как видит игрок' }).click()
  await page.getByRole('button', { name: 'Выход из зоны — описание' }).click()
  const sheet = page.getByRole('button', { name: 'Закрыть описание' }).locator('xpath=ancestor::*[@aria-label="Выход из зоны"][1]')
  await expect(sheet.getByText('Защитник отдаёт в борт, центр открывается.')).toBeVisible()
  await page.keyboard.press('Escape')
  await page.keyboard.press('Escape')

  await page.goto(`${base}?tab=board`)
  await page.getByRole('region', { name: 'Раздел Разминка' }).getByRole('button', { name: 'Упражнение Выход из зоны' }).click()
  const field = page.getByRole('dialog').getByLabel('Ключевые слова (через запятую)')
  await field.fill('Пас, Скорость, Голова')
  await expect(page.getByText('До 3, коротко — игроки увидят их под названием в плане.')).toBeVisible()
  await field.fill('Пас, Скорость, Голова, Борт')
  await expect(page.getByText('Больше 3 не поместится — лишнее отрежется. Игроки увидят: Пас / Скорость / Голова')).toBeVisible()
})
