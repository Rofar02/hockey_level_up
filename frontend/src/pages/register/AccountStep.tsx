import type { FormEvent } from 'react'
import { Button } from '../../components/ui/Button'
import { TextField } from '../../components/ui/TextField'

// Step 1/3 of registration. Wrapped in its own <form> (submit-boundary =
// "Далее") purely so the existing HTML5 required/minLength constraints on
// these fields still block advancing exactly like they blocked the old
// single-form submit -- no new validation logic needed, just a later submit
// boundary.
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
  function handleSubmit(event: FormEvent) {
    event.preventDefault()
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
      <Button type="submit" className="self-end">
        Далее
      </Button>
    </form>
  )
}
