import { execFileSync } from 'node:child_process'
import { expect, test } from '@playwright/test'
import { api, createUser, declareWeek, expectNoHorizontalOverflow, localNow, loginAs, shot, type TestUser } from './helpers'

// The Analytics screen for a premium player after a real workout: findings
// (a drop with "Спросить тренера" that opens the chat with the question
// ready), the stat grid and chart, regularity, weekly load and balance.
//
// Premium and one old stat value (so a stat has visibly dropped) are
// written straight into the local docker database -- neither has an API a
// regular player can call.
test.describe.configure({ mode: 'serial' })

let player: TestUser

function sql(statement: string): void {
  execFileSync('docker', ['exec', 'hockey_level_up_postgres', 'psql', '-U', 'hockey', '-d', 'hockey_level_up', '-c', statement])
}

interface Block {
  id: string
  phase: string
  exercise: { id: string; tracks_weight: boolean; exercise_type: string | null }
}

test.beforeAll(async () => {
  const today = localNow().date
  player = await createUser('analytics', 17, 'forward')
  await declareWeek(player, today)
  sql(`UPDATE users SET has_premium = true WHERE id = '${player.id}'`)
  sql(
    `INSERT INTO stat_history (id, user_id, stat_type, value, recorded_at, reason)
     VALUES (gen_random_uuid(), '${player.id}', 'endurance', 90, now() - interval '40 days', 'e2e baseline')`,
  )

  // Today's workout: every main block done, three logged sets each.
  const plan = await api<{ training_session: { id: string; blocks: Block[] } | null }>(
    'GET',
    `/schedule/day-plan?date=${today}`,
    { token: player.token },
  )
  const session = plan.training_session
  expect(session).not.toBeNull()
  for (const block of session!.blocks.filter((candidate) => candidate.phase === 'main')) {
    for (let set = 1; set <= 3; set += 1) {
      const duration = block.exercise.exercise_type === 'duration'
      await api('POST', '/set-completions', {
        token: player.token,
        body: {
          exercise_id: block.exercise.id,
          training_session_id: session!.id,
          set_number: set,
          weight_kg: block.exercise.tracks_weight ? 20 : null,
          reps_completed: duration ? null : 10,
          duration_seconds_completed: duration ? 30 : null,
        },
      })
    }
    await api('POST', `/session-blocks/${block.id}/complete`, { token: player.token })
  }
})

test('analytics shows findings, stats, regularity, load and balance', async ({ page }) => {
  await loginAs(page, player)
  await page.goto('/analytics')

  const findings = page.getByRole('region', { name: 'Главное за период' })
  await expect(findings.getByText('Главное за 30 дней')).toBeVisible()
  await expect(findings.getByText(/^Выносливость просела на/)).toBeVisible()

  // Six stat tiles; the dropped one is picked for the chart.
  const stats = page.getByRole('region', { name: 'Характеристики' })
  await expect(stats.getByRole('button', { pressed: true })).toHaveAccessibleName(/^Выносливость/)
  await expect(stats.locator('button[aria-pressed]')).toHaveCount(6)
  await stats.getByRole('button', { name: /^Сила/ }).click()
  await expect(stats.getByText('Сила · 30 дней')).toBeVisible()

  // Regularity: four weeks, today done.
  const regularity = page.getByRole('region', { name: 'Регулярность' })
  await expect(regularity.getByRole('listitem')).toHaveCount(28)
  await expect(regularity.getByRole('listitem', { name: /: сделано$/ })).toHaveCount(1)

  await expect(page.getByRole('region', { name: 'Нагрузка и самочувствие' }).getByText('эта')).toBeVisible()
  await expect(page.getByRole('region', { name: 'Баланс нагрузки' })).toBeVisible()
  await expectNoHorizontalOverflow(page)
  await shot(page, 'analytics-01-overview')

  // Another period reloads everything for it.
  await page.getByRole('group', { name: 'Период' }).getByRole('button', { name: '7 дней' }).click()
  await expect(findings.getByText('Главное за 7 дней')).toBeVisible()
  await page.getByRole('group', { name: 'Период' }).getByRole('button', { name: '30 дней' }).click()

  // "Спросить тренера" opens the chat with the question ready to send.
  await findings.getByRole('button', { name: 'Спросить тренера' }).click()
  await expect(page).toHaveURL(/\/coach$/)
  await expect(page.getByRole('textbox')).toHaveValue(/выносливость/)
  await shot(page, 'analytics-02-coach-draft')
})
