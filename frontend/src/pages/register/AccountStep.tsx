import { useState } from 'react'
import type { FormEvent } from 'react'
import * as authApi from '../../api/auth'
import { Button } from '../../components/ui/Button'
import { FormError } from '../../components/ui/FormError'
import { TextField } from '../../components/ui/TextField'

// Step 1/3 of registration. Wrapped in its own <form> (submit-boundary =
// "Далее") purely so the existing HTML5 required/minLength constraints on
// these fields still block advancing exactly like they blocked the old
// single-form submit -- no new validation logic needed, just a later submit
// boundary.
//
// The email-availability check (2026-08-29: "надо сразу давать подсказку
// пользователю если mail уже занят и не пропускать на следующий этап")
// blocks advancing here too -- previously the athlete only found out their
// email was taken at the very end, after filling in the physical-data step,
// when the final POST /auth/register itself 409'd. A dropped/erroring check
// (network hiccup, endpoint down) fails OPEN -- lets them through to the
// real registration submit anyway -- rather than stranding them on step 1
// over something that isn't actually their email being taken.
export function AccountStep({
  email,
  setEmail,
  password,
  setPassword,
  onNext,
}: {
  email: string
  setEmail: (value: string) => void
  password: string
  setPassword: (value: string) => void
  onNext: () => void
}) {
  const [isChecking, setIsChecking] = useState(false)
  const [emailError, setEmailError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setEmailError(null)
    setIsChecking(true)
    try {
      const result = await authApi.checkEmailAvailability(email)
      if (!result.available) {
        setEmailError('Этот email уже зарегистрирован — попробуйте войти или указать другой.')
        return
      }
    } catch {
      // Best-effort -- see the component comment above.
    } finally {
      setIsChecking(false)
    }
    onNext()
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold">Аккаунт</h2>
      <TextField
        label="Email"
        name="email"
        type="email"
        autoComplete="email"
        value={email}
        onChange={(event) => {
          setEmail(event.target.value)
          setEmailError(null)
        }}
        required
      />
      <FormError message={emailError} />
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
      <Button type="submit" disabled={isChecking} className="self-end">
        {isChecking ? 'Проверяем...' : 'Далее'}
      </Button>
    </form>
  )
}
