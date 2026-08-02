export const WEEKDAY_LABELS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

export function getMondayOfCurrentWeek(reference: Date = new Date()): Date {
  const monday = new Date(reference)
  const daysSinceMonday = (reference.getDay() + 6) % 7
  monday.setDate(reference.getDate() - daysSinceMonday)
  monday.setHours(0, 0, 0, 0)
  return monday
}

export function addDays(date: Date, days: number): Date {
  const result = new Date(date)
  result.setDate(result.getDate() + days)
  return result
}

export function toIsoDate(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

// Local-date parse -- avoids the UTC-midnight shift `new Date(iso)` causes
// in negative-offset timezones when the caller only cares about the local
// calendar day (weekday label, "is this today").
export function parseIsoDate(iso: string): Date {
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(year, month - 1, day)
}

export function formatShortDate(date: Date): string {
  const day = String(date.getDate()).padStart(2, '0')
  const month = String(date.getMonth() + 1).padStart(2, '0')
  return `${day}.${month}`
}
