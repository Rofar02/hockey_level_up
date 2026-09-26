import { expect, test } from '@playwright/test'
import { addDays, api, createTeamWithPlayer, expectNoHorizontalOverflow, localIso, localNow, loginAs, shot, type TeamSetup } from './helpers'

// A coach's own templates: save a drill (with its scheme) as a template,
// drop it onto the board as a copy, rename it, delete it.
test.describe.configure({ mode: 'serial' })

const DIAGRAM = {
  tokens: [{ id: 'p1', kind: 'own', position: 'F', number: 17, x: 0.3, y: 0.75 }],
  arrows: [
    { id: 'a1', kind: 'skate_puck', from_token: 'p1', start: { x: 0.3, y: 0.75 }, via: [{ x: 0.4, y: 0.5 }], end: { x: 0.35, y: 0.37 }, step: 1 },
    { id: 'a2', kind: 'shot', from_token: null, start: { x: 0.35, y: 0.37 }, via: [], end: { x: 0.5, y: 22 / 360 }, step: 2 },
  ],
}

let setup: TeamSetup
let eventId: string
let sectionIds: string[]

test.beforeAll(async () => {
  setup = await createTeamWithPlayer()
  const event = await api<{ id: string }>('POST', `/teams/${setup.teamId}/events`, {
    token: setup.captain.token,
    body: { event_type: 'training', starts_at: localIso(addDays(localNow().date, 2), 12) },
  })
  eventId = event.id
  sectionIds = []
  for (const name of ['Розыгрыш', 'Игровые']) {
    const section = await api<{ id: string }>('POST', `/teams/${setup.teamId}/events/${eventId}/sections`, {
      token: setup.captain.token,
      body: { name },
    })
    sectionIds.push(section.id)
  }
  const drill = await api<{ id: string }>('POST', `/teams/${setup.teamId}/events/${eventId}/drills`, {
    token: setup.captain.token,
    body: { section_id: sectionIds[0], title: '2 в 1 через центр', description: 'Пас в среднюю зону', duration_minutes: 15 },
  })
  await api('PUT', `/teams/${setup.teamId}/events/${eventId}/drills/${drill.id}/diagram`, {
    token: setup.captain.token,
    body: { diagram: DIAGRAM },
  })
})

test('coach saves a drill as a template and reuses it on the board', async ({ page }) => {
  await loginAs(page, setup.captain)
  await page.goto(`/teams/${setup.teamId}/events/${eventId}?tab=board`)

  // No templates yet: a new drill offers none.
  const games = page.getByRole('region', { name: 'Раздел Игровые' })
  await games.getByRole('button', { name: 'Добавить упражнение' }).click()
  const newDrill = page.getByRole('dialog', { name: 'Новое упражнение' })
  await expect(newDrill.getByLabel('Название')).toBeVisible()
  await expect(newDrill.getByRole('button', { name: /Взять из моих шаблонов/ })).toHaveCount(0)
  await newDrill.getByRole('button', { name: 'Закрыть' }).click()

  // Save the drill (scheme included) as a template.
  await page.getByRole('button', { name: 'Упражнение 2 в 1 через центр' }).click()
  const sheet = page.getByRole('dialog', { name: 'Упражнение' })
  await sheet.getByRole('button', { name: 'Сохранить как шаблон' }).click()
  await expect(sheet.getByRole('button', { name: 'Сохранено в мои шаблоны' })).toBeDisabled()
  await shot(page, 'tpl-01-saved')
  await sheet.getByRole('button', { name: 'Закрыть' }).click()

  // Another section: the template goes in as a copy, scheme and all.
  await games.getByRole('button', { name: 'Добавить упражнение' }).click()
  await newDrill.getByRole('button', { name: /Взять из моих шаблонов/ }).click()
  const picker = page.getByRole('dialog', { name: 'Мои шаблоны' })
  await expect(picker.getByRole('button', { name: 'Взять шаблон 2 в 1 через центр' })).toBeVisible()
  await expectNoHorizontalOverflow(page)
  await shot(page, 'tpl-02-picker')
  await picker.getByRole('button', { name: 'Взять шаблон 2 в 1 через центр' }).click()
  await expect(picker).toBeHidden()
  await expect(games.getByRole('button', { name: 'Изменить схему: 2 в 1 через центр' })).toBeVisible()

  const board = await api<{
    sections: { name: string; drills: { title: string; description: string | null; duration_minutes: number | null; diagram: unknown }[] }[]
  }>('GET', `/teams/${setup.teamId}/events/${eventId}`, { token: setup.captain.token })
  const copied = board.sections.find((section) => section.name === 'Игровые')?.drills ?? []
  expect(copied).toHaveLength(1)
  expect(copied[0]).toMatchObject({ title: '2 в 1 через центр', description: 'Пас в среднюю зону', duration_minutes: 15, diagram: DIAGRAM })

  // Rename, then delete it -- the copy on the board stays.
  await games.getByRole('button', { name: 'Добавить упражнение' }).click()
  await newDrill.getByRole('button', { name: /Взять из моих шаблонов/ }).click()
  await picker.getByRole('button', { name: 'Действия с шаблоном 2 в 1 через центр' }).click()
  await picker.getByLabel('Название шаблона').fill('2 в 1')
  await picker.getByRole('button', { name: 'Переименовать' }).click()
  await expect(picker.getByRole('button', { name: 'Взять шаблон 2 в 1', exact: true })).toBeVisible()
  await picker.getByRole('button', { name: 'Действия с шаблоном 2 в 1' }).click()
  await picker.getByRole('button', { name: 'Удалить шаблон' }).click()
  await picker.getByRole('button', { name: 'Удалить шаблон' }).click()
  await expect(picker.getByText(/Шаблонов пока нет/)).toBeVisible()
  await picker.getByRole('button', { name: 'Закрыть' }).click()
  await expect(games.getByRole('button', { name: 'Изменить схему: 2 в 1 через центр' })).toBeVisible()
})
