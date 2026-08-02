import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { FormError } from '../components/ui/FormError'
import { SelectField } from '../components/ui/SelectField'
import { TextField } from '../components/ui/TextField'
import * as authApi from '../api/auth'
import { ApiError } from '../api/client'
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

  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [height, setHeight] = useState('')
  const [weight, setWeight] = useState('')
  const [age, setAge] = useState('')
  const [position, setPosition] = useState('')
  const [yearsOfExperience, setYearsOfExperience] = useState('')

  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setIsSubmitting(true)
    try {
      await authApi.register({
        username,
        email,
        password,
        height: toOptionalNumber(height),
        weight: toOptionalNumber(weight),
        age: toOptionalNumber(age),
        position: position === '' ? undefined : (position as Position),
        years_of_experience: toOptionalNumber(yearsOfExperience),
      })
      navigate('/login', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось зарегистрироваться. Попробуйте ещё раз.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-svh items-center justify-center px-4 py-10">
      <Card className="w-full max-w-md">
        <h1 className="mb-6 text-xl font-semibold">Регистрация</h1>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <TextField
            label="Имя пользователя"
            name="username"
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            minLength={3}
            maxLength={50}
            required
          />
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

          <FormError message={error} />
          <Button type="submit" isLoading={isSubmitting}>
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
