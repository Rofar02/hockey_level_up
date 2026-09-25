import { expect, test } from '@playwright/test'
import {
  api,
  createTeamWithPlayer,
  declareWeek,
  expectBottomNotHiddenByNav,
  expectNoHorizontalOverflow,
  loginAs,
  localIso,
  localNow,
  shot,
  type TeamSetup,
} from './helpers'

// Every screen the team-training work added or changed, on the phone
// sizes it's used at: nothing sticks out sideways, nothing ends up under
// the bottom navigation, the scheme editor fits without scrolling.
test.describe.configure({ mode: 'serial' })

let setup: TeamSetup
let eventId: string

test.beforeAll(async () => {
  const now = localNow()
  test.skip(now.hour >= 21, 'needs an event later today at least 2.5h away -- pin a mid-day zone with E2E_TZ')
  setup = await createTeamWithPlayer()
  await declareWeek(setup.player, now.date)
  const event = await api<{ id: string }>('POST', `/teams/${setup.teamId}/events`, {
    token: setup.captain.token,
    body: { event_type: 'training', starts_at: localIso(now.date, now.hour + 3, now.minute) },
  })
  eventId = event.id
  const base = `/teams/${setup.teamId}/events/${eventId}`
  const token = setup.captain.token
  // A realistic, fairly long board: long names, long descriptions, a scheme.
  for (const [name, drills] of [
    ['Разминка', ['Катание по кругам с ускорениями на синих линиях', 'Разгоны и торможения']],
    ['Броски и завершение атаки после розыгрыша', ['Бросок с кистей от синей', 'Добивание у пятака', 'Бросок в одно касание']],
    ['Игровые', ['Игра 3 на 3 в зоне']],
  ] as const) {
    const section = await api<{ id: string }>('POST', `${base}/sections`, { token, body: { name } })
    for (const title of drills) {
      await api('POST', `${base}/drills`, {
        token,
        body: {
          section_id: section.id,
          title,
          duration_minutes: 10,
          description: 'Пары у синей линии. Первый отдаёт пас, второй бросает с ходу; меняемся после каждой серии.',
        },
      })
    }
  }
  const event2 = await api<{ sections: { drills: { id: string }[] }[] }>('GET', base, { token })
  await api('PUT', `${base}/drills/${event2.sections[1].drills[0].id}/diagram`, {
    token,
    body: {
      diagram: {
        tokens: [
          { id: 'a', kind: 'own', position: 'F', number: 17, x: 0.3, y: 0.7 },
          { id: 'b', kind: 'own', position: 'D', number: 4, x: 0.7, y: 0.8 },
          { id: 'c', kind: 'opponent', x: 0.5, y: 0.3 },
          { id: 'p', kind: 'puck', x: 0.32, y: 0.68 },
        ],
        arrows: [
          { id: 'x', kind: 'skate_puck', from_token: 'a', start: { x: 0.3, y: 0.7 }, end: { x: 0.35, y: 0.35 } },
          { id: 'y', kind: 'pass', start: { x: 0.35, y: 0.35 }, end: { x: 0.7, y: 0.25 } },
          { id: 'z', kind: 'skate', from_token: 'b', start: { x: 0.7, y: 0.8 }, end: { x: 0.72, y: 0.3 } },
        ],
      },
    },
  })
  await api('POST', `${base}/board/publish`, { token })
  await api('PUT', `${base}/attendance/me`, { token: setup.player.token, body: { status: 'going' } })
})

test('coach screens fit the phone', async ({ page }) => {
  await loginAs(page, setup.captain)

  await page.goto(`/teams/${setup.teamId}`)
  await expect(page.getByRole('region', { name: 'Тренировки и игры' })).toBeVisible()
  await expectNoHorizontalOverflow(page)
  await expectBottomNotHiddenByNav(page)

  await page.goto(`/teams/${setup.teamId}/events`)
  await expect(page.getByText(/План готов/)).toBeVisible()
  await expectNoHorizontalOverflow(page)
  await expectBottomNotHiddenByNav(page)
  await shot(page, 'layout-events')

  await page.goto(`/teams/${setup.teamId}/events/${eventId}?tab=board`)
  await expect(page.getByRole('heading', { name: 'План тренировки' })).toBeVisible()
  await expectNoHorizontalOverflow(page)
  await shot(page, 'layout-board-top')
  await expectBottomNotHiddenByNav(page)
  await shot(page, 'layout-board-bottom')

  // Drill sheet: all actions reachable inside the modal.
  await page.getByRole('button', { name: 'Упражнение Бросок с кистей от синей' }).click()
  const sheet = page.getByRole('dialog', { name: 'Упражнение' })
  await expect(sheet.getByText('Схема на площадке')).toBeVisible()
  await sheet.getByRole('button', { name: 'Удалить упражнение' }).scrollIntoViewIfNeeded()
  await expect(sheet.getByRole('button', { name: 'Удалить упражнение' })).toBeInViewport()
  await expectNoHorizontalOverflow(page)
  await shot(page, 'layout-drill-sheet')
  await sheet.getByRole('button', { name: 'Закрыть' }).click()

  // Scheme editor: the whole rink and the toolbar visible without scrolling.
  await page.getByRole('button', { name: 'Изменить схему: Бросок с кистей от синей' }).click()
  const editor = page.getByRole('dialog', { name: /Схема:/ })
  await expect(editor.getByRole('img', { name: 'Схема упражнения на площадке' })).toBeInViewport({ ratio: 1 })
  await expect(editor.getByRole('button', { name: 'Отменить' })).toBeInViewport({ ratio: 1 })
  await expect(editor.getByRole('button', { name: 'Сохранить' })).toBeInViewport({ ratio: 1 })
  await expectNoHorizontalOverflow(page)
  // Tapping a player shows the arrow palette -- every button on screen.
  const box = await editor.getByRole('img', { name: 'Схема упражнения на площадке' }).boundingBox()
  await page.mouse.click(box!.x + box!.width * 0.7, box!.y + box!.height * 0.8)
  for (const name of ['Пас', 'Перепас', 'Бросок', 'Кат с шайбой', 'Кат без шайбы', 'Убрать фишку']) {
    await expect(editor.getByRole('button', { name, exact: true })).toBeInViewport({ ratio: 1 })
  }
  // The player tapped low on the rink stays visible: the palette moves up.
  const paletteBox = await editor.getByRole('button', { name: 'Убрать фишку' }).boundingBox()
  expect(paletteBox!.y + paletteBox!.height, 'palette covers the selected player').toBeLessThan(box!.y + box!.height * 0.8 - 20)
  await shot(page, 'layout-diagram-palette')
  // Shot mode: the instructions sit above the rink, never over a goal.
  await editor.getByRole('button', { name: 'Бросок', exact: true }).click()
  const hintBox = await editor.getByText(/коснись ворот/).boundingBox()
  expect(hintBox!.y + hintBox!.height, 'drawing hint overlaps the rink').toBeLessThanOrEqual(box!.y + 1)
  await shot(page, 'layout-diagram-shot-mode')
  await editor.getByRole('button', { name: 'Отменить стрелку' }).click()
  await shot(page, 'layout-diagram-editor')
})

test('floating tab bar: all tabs on screen, coach in the middle opens the chat', async ({ page }) => {
  await loginAs(page, setup.player)
  await page.goto('/')
  const nav = page.getByRole('navigation', { name: 'Основная навигация' })
  // A player who has never met the coach: the centre button glows.
  const coachLink = nav.locator('a[href="/coach"]')
  await expect(coachLink).toHaveAttribute('data-attention', 'first_visit')
  await expect(coachLink.locator('.coach-glow')).toHaveCount(1)
  const labels = ['Главная', 'Неделя', /ИИ-тренер/, 'Профиль', 'Ещё']
  for (const name of labels) {
    await expect(nav.getByRole('link', { name })).toBeInViewport({ ratio: 1 })
  }
  // Coach is the middle one, in visual order too.
  const xs = await Promise.all(labels.map(async (name) => (await nav.getByRole('link', { name }).boundingBox())!.x))
  expect([...xs].sort((a, b) => a - b)).toEqual(xs)
  await shot(page, 'layout-tabbar')

  await coachLink.click()
  await expect(page).toHaveURL(/\/coach$/)
  // The chat's message box sits at the bottom -- the capsule steps aside.
  await expect(page.getByRole('navigation', { name: 'Основная навигация' })).toHaveCount(0)
  await expect(page.getByPlaceholder('Спросите тренера о тренировках...')).toBeInViewport()
  // The chat says why the button was glowing.
  await expect(page.getByText(/Это ваш ИИ-тренер/)).toBeVisible()
  await shot(page, 'layout-coach-chat')

  // Opening the chat ends the "get acquainted" glow.
  await page.getByRole('button', { name: 'Назад' }).click()
  const navBack = page.getByRole('navigation', { name: 'Основная навигация' })
  await expect(navBack.locator('a[href="/coach"]')).not.toHaveAttribute('data-attention', /.+/)
  await expect(navBack.locator('.coach-glow')).toHaveCount(0)
})

test('player screens fit the phone', async ({ page }) => {
  await loginAs(page, setup.player)
  await page.goto('/')
  await expect(page.getByText('Командная тренировка')).toBeVisible()
  await expectNoHorizontalOverflow(page)
  await shot(page, 'layout-home-card')

  await page.getByRole('button', { name: 'Смотреть план' }).click()
  const modal = page.getByRole('dialog', { name: 'План тренировки' })
  await expect(modal.getByText('Броски и завершение атаки после розыгрыша')).toBeVisible()
  await expectNoHorizontalOverflow(page)
  await shot(page, 'layout-plan-modal')
  await modal.getByRole('button', { name: /Бросок с кистей от синей/ }).click()
  await expect(modal.getByRole('img', { name: 'Схема упражнения на площадке' })).toBeVisible()
  await expectNoHorizontalOverflow(page)
  await shot(page, 'layout-plan-drill')
  await modal.getByRole('button', { name: 'Закрыть' }).click()

  await page.goto(`/teams/${setup.teamId}/events/${eventId}?tab=board`)
  await expect(page.getByRole('button', { name: /Добивание у пятака/ })).toBeVisible()
  await expectNoHorizontalOverflow(page)
  await expectBottomNotHiddenByNav(page)
})
