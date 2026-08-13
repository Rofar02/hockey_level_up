import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { FormError } from '../components/ui/FormError'
import { TextField } from '../components/ui/TextField'
import * as authApi from '../api/auth'
import { ApiError } from '../api/client'

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // The request itself is generic (same response for a real or made-up
  // email, see AuthService.request_password_reset) -- but a 503 (no
  // RESEND_API_KEY configured at all) is a real, honest failure to
  // surface, not something to hide behind the generic message.
  const [resultMessage, setResultMessage] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setResultMessage(null)
    setIsSubmitting(true)
    try {
      const result = await authApi.requestPasswordReset(email)
      setResultMessage(result.detail)
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 503
          ? 'Восстановление пароля сейчас недоступно. Попробуйте позже.'
          : err instanceof ApiError
            ? err.message
            : 'Не удалось отправить запрос. Попробуйте ещё раз.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="relative flex min-h-svh items-center justify-center overflow-hidden px-4">
      <div className="absolute inset-0 bg-[url('/images/arena-bg.webp')] bg-cover bg-center" />
      <div className="absolute inset-0 bg-dark-bg/80" />
      <Card className="relative w-full max-w-sm">
        <h1 className="mb-2 text-xl font-semibold">Забыли пароль?</h1>
        <p className="mb-6 text-sm text-text-secondary">
          Введите email — если аккаунт с таким адресом есть, мы отправим ссылку для сброса пароля.
        </p>
        {resultMessage === null ? (
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
            <FormError message={error} />
            <Button type="submit" isLoading={isSubmitting}>
              Отправить ссылку
            </Button>
          </form>
        ) : (
          <p className="text-sm text-accent-ice">{resultMessage}</p>
        )}
        <p className="mt-6 text-sm text-text-secondary">
          <Link to="/login" className="text-accent-ice hover:underline">
            Вернуться ко входу
          </Link>
        </p>
      </Card>
    </div>
  )
}
