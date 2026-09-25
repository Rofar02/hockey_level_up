// The e2e scenarios need "a training later today, at least 2.5h away" and
// a start time earlier today -- impossible late in the evening in any one
// timezone. So the test users and the browser live in whichever of these
// zones is currently mid-day; the backend works in the user's timezone and
// the browser in `timezoneId`, so both agree on what "today" is.
// E2E_TZ pins one explicitly.
const CANDIDATES = [
  'Europe/Moscow',
  'Asia/Dubai',
  'Asia/Tokyo',
  'Pacific/Auckland',
  'Pacific/Honolulu',
  'America/Los_Angeles',
  'America/New_York',
  'Europe/London',
]

function hourIn(tz: string, at = new Date()): number {
  return Number(new Intl.DateTimeFormat('en-GB', { timeZone: tz, hour: '2-digit', hourCycle: 'h23' }).format(at))
}

function pickTimezone(): string {
  return CANDIDATES.find((tz) => {
    const hour = hourIn(tz)
    return hour >= 8 && hour <= 18
  }) ?? 'Europe/Moscow'
}

export const TZ = process.env.E2E_TZ ?? pickTimezone()
