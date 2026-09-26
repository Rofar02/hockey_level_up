import { expect, test, type Page } from '@playwright/test'
import {
  addDays,
  api,
  createTeamWithPlayer,
  dayPlan,
  declareWeek,
  expectNoHorizontalOverflow,
  loginAs,
  localIso,
  localNow,
  shot,
  type TeamSetup,
} from './helpers'

// The whole team-training loop on a phone, in the order it happens:
// coach finds the event and builds the plan (sections, drills, a scheme),
// publishes it; the player says "going", which takes over their day; the
// home card shows the plan; after the start the card turns into the diary.
test.describe.configure({ mode: 'serial' })

let setup: TeamSetup
let eventId: string
let today: string

test.beforeAll(async () => {
  const now = localNow()
  // "Going" closes 2h before the start and the event must still be today
  // for the home card -- there's no such slot late in the evening.
  test.skip(now.hour >= 21, 'needs an event later today at least 2.5h away -- pin a mid-day zone with E2E_TZ')
  today = now.date
  setup = await createTeamWithPlayer()
  await declareWeek(setup.player, today)
  const startHour = now.hour + 3
  const event = await api<{ id: string }>('POST', `/teams/${setup.teamId}/events`, {
    token: setup.captain.token,
    body: { event_type: 'training', starts_at: localIso(today, startHour, now.minute) },
  })
  eventId = event.id
})

async function rinkBox(page: Page) {
  const box = await page.getByRole('dialog', { name: /Схема:/ }).getByRole('img', { name: 'Схема упражнения на площадке' }).boundingBox()
  if (box === null) {
    throw new Error('rink not rendered')
  }
  return { at: (x: number, y: number) => ({ x: box.x + box.width * x, y: box.y + box.height * y }) }
}

test('coach finds the plan from the team page and builds it', async ({ page }) => {
  await loginAs(page, setup.captain)

  // The captain's home screen nudges about the unfinished plan and leads
  // straight to it.
  await page.goto('/')
  const reminder = page.getByRole('region', { name: 'Завершите план тренировки' })
  await expect(reminder.getByText('План не составлен')).toBeVisible()
  await shot(page, '00-home-coach-reminder')
  await expectNoHorizontalOverflow(page)
  await reminder.getByRole('button', { name: 'Завершить план' }).click()
  await expect(page).toHaveURL(new RegExp(`/events/${eventId}\\?tab=board`))

  // Discoverability: Ещё -> Команда -> team -> "Ближайшее" -> plan.
  await page.goto('/more')
  await page.getByText('Команда', { exact: true }).click()
  await page.getByText(setup.teamName).click()
  const nextCard = page.getByRole('region', { name: 'Тренировки и игры' })
  await expect(nextCard.getByText('План не составлен')).toBeVisible()
  await shot(page, '01-team-page-next-event')
  await expectNoHorizontalOverflow(page)
  await nextCard.getByRole('button', { name: 'Составить план тренировки' }).click()

  await expect(page).toHaveURL(new RegExp(`/events/${eventId}\\?tab=board`))
  await expect(page.getByRole('heading', { name: 'План тренировки' })).toBeVisible()
  await expect(page.getByText('Собери тренировку из разделов')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Опубликовать для команды' })).toBeDisabled()
  await shot(page, '02-board-empty')
  await expectNoHorizontalOverflow(page)

  // Section from a preset, then drills inside it.
  await page.getByRole('button', { name: 'Разминка' }).click()
  const warmup = page.getByRole('region', { name: 'Раздел Разминка' })
  await expect(warmup.getByText('Пока пусто')).toBeVisible()

  await warmup.getByRole('button', { name: 'Добавить упражнение' }).click()
  const sheet = page.getByRole('dialog')
  await sheet.getByLabel('Название').fill('Катание по кругам')
  await sheet.getByLabel('Что делать').fill('Два круга вперёд, два назад, темп средний.')
  await sheet.getByLabel('Минут').fill('8')
  await shot(page, '03-new-drill-sheet')
  await sheet.getByRole('button', { name: 'Добавить', exact: true }).click()
  await expect(warmup.getByRole('button', { name: 'Упражнение Катание по кругам' })).toBeVisible()
  await expect(warmup.getByText('1 упражнение · 8 мин')).toBeVisible()

  // Second section by custom name, second drill straight into the scheme editor.
  await page.getByLabel('Или своё название').fill('Розыгрыш')
  await page.getByRole('button', { name: 'Добавить', exact: true }).click()
  const plays = page.getByRole('region', { name: 'Раздел Розыгрыш' })
  await plays.getByRole('button', { name: 'Добавить упражнение' }).click()
  // Empty title: the button still reacts and says what's missing.
  await page.getByRole('dialog').getByRole('button', { name: 'Добавить и нарисовать схему' }).click()
  await expect(page.getByRole('dialog').getByRole('alert')).toHaveText('Сначала напиши название упражнения')
  await expect(page.getByRole('dialog').getByLabel('Название')).toBeFocused()
  await page.getByRole('dialog').getByLabel('Название').fill('2 в 1 через центр')
  await expect(page.getByRole('dialog').getByRole('alert')).toHaveCount(0)
  await page.getByRole('dialog').getByLabel('Минут').fill('15')
  await page.getByRole('dialog').getByRole('button', { name: 'Добавить и нарисовать схему' }).click()

  // Scheme: our forward with #17, drag him, skate with the puck, then a
  // chained pass from the end of that arrow; an opponent; undo; save.
  const editor = page.getByRole('dialog', { name: 'Схема: 2 в 1 через центр' })
  await expect(editor).toBeVisible()
  // Empty rink: a hint, and "Сохранить" explains instead of closing.
  await expect(editor.getByText('Добавь игрока кнопкой «Свой» внизу')).toBeVisible()
  await editor.getByRole('button', { name: 'Сохранить' }).click()
  await expect(editor.getByText(/Схема пустая/)).toBeVisible()
  await expect(editor).toBeVisible()
  await editor.getByRole('button', { name: 'Свой' }).click()
  await editor.getByPlaceholder('17').fill('17')
  await editor.getByRole('button', { name: 'Поставить на каток' }).click()
  const rink = await rinkBox(page)
  const start = rink.at(0.4, 0.5)
  const dropped = rink.at(0.3, 0.75)
  await page.mouse.move(start.x, start.y)
  await page.mouse.down()
  await page.mouse.move(dropped.x, dropped.y, { steps: 8 })
  await page.mouse.up()
  // Skate with the puck drawn with a finger: an S-curve from the player.
  await editor.getByRole('button', { name: 'Кат с шайбой' }).click()
  await expect(editor.getByText(/веди пальцем по траектории/)).toBeVisible()
  const curve = [
    [0.3, 0.75], [0.36, 0.7], [0.42, 0.64], [0.44, 0.58], [0.4, 0.52],
    [0.33, 0.48], [0.28, 0.44], [0.29, 0.4], [0.35, 0.37],
  ].map(([x, y]) => rink.at(x, y))
  await page.mouse.move(curve[0].x, curve[0].y)
  await page.mouse.down()
  for (const point of curve.slice(1)) {
    await page.mouse.move(point.x, point.y, { steps: 4 })
  }
  await page.mouse.up()
  // Then a straight pass from the end of that curve -- a tap, no drawing.
  await editor.getByRole('button', { name: 'Пас', exact: true }).click()
  const passEnd = rink.at(0.75, 0.28)
  await page.mouse.click(passEnd.x, passEnd.y)
  // A stroke the phone's browser cancels half-way (pointercancel carries
  // 0,0) must not create an arrow flying to the top corner.
  await editor.getByRole('button', { name: 'Кат без шайбы' }).click()
  const cancelFrom = rink.at(0.6, 0.6)
  const cancelTo = rink.at(0.62, 0.5)
  await editor.getByRole('img', { name: 'Схема упражнения на площадке' }).evaluate(
    async (svg, [from, to]) => {
      // A frame between events, like a real finger -- React has to render
      // the started stroke before the next event reaches its handlers.
      const frame = () => new Promise((resolve) => requestAnimationFrame(() => setTimeout(resolve, 30)))
      const fire = async (type: string, x: number, y: number) => {
        svg.dispatchEvent(
          new PointerEvent(type, { bubbles: true, clientX: x, clientY: y, pointerId: 77, pointerType: 'touch', isPrimary: true }),
        )
        await frame()
      }
      await fire('pointerdown', from.x, from.y)
      await fire('pointermove', (from.x + to.x) / 2, (from.y + to.y) / 2)
      await fire('pointermove', to.x, to.y)
      await fire('pointercancel', 0, 0)
    },
    [cancelFrom, cancelTo],
  )
  // Still waiting for a proper stroke; leave drawing mode.
  await expect(editor.getByText(/веди пальцем по траектории/)).toBeVisible()
  await editor.getByRole('button', { name: 'Отменить стрелку' }).click()

  // A shaky, nearly straight stroke (skate without the puck, from the end
  // of the pass) is saved perfectly straight.
  await editor.getByRole('button', { name: 'Кат без шайбы' }).click()
  const shaky = [
    [0.75, 0.28], [0.765, 0.26], [0.77, 0.235], [0.785, 0.21], [0.795, 0.19],
    [0.815, 0.17], [0.82, 0.145], [0.84, 0.13], [0.85, 0.11],
  ].map(([x, y]) => rink.at(x, y))
  await page.mouse.move(shaky[0].x, shaky[0].y)
  await page.mouse.down()
  for (const point of shaky.slice(1)) {
    await page.mouse.move(point.x, point.y, { steps: 3 })
  }
  await page.mouse.up()
  // Перепас from there back towards the middle -- a tap, heads on both ends.
  await editor.getByRole('button', { name: 'Перепас' }).click()
  const repassEnd = rink.at(0.55, 0.2)
  await page.mouse.click(repassEnd.x, repassEnd.y)
  await expect(editor.locator('path[marker-start]')).toHaveCount(1)
  // Бросок from the end of the repass: a tap near the top goal lands
  // exactly in the goal mouth, as a straight double line.
  await editor.getByRole('button', { name: 'Бросок' }).click()
  await expect(editor.getByText(/коснись ворот/)).toBeVisible()
  const nearGoal = rink.at(0.58, 0.12)
  await page.mouse.click(nearGoal.x, nearGoal.y)

  // Кадры: the chain went into frames 1..5 on its own (each arrow
  // continues the last). The shot is selected -- move it to frame 3, the
  // same moment as the skate; the frame strip follows it.
  const frameChips = editor.getByRole('group', { name: 'Кадры' }).getByRole('button', { name: /^Кадр \d+$/ })
  await expect(frameChips).toHaveCount(5)
  await expect(editor.getByTestId('arrow-step')).toHaveText('5')
  await editor.getByRole('button', { name: 'Кадр раньше' }).click()
  await editor.getByRole('button', { name: 'Кадр раньше' }).click()
  await expect(editor.getByTestId('arrow-step')).toHaveText('3')
  await expect(frameChips).toHaveCount(4)
  await expect(editor.getByRole('button', { name: 'Кадр 3', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(editor.locator('g[data-frame-state="current"]')).toHaveCount(2)
  await shot(page, '04a-diagram-frames')

  // A later frame shows the player where frame 1's skate left him, and a
  // new arrow from him starts right there -- then he's at its end in the
  // next frame. Undone, so the saved scheme below stays as drawn.
  const forward = editor.locator('g[data-token="own"] circle[r="10"]')
  // Within a token's radius (rink units) -- a finger stroke's end lands
  // a few units off the exact point.
  const standsAt = async (x: number, y: number) => {
    await expect
      .poll(async () =>
        Math.hypot(Number(await forward.getAttribute('cx')) - x * 200, Number(await forward.getAttribute('cy')) - y * 360),
      )
      .toBeLessThan(10)
  }
  await editor.getByRole('button', { name: 'Кадр 1', exact: true }).click()
  await standsAt(0.3, 0.75)
  await expect(editor.locator('g[data-ghost]')).toHaveCount(0)
  // "Дальше отсюда" on the selected player jumps to the frame after his
  // last move: he stands at its end, a faint copy marks where he started.
  await editor.locator('g[data-token="own"]').click()
  await editor.getByRole('button', { name: 'Дальше отсюда' }).click()
  await expect(editor.getByRole('button', { name: 'Кадр 2', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await standsAt(0.35, 0.37)
  await expect(editor.locator('g[data-ghost="own"]')).toHaveCount(1)
  await expect(editor.getByRole('button', { name: 'Дальше отсюда' })).toHaveCount(0)
  // Tapped, not dragged: he stays where frame 1 left him.
  await editor.locator('g[data-token="own"]').click()
  await standsAt(0.35, 0.37)
  await editor.getByRole('button', { name: 'Кат без шайбы' }).click()
  const onward = rink.at(0.2, 0.3)
  await page.mouse.click(onward.x, onward.y)
  await expect(editor.getByTestId('arrow-step')).toHaveText('2')
  await editor.getByRole('button', { name: 'Кадр 3', exact: true }).click()
  await standsAt(0.2, 0.3)
  await editor.getByRole('button', { name: 'Отменить' }).click()

  await editor.getByRole('button', { name: 'Соперник' }).click()
  await editor.getByRole('button', { name: 'Соперник' }).click()
  await editor.getByRole('button', { name: 'Отменить' }).click()
  await shot(page, '04-diagram-editor')
  await expectNoHorizontalOverflow(page)
  await editor.getByRole('button', { name: 'Сохранить' }).click()
  await expect(editor).toBeHidden()

  await expect(plays.getByRole('button', { name: 'Изменить схему: 2 в 1 через центр' })).toBeVisible()
  const saved = await api<{
    sections: {
      drills: {
        title: string
        diagram: {
          tokens: unknown[]
          arrows: { kind: string; via?: unknown[]; step?: number | null; end: { x: number; y: number } }[]
        } | null
      }[]
    }[]
  }>(
    'GET',
    `/teams/${setup.teamId}/events/${eventId}`,
    { token: setup.captain.token },
  )
  const drawn = saved.sections.flatMap((section) => section.drills).find((drill) => drill.title === '2 в 1 через центр')
  expect(drawn?.diagram?.tokens).toHaveLength(2) // forward + one opponent (the second was undone)
  expect(drawn?.diagram?.arrows.map((arrow) => arrow.kind)).toEqual(['skate_puck', 'pass', 'skate', 'repass', 'shot'])
  const [skatePuck, pass, skateLine, repass, shotArrow] = drawn?.diagram?.arrows ?? []
  expect(shotArrow.via ?? []).toEqual([])
  expect(drawn?.diagram?.arrows.map((arrow) => arrow.step)).toEqual([1, 2, 3, 4, 3])
  expect(shotArrow.end.x).toBeCloseTo(0.5, 5)
  expect(shotArrow.end.y).toBeCloseTo(22 / 360, 5)
  expect(skatePuck.via?.length ?? 0, 'the S-curve keeps its shape').toBeGreaterThanOrEqual(1)
  expect(skatePuck.via?.length ?? 0, 'curve smoothed down to a few points').toBeLessThanOrEqual(6)
  expect(pass.via ?? [], 'a tap stays a straight arrow').toEqual([])
  expect(skateLine.via ?? [], 'a shaky, nearly straight stroke is straightened').toEqual([])
  expect(repass.via ?? []).toEqual([])

  // Section menu: move "Розыгрыш" above "Разминка", then back.
  await plays.getByRole('button', { name: 'Действия с разделом Розыгрыш' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Выше' }).click()
  await expect(page.getByRole('dialog').getByRole('button', { name: 'Выше' })).toBeDisabled()
  await shot(page, '05-section-menu')
  await page.getByRole('dialog').getByRole('button', { name: 'Ниже' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Закрыть' }).click()

  // Editing a drill: open it, change minutes, see the scheme block.
  await warmup.getByRole('button', { name: 'Упражнение Катание по кругам' }).click()
  await page.getByRole('dialog').getByLabel('Минут').fill('10')
  await expect(page.getByRole('dialog').getByText('Нарисовать схему')).toBeVisible()
  await page.getByRole('dialog').getByRole('button', { name: 'Сохранить', exact: true }).click()
  await expect(warmup.getByText('1 упражнение · 10 мин')).toBeVisible()

  // Header totals, publish, preview as a player.
  const header = page.locator('section', { has: page.getByRole('heading', { name: 'План тренировки' }) })
  await expect(header.getByText('25', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Опубликовать для команды' }).click()
  await expect(page.getByText('Опубликован — команда видит план')).toBeVisible()
  // "Как видит игрок" is the player's own plan modal: tapping a drill
  // shows its scheme right away, not somewhere below the fold.
  await page.getByRole('button', { name: 'Как видит игрок' }).click()
  const preview = page.getByRole('dialog', { name: 'План тренировки' })
  await preview.getByRole('button', { name: /2 в 1 через центр/ }).click()
  await expect(preview.getByRole('img', { name: 'Схема упражнения на площадке' })).toBeInViewport()
  await shot(page, '06-board-published-preview')
  await preview.getByRole('button', { name: 'Закрыть' }).click()
  await shot(page, '07-board-editor')
  await expectNoHorizontalOverflow(page)

  // Published: the home-screen nudge is gone.
  await page.goto('/')
  await expect(page.getByText('Командная тренировка').or(page.getByText('Нет плана на сегодня')).first()).toBeVisible()
  await expect(page.getByRole('region', { name: 'Завершите план тренировки' })).toHaveCount(0)

  // The events list now says the plan is ready.
  await page.goto(`/teams/${setup.teamId}/events`)
  await expect(page.getByText(/План готов · 2 раздела · 2 упражнения · 25 мин/)).toBeVisible()
  await shot(page, '08-events-list')
  await expectNoHorizontalOverflow(page)
})

test('player says "going": the day becomes team ice and the home card shows the plan', async ({ page }) => {
  await loginAs(page, setup.player)
  await page.goto(`/teams/${setup.teamId}/events/${eventId}?tab=attendance`)
  await page.getByRole('button', { name: 'Отметиться' }).click()
  await page.getByText('Буду', { exact: true }).click()
  await page.getByRole('button', { name: 'Сохранить' }).click()
  await expect(page.getByRole('button', { name: 'Изменить' })).toBeVisible()

  const day = await dayPlan(setup.player, today)
  expect(day.session_type).toBe('on_ice')
  expect(day.team_event_id).toBe(eventId)

  await page.goto('/')
  await expect(page.getByText('Командная тренировка')).toBeVisible()
  await expect(page.getByText('План · 25 мин · 1 схема')).toBeVisible()
  // Players never get the captain's nudge.
  await expect(page.getByRole('region', { name: 'Завершите план тренировки' })).toHaveCount(0)
  await expect(page.getByText('Первое звено')).toHaveCount(0) // no lineup published in this run
  await shot(page, '09-home-team-card')
  await expectNoHorizontalOverflow(page)

  await page.getByRole('button', { name: 'Смотреть план' }).click()
  const modal = page.getByRole('dialog', { name: 'План тренировки' })
  await expect(modal.getByText('Разминка')).toBeVisible()
  // The scheme is visible right in the list, before opening the drill.
  const schemeRow = modal.getByRole('button', { name: /2 в 1 через центр/ })
  await expect(schemeRow.getByTestId('scheme-thumbnail')).toBeVisible()
  await expect(schemeRow.getByText('схема')).toBeVisible()
  await expect(modal.getByRole('button', { name: /Катание по кругам/ }).getByTestId('scheme-thumbnail')).toHaveCount(0)
  await shot(page, '10a-plan-modal-list')
  await schemeRow.click()
  await expect(modal.getByRole('img', { name: 'Схема упражнения на площадке' })).toBeVisible()
  // Frames: "Всё" at rest; a frame shows only what happens then; ▶ plays
  // them through and comes back to the whole scheme.
  const frames = modal.getByRole('group', { name: 'Кадры' })
  await expect(frames.getByRole('button', { name: 'Всё' })).toHaveAttribute('aria-pressed', 'true')
  const player = modal.locator('g[data-token="own"] circle').first()
  const restX = Number(await player.getAttribute('cx'))
  await frames.getByRole('button', { name: 'Кадр 2', exact: true }).click()
  await expect(modal.locator('g[data-frame-state="current"]')).toHaveCount(1)
  // Frame 2 begins after frame 1's skate: the player stands at its end.
  expect(Number(await player.getAttribute('cx'))).not.toBeCloseTo(restX, 0)
  await shot(page, '10b-plan-drill-frame-2')
  await modal.getByRole('button', { name: 'Проиграть' }).click()
  await expect(modal.getByRole('button', { name: 'Пауза' })).toBeVisible()
  await expect(modal.getByRole('button', { name: 'Проиграть' })).toBeVisible({ timeout: 15_000 })
  await expect(frames.getByRole('button', { name: 'Всё' })).toHaveAttribute('aria-pressed', 'true')
  await shot(page, '10-plan-modal-drill-scheme')
  await expectNoHorizontalOverflow(page)
  await modal.getByRole('button', { name: 'Весь план' }).click()
  await expect(modal.getByRole('button', { name: /Катание по кругам/ })).toBeVisible()
  await modal.getByRole('button', { name: 'Закрыть' }).click()
  // Let the modal finish closing (it restores the page's scroll) before
  // tapping the tab bar -- tapping mid-close occasionally went nowhere.
  await expect(modal).toBeHidden()

  // The week screen shows the team day and the same plan.
  await page.getByRole('link', { name: 'Неделя' }).click()
  await expect(page).toHaveURL(/\/schedule\/new$/)
  await expect(page.getByText('Командная тренировка')).toBeVisible()
  await expect(page.getByText(/План · 25 мин · 1 схема/)).toBeVisible()
  await shot(page, '12-week-team-day')
  await expectNoHorizontalOverflow(page)
  await page.getByRole('button', { name: 'План тренировки' }).click()
  const weekModal = page.getByRole('dialog', { name: /командная тренировка/ })
  await expect(weekModal.getByRole('button', { name: 'Разминка до выхода на лёд' })).toBeVisible()
  await weekModal.getByRole('button', { name: /2 в 1 через центр/ }).click()
  await expect(weekModal.getByRole('img', { name: 'Схема упражнения на площадке' })).toBeInViewport()
  await shot(page, '13-week-team-plan-drill')
  await weekModal.getByRole('button', { name: 'Весь план' }).click()
  await weekModal.getByRole('button', { name: 'Разминка до выхода на лёд' }).click()
  await expect(page.getByRole('dialog', { name: /— Лёд/ })).toBeVisible()
})

test('"not going" gives the day back, "going" takes it again', async () => {
  await api('PUT', `/teams/${setup.teamId}/events/${eventId}/attendance/me`, {
    token: setup.player.token,
    body: { status: 'not_going', reason: 'work' },
  })
  let day = await dayPlan(setup.player, today)
  expect(day.session_type).toBe('off_ice')
  expect(day.team_event_id).toBeNull()

  await api('PUT', `/teams/${setup.teamId}/events/${eventId}/attendance/me`, {
    token: setup.player.token,
    body: { status: 'going' },
  })
  day = await dayPlan(setup.player, today)
  expect(day.session_type).toBe('on_ice')
})

test('after the start the home card leads to the personal diary, which grants the team reward', async ({ page }) => {
  const now = localNow()
  test.skip(now.hour === 0 && now.minute < 20, 'needs a start time earlier today')
  // Start moved to a few minutes ago -- the takeover follows the event.
  const minutesAgo = Math.max(0, now.hour * 60 + now.minute - 10)
  await api('PUT', `/teams/${setup.teamId}/events/${eventId}/schedule`, {
    token: setup.captain.token,
    body: { starts_at: localIso(today, Math.floor(minutesAgo / 60), minutesAgo % 60) },
  })

  await loginAs(page, setup.player)
  await page.goto('/')
  await expect(page.getByText(/Началась в/)).toBeVisible()
  const xpBefore = (await api<{ xp: number }>('GET', '/auth/me', { token: setup.player.token })).xp
  await page.getByRole('button', { name: 'Вести дневник' }).click()
  // The ordinary personal diary -- there is no separate team diary.
  await expect(page).toHaveURL(/\/training\/[^/]+\/diary$/)
  await page.getByRole('textbox').fill('Отработали 2 в 1, бросок шёл хорошо')
  await page.getByRole('button', { name: 'Готово' }).click()
  await expect(page).toHaveURL(/\/$/)
  // The first entry on a team-training day grants the team reward.
  const xpAfter = (await api<{ xp: number }>('GET', '/auth/me', { token: setup.player.token })).xp
  expect(xpAfter - xpBefore).toBe(50)
  await page.goto('/')
  await expect(page.getByText('Выполнено')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Открыть дневник' })).toBeVisible()
  await shot(page, '11-home-diary-done')
})

test('a training day from weeks ago still opens (regression)', async ({ page }) => {
  // Three weeks back: the old page only looked in the current + next week.
  const oldDay = addDays(today, -21)
  await declareWeek(setup.player, oldDay)
  const day = await dayPlan(setup.player, oldDay)
  await loginAs(page, setup.player)
  await page.goto(`/training/${day.id}`)
  await expect(page.getByText('Сухая').first()).toBeVisible()
  await expect(page.getByText('Тренировка не найдена.')).toHaveCount(0)
})
