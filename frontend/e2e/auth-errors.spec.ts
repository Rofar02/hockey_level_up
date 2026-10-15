import { expect, test } from '@playwright/test'
import { createUser } from './helpers'

// 15.10: sign-in and sign-up speak Russian -- the server's answers, the
// field checks (no browser bubbles), the password rule shown up front.

test('a wrong password says so in Russian', async ({ page }) => {
  const me = await createUser('autherr', 51, 'forward')
  await page.goto('/login')
  await page.getByLabel('Email').fill(me.email)
  await page.getByLabel('Пароль').fill('wrong-password')
  await page.getByRole('button', { name: 'Войти' }).click()
  await expect(page.getByText('Неверный email или пароль')).toBeVisible()
})

test('an empty sign-in form names the field instead of a browser bubble', async ({ page }) => {
  await page.goto('/login')
  await page.getByRole('button', { name: 'Войти' }).click()
  await expect(page.getByText('Заполните поле «Email»')).toBeVisible()
})

test('sign-up step 1: the password rule up front, Russian field errors', async ({ page }) => {
  await page.goto('/register')
  await expect(page.getByText('Минимум 8 символов')).toBeVisible()
  await page.getByLabel('Email').fill('not-an-email')
  await page.getByLabel('Пароль').fill('12345678')
  await page.getByRole('button', { name: 'Далее' }).click()
  await expect(page.getByText('Проверьте email: в нём должны быть @ и домен, например name@mail.ru')).toBeVisible()

  await page.getByLabel('Email').fill(`e2e_short_${Date.now()}@example.com`)
  await page.getByLabel('Пароль').fill('short')
  await page.getByRole('button', { name: 'Далее' }).click()
  await expect(page.getByText('Пароль — минимум 8 символов')).toBeVisible()
})
