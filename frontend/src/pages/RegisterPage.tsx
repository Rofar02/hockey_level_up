import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Checkbox } from '../components/ui/Checkbox'
import { FormError } from '../components/ui/FormError'
import { SelectField } from '../components/ui/SelectField'
import { TextField } from '../components/ui/TextField'
import * as authApi from '../api/auth'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { POSITIONS, POSITION_LABELS } from '../types/user'
import type { Position } from '../types/user'

function toOptionalNumber(value: string): number | undefined {
  if (value.trim() === '') {
    return undefined
  }
  const parsed = Number(value)
  return Number.isNaN(parsed) ? undefined : parsed
}

export function RegisterPage() {
  const navigate = useNavigate()
  const { login } = useAuth()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [lastName, setLastName] = useState('')
  const [firstName, setFirstName] = useState('')
  const [patronymic, setPatronymic] = useState('')
  const [jerseyNumber, setJerseyNumber] = useState('')
  const [height, setHeight] = useState('')
  const [weight, setWeight] = useState('')
  const [age, setAge] = useState('')
  const [position, setPosition] = useState('')
  const [yearsOfExperience, setYearsOfExperience] = useState('')
  // Never pre-checked -- the user must actively opt in on every visit to
  // this form, not just once ever (a fresh page load always starts false).
  const [privacyConsent, setPrivacyConsent] = useState(false)

  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)

    const parsedJerseyNumber = Number(jerseyNumber.trim())
    if (
      jerseyNumber.trim() === '' ||
      !Number.isInteger(parsedJerseyNumber) ||
      parsedJerseyNumber < 0 ||
      parsedJerseyNumber > 99
    ) {
      setError('Укажите игровой номер — целое число от 0 до 99.')
      return
    }

    setIsSubmitting(true)
    try {
      await authApi.register({
        email,
        password,
        last_name: lastName,
        first_name: firstName,
        jersey_number: parsedJerseyNumber,
        patronymic: patronymic.trim() === '' ? undefined : patronymic,
        height: toOptionalNumber(height),
        weight: toOptionalNumber(weight),
        age: toOptionalNumber(age),
        position: position === '' ? undefined : (position as Position),
        years_of_experience: toOptionalNumber(yearsOfExperience),
        privacy_consent: privacyConsent,
      })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось зарегистрироваться. Попробуйте ещё раз.')
      setIsSubmitting(false)
      return
    }

    // /auth/register only creates the account, it doesn't return a token
    // (unlike /auth/login) -- reuse the same email/password right away so
    // the user isn't sent to the login screen to type what they just typed.
    try {
      await login(email, password)
      navigate('/', { replace: true })
    } catch {
      // Account exists at this point; only the auto-login itself failed
      // (e.g. a transient network hiccup) -- let them log in manually
      // instead of stranding them on this form.
      navigate('/login', { replace: true })
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="relative flex min-h-svh items-center justify-center overflow-hidden px-4 py-10">
      <div className="absolute inset-0 bg-[url('/images/arena-bg.webp')] bg-cover bg-center" />
      <div className="absolute inset-0 bg-dark-bg/80" />
      <Card className="relative w-full max-w-md">
        <h1 className="mb-6 text-xl font-semibold">Регистрация</h1>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <TextField
            label="Email"
            name="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
          <TextField
            label="Пароль"
            name="password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            minLength={8}
            maxLength={128}
            required
          />

          <div className="grid grid-cols-2 gap-4">
            <TextField
              label="Фамилия"
              name="last_name"
              autoComplete="family-name"
              value={lastName}
              onChange={(event) => setLastName(event.target.value)}
              maxLength={100}
              required
            />
            <TextField
              label="Имя"
              name="first_name"
              autoComplete="given-name"
              value={firstName}
              onChange={(event) => setFirstName(event.target.value)}
              maxLength={100}
              required
            />
          </div>
          <TextField
            label="Отчество (необязательно)"
            name="patronymic"
            autoComplete="additional-name"
            value={patronymic}
            onChange={(event) => setPatronymic(event.target.value)}
            maxLength={100}
          />
          <TextField
            label="Игровой номер"
            name="jersey_number"
            type="number"
            numeric
            min={0}
            max={99}
            value={jerseyNumber}
            onChange={(event) => setJerseyNumber(event.target.value)}
            required
          />

          <div className="grid grid-cols-2 gap-4">
            <TextField
              label="Рост, см"
              name="height"
              type="number"
              numeric
              min={0}
              value={height}
              onChange={(event) => setHeight(event.target.value)}
            />
            <TextField
              label="Вес, кг"
              name="weight"
              type="number"
              numeric
              min={0}
              value={weight}
              onChange={(event) => setWeight(event.target.value)}
            />
            <TextField
              label="Возраст"
              name="age"
              type="number"
              numeric
              min={0}
              value={age}
              onChange={(event) => setAge(event.target.value)}
            />
            <TextField
              label="Стаж, лет"
              name="years_of_experience"
              type="number"
              numeric
              min={0}
              step="0.5"
              value={yearsOfExperience}
              onChange={(event) => setYearsOfExperience(event.target.value)}
            />
          </div>

          <SelectField
            label="Позиция"
            name="position"
            placeholder="Не выбрано"
            value={position}
            onChange={(event) => setPosition(event.target.value)}
            options={POSITIONS.map((value) => ({ value, label: POSITION_LABELS[value] }))}
          />

          <label className="flex cursor-pointer items-start gap-2.5">
            <Checkbox checked={privacyConsent} onClick={() => setPrivacyConsent((value) => !value)} />
            <span className="text-sm text-text-secondary">
              Я согласен с{' '}
              <Link
                to="/privacy"
                target="_blank"
                rel="noreferrer"
                className="text-accent-ice hover:underline"
                onClick={(event) => event.stopPropagation()}
              >
                Политикой обработки персональных данных
              </Link>
            </span>
          </label>

          <FormError message={error} />
          <Button type="submit" isLoading={isSubmitting} disabled={!privacyConsent}>
            Зарегистрироваться
          </Button>
        </form>
        <p className="mt-6 text-sm text-text-secondary">
          Уже есть аккаунт?{' '}
          <Link to="/login" className="text-accent-ice hover:underline">
            Войти
          </Link>
        </p>
      </Card>
    </div>
  )
}
