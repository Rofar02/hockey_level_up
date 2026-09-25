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

export function formatTime(date: Date): string {
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  return `${hours}:${minutes}`
}

// "24.09 в 19:00" -- TeamEvent.starts_at display, local time.
export function formatDateTime(date: Date): string {
  return `${formatShortDate(date)} в ${formatTime(date)}`
}

// <input type="datetime-local"> only accepts/emits a timezone-less
// "YYYY-MM-DDTHH:mm" string, always read as the *browser's* local time --
// this pair converts to/from a real Date without the UTC-midnight shift
// `date.toISOString()` would cause in a non-UTC timezone (same reasoning
// as parseIsoDate above).
export function toDatetimeLocalValue(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}T${formatTime(date)}`
}

export function fromDatetimeLocalValue(value: string): Date {
  const [datePart, timePart] = value.split('T')
  const [year, month, day] = datePart.split('-').map(Number)
  const [hours, minutes] = timePart.split(':').map(Number)
  return new Date(year, month - 1, day, hours, minutes)
}
