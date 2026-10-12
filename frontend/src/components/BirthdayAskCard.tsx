import { useState } from 'react'
import * as usersApi from '../api/users'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { birthDateError } from '../utils/birth'
import { toIsoDate } from '../utils/date'
import { Button } from './ui/Button'
import { FormError } from './ui/FormError'
import { TextField } from './ui/TextField'

const HIDDEN_KEY = 'hlu_birthday_ask_hidden'

function readHidden(): boolean {
  try {
    return localStorage.getItem(HIDDEN_KEY) === '1'
  } catch {
    return false
  }
}

// Review 2026-10-11, 3.3: a one-time ask for the birth date, for players
// who registered with a typed-in age (or none) -- the age then stays right
// by itself. «Не сейчас» hides it on this device.
export function BirthdayAskCard() {
  const { user, accessToken, updateUser } = useAuth()
  const [hidden, setHidden] = useState(readHidden)
  const [birthDate, setBirthDate] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  if (user === null || user.birth_date !== null || hidden) {
    return null
  }

  function hide() {
    try {
      localStorage.setItem(HIDDEN_KEY, '1')
    } catch {
      // Private mode -- hidden for this visit only.
    }
    setHidden(true)
  }

  async function save() {
    if (accessToken === null) return
    const problem = birthDate === '' ? 'Выберите дату.' : birthDateError(birthDate)
    if (problem !== null) {
      setError(problem)
      return
    }
    setIsSaving(true)
    setError(null)
    try {
      updateUser(await usersApi.updateProfile({ birth_date: birthDate }, accessToken))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сохранить. Попробуйте ещё раз.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-accent-ice/30 bg-gradient-to-br from-[#1C2A3A] to-dark-card p-4">
      <div className="flex items-start gap-3">
        <i className="ti ti-cake text-xl text-accent-ice" aria-hidden="true" />
        <div className="flex flex-col gap-1">
          <p className="font-semibold leading-snug">Когда у вас день рождения?</p>
          <p className="text-sm leading-snug text-text-secondary">
            Возраст будет обновляться сам — от него зависят нормы теста и рейтинг.
          </p>
        </div>
      </div>
      <TextField
        label="Дата рождения"
        name="birth_date"
        type="date"
        max={toIsoDate(new Date())}
        value={birthDate}
        onChange={(event) => setBirthDate(event.target.value)}
      />
      <FormError message={error} />
      <div className="flex gap-2">
        <Button variant="neutral" onClick={hide} className="flex-1">
          Не сейчас
        </Button>
        <Button onClick={() => void save()} isLoading={isSaving} className="flex-1">
          Сохранить
        </Button>
      </div>
    </div>
  )
}
