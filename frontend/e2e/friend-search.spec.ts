import { expect, test } from '@playwright/test'
import { api, createUser, expectNoHorizontalOverflow, loginAs, shot } from './helpers'

// Finding friends (2026-10-08): by first and last name with the player's
// card in a sheet, the invite link opened before logging in, and the
// "Меня можно найти по имени" switch.

function randomSurname(): string {
  const letters = 'абвгдежзиклмнопрстуф'
  let tail = ''
  for (let i = 0; i < 6; i += 1) {
    tail += letters[Math.floor(Math.random() * letters.length)]
  }
  return `Шайбов${tail}`
}

test('a player is found by name, opens as a card and gets a request', async ({ page }) => {
  const me = await createUser('seeker', 11, 'forward')
  const target = await createUser('found', 22, 'defense')
  const surname = randomSurname()
  await api('PATCH', '/users/me', { token: target.token, body: { first_name: 'Иван', last_name: surname } })

  await loginAs(page, me)
  await page.goto('/friends')
  await page.getByRole('button', { name: 'Добавить' }).first().click()
  const search = page.getByPlaceholder('Найти по имени и фамилии')
  await search.fill('Ив')
  await expect(page.getByText('Напиши имя и фамилию — хотя бы по 2 буквы')).toBeVisible()
  await search.fill(`Иван ${surname.slice(0, 9)}`)
  const row = page.getByRole('button', { name: `Открыть карточку: Иван ${surname}` })
  await expect(row).toBeVisible()
  await expectNoHorizontalOverflow(page)
  await shot(page, 'friend-search-results')

  await row.click()
  const sheet = page.getByRole('dialog', { name: `Иван ${surname}` })
  await expect(sheet.getByText('ОБЩИЙ')).toBeVisible()
  await expect(sheet.getByText(/24 лет/)).toHaveCount(0)
  await shot(page, 'friend-search-card')
  await sheet.getByRole('button', { name: 'Добавить в друзья' }).click()
  await expect(sheet.getByText('Заявка отправлена')).toBeVisible()

  const incoming = await api<{ sender_id: string }[]>('GET', '/friends/requests', { token: target.token })
  expect(incoming.map((request) => request.sender_id)).toContain(me.id)
})

test('an invite link opened logged out sends the request after login', async ({ page }) => {
  const inviter = await createUser('inviter', 33, 'forward')
  const guest = await createUser('guest', 44, 'goalie')
  const { friend_code: code } = await api<{ friend_code: string }>('GET', '/auth/me', { token: inviter.token })

  await page.goto(`/f/${code}`)
  await expect(page.getByText('Игрок Тестовый зовёт тебя в друзья')).toBeVisible()
  await expect(page.getByText('ОБЩИЙ')).toBeVisible()
  await expectNoHorizontalOverflow(page)
  await shot(page, 'friend-invite-link')
  await page.getByRole('button', { name: 'У меня есть аккаунт — войти' }).click()
  await expect(page).toHaveURL(/\/login/)

  await loginAs(page, guest)
  await page.goto('/')
  await expect(page.getByRole('status').getByText('Заявка отправлена: Игрок Тестовый')).toBeVisible()
  const incoming = await api<{ sender_id: string }[]>('GET', '/friends/requests', { token: inviter.token })
  expect(incoming.map((request) => request.sender_id)).toContain(guest.id)
})

test('the name-search switch hides and shows the player', async ({ page }) => {
  const me = await createUser('private', 55, 'forward')
  await loginAs(page, me)
  await page.goto('/settings/privacy')
  const toggle = page.getByRole('switch', { name: 'Меня можно найти по имени' })
  await expect(toggle).toHaveAttribute('aria-checked', 'true')
  await shot(page, 'friend-privacy')
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-checked', 'false')
  const after = await api<{ findable_by_name: boolean }>('GET', '/auth/me', { token: me.token })
  expect(after.findable_by_name).toBe(false)

  await page.goto('/friends')
  await page.getByRole('button', { name: 'Добавить' }).first().click()
  await expect(page.getByText('Тебя самого сейчас не найти по имени')).toBeVisible()
})
