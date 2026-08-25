import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { FormError } from '../components/ui/FormError'
import { ShieldIcon } from '../components/ui/ShieldIcon'
import { TextField } from '../components/ui/TextField'
import * as authApi from '../api/auth'
import { ApiError } from '../api/client'

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')

  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (token === null) {
      return
    }
    setError(null)
    if (newPassword !== confirmPassword) {
      setError('Пароли не совпадают.')
      return
    }
    setIsSubmitting(true)
    try {
      const result = await authApi.confirmPasswordReset(token, newPassword)
      setSuccessMessage(result.detail)
    } catch (err) {
      if (err instanceof ApiError && err.status === 410) {
        setError('Эта ссылка уже использована. Запросите новую на странице «Забыли пароль».')
      } else if (err instanceof ApiError) {
        setError(err.message)
      } else {
        setError('Не удалось обновить пароль. Попробуйте ещё раз.')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="relative flex min-h-svh items-center justify-center overflow-hidden px-4">
      <div className="absolute inset-0 bg-[url('/images/arena-bg.webp')] bg-cover bg-center" />
      <div className="absolute inset-0 bg-dark-bg/80" />
      <Card className="relative w-full max-w-sm">
        <h1 className="mb-6 flex items-center gap-2 text-xl font-semibold">
          <ShieldIcon />
          Новый пароль
        </h1>

        {token === null && (
          <FormError message="В ссылке нет кода восстановления. Откройте ссылку из письма ещё раз." />
        )}

        {token !== null && successMessage === null && (
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <TextField
              label="Новый пароль"
              name="new-password"
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              minLength={8}
              required
            />
            <TextField
              label="Повторите пароль"
              name="confirm-password"
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              minLength={8}
              required
            />
            <FormError message={error} />
            <Button type="submit" isLoading={isSubmitting}>
              Сохранить пароль
            </Button>
          </form>
        )}

        {successMessage !== null && (
          <>
            <p className="mb-6 text-sm text-accent-ice">{successMessage}</p>
            <Link to="/login">
              <Button type="button" className="w-full">
                Войти
              </Button>
            </Link>
          </>
        )}
      </Card>
    </div>
  )
}
