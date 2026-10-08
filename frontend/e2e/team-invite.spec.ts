import { expect, test } from '@playwright/test'
import { api, createUser, expectNoHorizontalOverflow, loginAs, shot } from './helpers'

// Bringing players into a team (2026-10-08): the team's invite link opened
// before logging in, and the captain inviting a player by name, who joins
// from the team hub.

function randomSurname(): string {
  const letters = 'абвгдежзиклмнопрстуф'
  let tail = ''
  for (let i = 0; i < 6; i += 1) {
    tail += letters[Math.floor(Math.random() * letters.length)]
  }
  return `Клюшкин${tail}`
}

test('a team link opened logged out turns into a join request after login', async ({ page }) => {
  const captain = await createUser('captain', 1, 'defense')
  const guest = await createUser('guest', 8, 'forward')
  const teamName = `E2E Барсы ${Math.random().toString(36).slice(2, 6)}`
  const team = await api<{ id: string; invite_code: string }>('POST', '/teams', {
    token: captain.token,
    body: { name: teamName },
  })

  await page.goto(`/t/${team.invite_code}`)
  await expect(page.getByRole('heading', { name: teamName })).toBeVisible()
  await expect(page.getByText('Капитан Тренер Тестовый · 1 участн.')).toBeVisible()
  await expectNoHorizontalOverflow(page)
  await shot(page, 'team-invite-link')
  await page.getByRole('button', { name: 'У меня есть аккаунт — войти' }).click()

  await loginAs(page, guest)
  await page.goto('/')
  await expect(page.getByRole('status').getByText(`Заявка в «${teamName}» отправлена`)).toBeVisible()
  const requests = await api<{ user_id: string }[]>('GET', `/teams/${team.id}/join-requests`, { token: captain.token })
  expect(requests.map((request) => request.user_id)).toContain(guest.id)
})

test('the captain invites a player by name and the player joins from the hub', async ({ page, browser }) => {
  // Two fresh players and two browsers -- longer than the 90s default.
  test.setTimeout(180_000)
  const captain = await createUser('captain', 1, 'defense')
  const player = await createUser('player', 27, 'forward')
  const surname = randomSurname()
  await api('PATCH', '/users/me', { token: player.token, body: { first_name: 'Егор', last_name: surname } })
  const teamName = `E2E Волки ${Math.random().toString(36).slice(2, 6)}`
  const team = await api<{ id: string }>('POST', '/teams', { token: captain.token, body: { name: teamName } })

  await loginAs(page, captain)
  await page.goto(`/teams/${team.id}`)
  await expect(page.getByRole('heading', { name: 'Позвать в команду' })).toBeVisible()
  await page.getByRole('button', { name: 'Пригласить в команду' }).click()
  const sheet = page.getByRole('dialog', { name: `Пригласить в «${teamName}»` })
  await sheet.getByPlaceholder('Имя или фамилия игрока').fill(`Егор ${surname}`)
  await expect(sheet.getByText(`Егор ${surname}`)).toBeVisible()
  await shot(page, 'team-invite-sheet')
  // Exact hit's own row -- similar spellings from earlier runs show too.
  await sheet.locator('div.flex.items-center.gap-3', { hasText: `Егор ${surname}` }).getByRole('button', { name: 'В команду' }).click()
  await expect(sheet.getByText('Приглашён в команду')).toBeVisible()

  // The player in a browser of their own -- a second login in the same tab
  // keeps the captain's session.
  const { baseURL, timezoneId, viewport } = test.info().project.use
  const playerContext = await browser.newContext({ baseURL, timezoneId, viewport })
  const playerPage = await playerContext.newPage()
  await loginAs(playerPage, player)
  await playerPage.goto('/team')
  await expect(playerPage.getByText(`Тренер Тестовый зовёт тебя в «${teamName}»`)).toBeVisible()
  await shot(playerPage, 'team-invite-card')
  await playerPage.getByRole('button', { name: 'Вступить' }).click()
  await expect(playerPage).toHaveURL(new RegExp(`/teams/${team.id}`))
  await playerContext.close()
  const mine = await api<{ id: string }[]>('GET', '/teams/me', { token: player.token })
  expect(mine.map((item) => item.id)).toContain(team.id)
})
