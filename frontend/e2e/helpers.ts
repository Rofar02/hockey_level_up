import { expect, type Page } from '@playwright/test'

// API seeding for e2e tests -- talks to the backend directly, the browser
// only ever does what a real user would.
export const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000'
import { TZ } from './tz'

export { TZ }
const PASSWORD = 'E2ePass123!'

export interface TestUser {
  id: string
  email: string
  token: string
  refreshToken: string
}

export async function api<T = unknown>(
  method: string,
  path: string,
  options: { token?: string; body?: unknown; form?: Record<string, string> } = {},
): Promise<T> {
  const headers: Record<string, string> = {}
  let body: string | undefined
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }
  if (options.form !== undefined) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    body = new URLSearchParams(options.form).toString()
  }
  if (options.token !== undefined) {
    headers.Authorization = `Bearer ${options.token}`
  }
  const response = await fetch(`${API_URL}${path}`, { method, headers, body })
  const text = await response.text()
  if (!response.ok) {
    throw new Error(`${method} ${path} -> ${response.status}: ${text}`)
  }
  return (text === '' ? undefined : JSON.parse(text)) as T
}

const HINT_IDS = ['home-skill-milestones', 'schedule-week-day-tap', 'profile-stat-unlocks']

export async function createUser(role: string, jersey: number, position: 'forward' | 'defense' | 'goalie'): Promise<TestUser> {
  const email = `e2e_${role}_${Date.now()}_${Math.random().toString(36).slice(2, 6)}@example.com`
  await api('POST', '/auth/register', {
    body: {
      email,
      password: PASSWORD,
      first_name: role === 'captain' ? 'Тренер' : 'Игрок',
      last_name: 'Тестовый',
      jersey_number: jersey,
      position,
      age: 24,
      privacy_consent: true,
    },
  })
  const tokens = await api<{ access_token: string; refresh_token: string }>('POST', '/auth/login', {
    form: { username: email, password: PASSWORD },
  })
  const token = tokens.access_token
  await api('PATCH', '/users/me', { token, body: { timezone: TZ } })
  await api('POST', '/assessment/start-from-scratch', { token })
  await api('POST', '/users/me/onboarding-tour-seen', { token })
  await api('POST', '/users/me/coach-personality-intro-seen', { token })
  for (const hintId of HINT_IDS) {
    await api('POST', `/users/me/coachmarks-seen/${hintId}`, { token })
  }
  const me = await api<{ id: string }>('GET', '/auth/me', { token })
  return { id: me.id, email, token, refreshToken: tokens.refresh_token }
}

export interface TeamSetup {
  captain: TestUser
  player: TestUser
  teamId: string
  teamName: string
}

export async function createTeamWithPlayer(): Promise<TeamSetup> {
  const captain = await createUser('captain', 1, 'defense')
  const player = await createUser('player', 17, 'forward')
  const teamName = `E2E Акулы ${Math.random().toString(36).slice(2, 6)}`
  const team = await api<{ id: string; invite_code: string }>('POST', '/teams', {
    token: captain.token,
    body: { name: teamName },
  })
  const request = await api<{ id: string }>('POST', '/teams/join', {
    token: player.token,
    body: { code: team.invite_code },
  })
  await api('POST', `/teams/join-requests/${request.id}/approve`, { token: captain.token })
  return { captain, player, teamId: team.id, teamName }
}

// Wall-clock date in the test timezone (see tz.ts) as YYYY-MM-DD, plus
// hour/minute -- tests pick event times relative to this so "today" means
// the same thing to the backend (user timezone) and the browser
// (timezoneId in the config).
export function localNow(): { date: string; hour: number; minute: number } {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date())
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? ''
  return { date: `${get('year')}-${get('month')}-${get('day')}`, hour: Number(get('hour')), minute: Number(get('minute')) }
}

export function addDays(isoDate: string, days: number): string {
  const date = new Date(`${isoDate}T12:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

export function mondayOf(isoDate: string): string {
  const weekday = (new Date(`${isoDate}T12:00:00Z`).getUTCDay() + 6) % 7
  return addDays(isoDate, -weekday)
}

// UTC offset of the test timezone right now, e.g. "+03:00" or "-04:00".
function tzOffset(): string {
  const name = new Intl.DateTimeFormat('en-US', { timeZone: TZ, timeZoneName: 'longOffset' })
    .formatToParts(new Date())
    .find((part) => part.type === 'timeZoneName')?.value
  const match = name?.match(/GMT([+-]\d{2}:\d{2})/)
  return match ? match[1] : '+00:00'
}

// A wall-clock time in the test timezone as an ISO timestamp.
export function localIso(isoDate: string, hour: number, minute = 0): string {
  return `${isoDate}T${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}:00${tzOffset()}`
}

// A week where `trainingDay` is OFF_ICE and every other day is REST.
export async function declareWeek(user: TestUser, trainingDay: string): Promise<void> {
  const monday = mondayOf(trainingDay)
  const days = Array.from({ length: 7 }, (_, offset) => {
    const date = addDays(monday, offset)
    return { date, session_type: date === trainingDay ? 'off_ice' : 'rest' }
  })
  await api('POST', '/schedule/weekly', { token: user.token, body: { days } })
}

export async function dayPlan(user: TestUser, date: string) {
  return api<{ id: string; session_type: string; team_event_id: string | null }>(
    'GET',
    `/schedule/day-plan?date=${date}`,
    { token: user.token },
  )
}

export async function loginAs(page: Page, user: TestUser): Promise<void> {
  await page.goto('/login')
  await page.evaluate(
    ([access, refresh]) => {
      localStorage.setItem('hlu_access_token', access)
      localStorage.setItem('hlu_refresh_token', refresh)
    },
    [user.token, user.refreshToken],
  )
}

// Nothing on the page may be wider than the viewport -- the most common
// way a layout breaks on a phone.
export async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => {
    const width = document.documentElement.clientWidth
    const offenders: string[] = []
    for (const element of Array.from(document.querySelectorAll<HTMLElement>('body *'))) {
      const rect = element.getBoundingClientRect()
      if (rect.width > 0 && (rect.right > width + 1 || rect.left < -1)) {
        const style = getComputedStyle(element)
        // Decorative, clipped-by-parent backgrounds are fine.
        if (style.position === 'absolute' || style.position === 'fixed') {
          continue
        }
        offenders.push(`${element.tagName.toLowerCase()}.${element.className.toString().slice(0, 60)} (${Math.round(rect.left)}..${Math.round(rect.right)})`)
      }
    }
    return { scroll: document.documentElement.scrollWidth, width, offenders: offenders.slice(0, 5) }
  })
  expect(overflow.scroll, `page wider than viewport: ${overflow.offenders.join(', ')}`).toBeLessThanOrEqual(overflow.width)
  expect(overflow.offenders, 'elements sticking out of the viewport').toEqual([])
}

// Viewport-sized on purpose: a fullPage capture paints the fixed
// BottomNav wherever the viewport happened to be, mid-page.
export async function shot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: `e2e/screenshots/${projectLabel(page)}-${name}.png` })
}

// Scrolled to the very bottom, the page's last content must end above the
// fixed BottomNav, not underneath it.
export async function expectBottomNotHiddenByNav(page: Page): Promise<void> {
  // Late data (members, events) grows the page -- measure the final one.
  await page.waitForLoadState('networkidle')
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight))
  await page.waitForTimeout(400)
  const result = await page.evaluate(() => {
    const nav = document.querySelector('nav a[href="/more"]')?.closest('nav')
    if (!nav) {
      return null
    }
    const navTop = nav.getBoundingClientRect().top
    let lowest = 0
    for (const element of Array.from(document.querySelectorAll<HTMLElement>('button, a, input, textarea, p, h1, h2, h3'))) {
      if (nav.contains(element) || element.closest('[role=dialog]')) {
        continue
      }
      const rect = element.getBoundingClientRect()
      if (rect.height > 0 && getComputedStyle(element).visibility !== 'hidden') {
        lowest = Math.max(lowest, rect.bottom)
      }
    }
    return { navTop, lowest }
  })
  if (result !== null) {
    expect(result.lowest, 'last content ends under the bottom navigation').toBeLessThanOrEqual(result.navTop + 1)
  }
}

function projectLabel(page: Page): string {
  const width = page.viewportSize()?.width ?? 0
  return `${width}px`
}
