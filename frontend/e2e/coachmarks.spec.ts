import { expect, test, type Page } from '@playwright/test'
import { api, createUser, loginAs } from './helpers'

// 15.10 blocker: a new player's first hint has to be on screen and has to
// close -- never an invisible card behind a backdrop that eats every tap.

async function expectHintOnScreen(page: Page) {
  const overlay = page.locator('[data-coachmark-overlay]')
  await expect(overlay).toBeVisible()
  const card = overlay.getByRole('dialog', { name: 'Подсказка' })
  await expect(card).toBeVisible()
  const box = await card.boundingBox()
  const viewport = page.viewportSize()
  expect(box).not.toBeNull()
  expect(viewport).not.toBeNull()
  if (box === null || viewport === null) {
    return
  }
  expect(box.height).toBeGreaterThan(60)
  expect(box.y).toBeGreaterThanOrEqual(0)
  expect(box.y + box.height).toBeLessThanOrEqual(viewport.height)
  await expect(card.getByRole('button', { name: /Далее|Понятно/ })).toBeInViewport()
}

test('new player: no hint over the planner, the home hint shows and closes', async ({ page }) => {
  const player = await createUser('player', 9, 'forward', { hintsSeen: false })
  await loginAs(page, player)

  await page.goto('/schedule/new')
  const generate = page.getByRole('button', { name: 'Сгенерировать план' })
  await expect(generate).toBeVisible()
  // Planning the week: nothing on top of it.
  await page.waitForTimeout(1200)
  await expect(page.locator('[data-coachmark-overlay]')).toHaveCount(0)
  await generate.click()
  await expect(generate).toHaveCount(0, { timeout: 30_000 })

  await page.goto('/')
  await expectHintOnScreen(page)

  // The nav stays usable while a page's hint is up (the nav's own hint
  // comes last, see below).
  await expect(page.getByRole('dialog', { name: 'Подсказка' })).not.toContainText('Команда, друзья')
  const nav = page.locator('[data-app-bottom-nav]')
  const navLink = nav.getByRole('link').first()
  const linkBox = await navLink.boundingBox()
  expect(linkBox).not.toBeNull()
  if (linkBox !== null) {
    const hit = await page.evaluate(
      ([x, y]) => document.elementFromPoint(x, y)?.closest('[data-app-bottom-nav]') !== null,
      [linkBox.x + linkBox.width / 2, linkBox.y + linkBox.height / 2],
    )
    expect(hit).toBe(true)
  }

  // A tap on the dimmed page closes the hint (top-left corner: never the card).
  const before = await page.getByRole('dialog', { name: 'Подсказка' }).textContent()
  await page.mouse.click(5, 5)
  await expect
    .poll(async () => {
      const overlays = await page.locator('[data-coachmark-overlay]').count()
      if (overlays === 0) {
        return 'closed'
      }
      return (await page.getByRole('dialog', { name: 'Подсказка' }).textContent()) === before ? 'same' : 'next'
    })
    .not.toBe('same')

  // The button closes whatever is left.
  for (let i = 0; i < 5 && (await page.locator('[data-coachmark-overlay]').count()) > 0; i += 1) {
    await expectHintOnScreen(page)
    await page.getByRole('dialog', { name: 'Подсказка' }).getByRole('button', { name: /Далее|Понятно/ }).click()
    await page.waitForTimeout(400)
  }
  await expect(page.locator('[data-coachmark-overlay]')).toHaveCount(0)

  // Seen stays seen.
  await page.reload()
  await page.waitForTimeout(1500)
  await expect(page.locator('[data-coachmark-overlay]')).toHaveCount(0)
})

test('a hint follows its target when the page above it grows', async ({ page }) => {
  const player = await createUser('player', 10, 'forward', { hintsSeen: false })
  // Only the in-page hints: the nav tab's target never moves.
  await api('POST', '/users/me/coachmarks-seen/nav-team-tab', { token: player.token })
  await loginAs(page, player)
  await page.goto('/schedule/new')
  await page.getByRole('button', { name: 'Сгенерировать план' }).click()
  await expect(page.getByRole('button', { name: 'Сгенерировать план' })).toHaveCount(0, { timeout: 30_000 })
  await page.goto('/schedule/new')
  await expectHintOnScreen(page)
  // Content arriving above the target long after the hint opened (a card
  // that loads late) -- the target slides off screen.
  await page.evaluate(() => {
    const filler = document.createElement('div')
    filler.style.height = '1600px'
    document.getElementById('root')?.prepend(filler)
  })
  await page.waitForTimeout(1500)
  await expectHintOnScreen(page)
  // Scrolled back to the target: the spotlight is on screen, not left
  // behind where the target used to be.
  const spot = await page.locator('[data-coachmark-overlay] > div[aria-hidden="true"]').boundingBox()
  const viewport = page.viewportSize()
  expect(spot).not.toBeNull()
  if (spot !== null && viewport !== null) {
    expect(spot.height).toBeLessThan(viewport.height)
    expect(spot.y).toBeGreaterThanOrEqual(0)
    expect(spot.y + spot.height).toBeLessThanOrEqual(viewport.height)
  }
})

const TEAM_HINT = 'Команда, друзья, совместные тренировки и рейтинги'

// 15.10: the «Команда» hint is on the tab itself, only on the home screen.
test('the team-tab hint points at the tab and stays on the home screen', async ({ page }) => {
  const player = await createUser('player', 11, 'forward', { hintsSeen: false })
  for (const hintId of ['home-skill-milestones', 'schedule-week-day-tap', 'profile-stat-unlocks']) {
    await api('POST', `/users/me/coachmarks-seen/${hintId}`, { token: player.token })
  }
  await loginAs(page, player)
  await page.goto('/profile')
  await page.waitForTimeout(1200)
  await expect(page.locator('[data-coachmark-overlay]')).toHaveCount(0)

  await page.goto('/')
  const card = page.getByRole('dialog', { name: 'Подсказка' })
  await expect(card).toContainText(TEAM_HINT)
  const tab = page.locator('[data-app-bottom-nav]').getByRole('link', { name: /Команда/ })
  const spot = page.locator('[data-coachmark-overlay] > div[aria-hidden="true"]')
  await expect
    .poll(async () => {
      const [tabBox, spotBox, cardBox] = await Promise.all([tab.boundingBox(), spot.boundingBox(), card.boundingBox()])
      if (tabBox === null || spotBox === null || cardBox === null) {
        return false
      }
      const around =
        spotBox.x <= tabBox.x && spotBox.y <= tabBox.y &&
        spotBox.x + spotBox.width >= tabBox.x + tabBox.width && spotBox.y + spotBox.height >= tabBox.y + tabBox.height
      return around && cardBox.y + cardBox.height <= tabBox.y
    })
    .toBe(true)
  await card.getByRole('button', { name: /Далее|Понятно/ }).click()
  await expect(page.locator('[data-coachmark-overlay]')).toHaveCount(0)
})

// 15.10: «Пропустить» on the welcome screen turns off the whole first-day tour.
test('skipping the welcome screen skips the first-day hints', async ({ page }) => {
  const player = await createUser('player', 12, 'forward', { hintsSeen: false, tourSeen: false })
  await loginAs(page, player)
  await page.goto('/')
  await page.getByRole('button', { name: 'Пропустить' }).click()
  await page.waitForTimeout(1500)
  await expect(page.locator('[data-coachmark-overlay]')).toHaveCount(0)
  for (const path of ['/profile', '/schedule/new', '/']) {
    await page.goto(path)
    await page.waitForTimeout(1200)
    await expect(page.locator('[data-coachmark-overlay]')).toHaveCount(0)
  }
})
