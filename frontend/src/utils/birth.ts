import { pluralRu } from './boardPlan'

// Review 2026-10-11, 3.1-3.3: the birth date and «С какого года играете?»
// instead of a typed-in age and years -- same limits as the backend
// (app/schemas/user.py).
export const MIN_AGE = 6
export const MAX_AGE = 90
const FIRST_HOCKEY_YEAR = 1930

export function fullYears(birthIso: string, today: Date = new Date()): number {
  const [year, month, day] = birthIso.split('-').map(Number)
  const beforeBirthday = today.getMonth() + 1 < month || (today.getMonth() + 1 === month && today.getDate() < day)
  return today.getFullYear() - year - (beforeBirthday ? 1 : 0)
}

export function birthDateError(birthIso: string): string | null {
  if (birthIso === '') return null
  const today = new Date()
  const [year, month, day] = birthIso.split('-').map(Number)
  if (new Date(year, month - 1, day) > today) return 'Дата рождения не может быть в будущем.'
  const age = fullYears(birthIso, today)
  if (age < MIN_AGE || age > MAX_AGE) return `Возраст должен быть от ${MIN_AGE} до ${MAX_AGE} лет.`
  return null
}

export function hockeySinceError(sinceText: string, birthIso: string): string | null {
  if (sinceText.trim() === '') return null
  const since = Number(sinceText)
  if (!Number.isInteger(since) || since < FIRST_HOCKEY_YEAR) return 'Укажите год, например 2018.'
  if (since > new Date().getFullYear()) return 'Год не может быть в будущем.'
  if (birthIso !== '' && since < Number(birthIso.slice(0, 4))) return 'Год начала игры раньше года рождения.'
  return null
}

export function ageLabel(age: number): string {
  return `${age} ${pluralRu(age, ['год', 'года', 'лет'])}`
}

export function playingSinceLabel(since: number | null | undefined, years: number | null | undefined): string | null {
  if (since != null) return `Играю с ${since}`
  if (years != null) return `${years} ${pluralRu(Math.round(years), ['год', 'года', 'лет'])} стажа`
  return null
}
