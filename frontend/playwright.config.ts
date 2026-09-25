import { defineConfig, devices } from '@playwright/test'
import { TZ } from './e2e/tz'

// End-to-end tests against the local dev stack (docker compose up:
// frontend on :5173, backend on :8000). Every test seeds its own users and
// team through the API, so they don't depend on existing data. Phone-sized
// by default -- the team features are used from the rink, on a phone.
export default defineConfig({
  testDir: './e2e',
  outputDir: './e2e/.results',
  timeout: 90_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
    // Whichever zone is mid-day right now -- see e2e/tz.ts.
    timezoneId: TZ,
    locale: 'ru-RU',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'phone',
      use: {
        ...devices['Pixel 7'],
        viewport: { width: 390, height: 844 },
      },
    },
    {
      name: 'small-phone',
      testMatch: /layout\.spec\.ts/,
      use: {
        ...devices['Pixel 7'],
        viewport: { width: 360, height: 640 },
      },
    },
  ],
})
