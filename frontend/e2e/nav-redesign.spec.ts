import { statSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { expect, test } from '@playwright/test'
import { api, createUser, expectNoHorizontalOverflow, loginAs, shot } from './helpers'

// The 5-tab layout: "Ещё" is gone, its items live under Команда and Профиль;
// the Команда tab says when something waits for an answer; a friend sees the
// same player card the owner does; equipment has one screen.

async function befriend(a: { token: string }, b: { token: string }) {
  const me = await api<{ friend_code: string }>('GET', '/auth/me', { token: b.token })
  const sent = await api<{ id: string }>('POST', '/friends/requests', { token: a.token, body: { code: me.friend_code } })
  return sent.id
}

test('the Команда tab shows what is waiting and leads straight to it', async ({ page }) => {
  const me = await createUser('hub', 11, 'forward')
  const stranger = await createUser('stranger', 12, 'defense')
  await befriend(stranger, me)

  await loginAs(page, me)
  await page.goto('/')
  const nav = page.getByRole('navigation', { name: 'Основная навигация' })
  const teamTab = nav.getByRole('link', { name: 'Команда: есть новое' })
  await expect(teamTab).toBeVisible()
  await teamTab.click()
  await expect(page).toHaveURL(/\/team$/)
  await expect(page.getByText('Заявки в друзья: 1')).toBeVisible()
  // No team yet: the hub offers to join one.
  await expect(page.getByRole('link', { name: 'Вступить по коду' })).toBeVisible()
  await shot(page, 'nav-team-hub-waiting')
  await expectNoHorizontalOverflow(page)

  await page.getByText('Заявки в друзья: 1').click()
  await expect(page).toHaveURL(/\/friends$/)
})

test('a friend sees the same player card, read-only', async ({ page }) => {
  const me = await createUser('viewer', 21, 'forward')
  const friend = await createUser('carded', 22, 'goalie')
  const requestId = await befriend(friend, me)
  await api('POST', `/friends/requests/${requestId}/accept`, { token: me.token })

  await loginAs(page, me)
  await page.goto(`/profile/${friend.id}`)
  await expect(page.getByText('ОБЩИЙ')).toBeVisible()
  await expect(page.getByText('ВРТ')).toBeVisible()
  await expect(page.getByText('Тестовый', { exact: true }).last()).toBeVisible()
  // Read-only: no way to change someone else's photo.
  await expect(page.getByRole('button', { name: 'Изменить фото профиля' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /фото профиля/ })).toHaveCount(0)
  await shot(page, 'nav-friend-card')
  await expectNoHorizontalOverflow(page)
})

test('equipment has one screen, reached from the profile', async ({ page }) => {
  const me = await createUser('gear', 31, 'forward')
  await loginAs(page, me)

  await page.goto('/settings/equipment')
  await expect(page).toHaveURL(/\/inventory$/)

  await page.goto('/profile')
  await page.getByRole('link', { name: /Инвентарь/ }).click()
  await expect(page).toHaveURL(/\/inventory$/)
  const gym = page.getByRole('switch')
  await expect(gym).toHaveAttribute('aria-checked', 'false')
  await expect(page.getByRole('heading', { name: 'Дома' })).toBeVisible()
  await gym.click()
  await expect(gym).toHaveAttribute('aria-checked', 'true')
  await expect(page.getByText(/Всё оборудование зала уже учтено/)).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Дома' })).toHaveCount(0)
  await shot(page, 'nav-inventory')
  await expectNoHorizontalOverflow(page)

  await page.goto('/settings')
  await expect(page.getByText('Оборудование', { exact: true })).toHaveCount(0)
})

test('old "Ещё" address and the profile tiles land on real screens', async ({ page }) => {
  const me = await createUser('tiles', 41, 'defense')
  await loginAs(page, me)

  await page.goto('/more')
  await expect(page).toHaveURL(/\/profile$/)

  await page.getByRole('link', { name: /Навыки/ }).click()
  await expect(page).toHaveURL(/\/skills$/)
  await expect(page.getByRole('heading', { name: 'Навыки' })).toBeVisible()

  await page.goto('/profile')
  await page.getByRole('link', { name: /Нагрузка/ }).click()
  await expect(page).toHaveURL(/\/muscle-load$/)
  await expect(page.getByRole('heading', { name: 'Нагрузка' })).toBeVisible()
  // The Профиль tab stays lit on screens reached from it.
  await expect(
    page.getByRole('navigation', { name: 'Основная навигация' }).getByRole('link', { name: 'Профиль' }),
  ).toHaveAttribute('aria-current', 'page')
})

test('a new photo goes through framing before it lands on the card', async ({ page }) => {
  const me = await createUser('photo', 51, 'forward')
  await loginAs(page, me)
  await page.goto('/profile')

  await page.locator('input[type=file]').setInputFiles(fileURLToPath(new URL('./fixtures/tall-photo.jpg', import.meta.url)))
  const dialog = page.getByRole('dialog', { name: 'Кадр для карточки' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('slider', { name: 'Приближение' })).toBeVisible()
  await shot(page, 'nav-avatar-framing')
  await dialog.getByRole('button', { name: 'Готово' }).click()

  await expect(dialog).toHaveCount(0)
  await expect(page.getByRole('img', { name: 'Аватар' })).toHaveAttribute('src', /\/static\/avatars\//)
})

test('the player card can be shared as a picture', async ({ page }) => {
  const me = await createUser('share', 61, 'forward')
  await loginAs(page, me)
  await page.goto('/profile')
  await expect(page.getByText('ОБЩИЙ')).toBeVisible()

  await page.getByRole('button', { name: 'Поделиться карточкой' }).click()
  const dialog = page.getByRole('dialog', { name: 'Карточка игрока' })
  await expect(dialog.getByRole('img', { name: 'Карточка игрока' })).toBeVisible()
  // No file share sheet in a headless browser, so only the download is offered.
  const download = page.waitForEvent('download')
  await dialog.getByRole('button', { name: 'Скачать' }).click()
  const saved = await download
  expect(saved.suggestedFilename()).toBe('icelevel-card.png')
  // A real rendered card, not an empty canvas.
  expect(statSync(await saved.path()).size).toBeGreaterThan(50_000)
})
